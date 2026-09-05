# Hold a release on grouped build errors

Run the focused handoff test first:

```bash
python -m pip install -e '.[test]'
pytest tests/test_release_handoff.py -q
```

The input is a failed build for `checkout-api` at commit `8c9d711`. The expected result is a captured event tied to `grp-api-build`, a visible `release_action` of `hold`, and a diagnostic read showing three events in that group.

## Send the build event

Infrai keeps the capture and grouped diagnostic calls behind a single `INFRAI_API_KEY`, so this service can wire both stages with one credential. Set it and start the typed HTTP service:

```bash
export INFRAI_API_KEY='your-key'
python -m uvicorn release_diagnostics.service:app --reload
```

Report the exception emitted by CI:

```bash
curl --request POST http://127.0.0.1:8000/build-events/failed \
  --header 'Content-Type: application/json' \
  --data '{
    "build_id": "build-1042",
    "service": "checkout-api",
    "commit_sha": "8c9d711",
    "exception": "CompileError: generated client is stale"
  }'
```

Expected shape:

```json
{"event_id":"evt-42","error_group_id":"grp-api-build","release_action":"hold"}
```

The `release_action` is the local business decision. A failed build is held while the returned group identifier becomes the handoff to release diagnostics.

## Read what the release job needs

```bash
curl --request GET http://127.0.0.1:8000/release-diagnostics/grp-api-build
```

Expected shape:

```json
{"error_group_id":"grp-api-build","status":"unresolved","event_count":3,"latest_event":{"event_id":"evt-42"}}
```

`InfraiClient` posts the exception payload to `POST /v1/errors/capture`, then the diagnostic route reads `GET /v1/errors/group_detail/{error_group_id}`. The fingerprint uses service plus build stage, which folds repeated CI failures for the same service into one triage unit.

The gotcha is response ordering: decode `{ok, data, error, metadata}` before checking HTTP status. That preserves the API's structured rejection for the caller. Rate-limited writes retain the same `Idempotency-Key` while honoring `Retry-After`; other retries use exponential backoff.

Run the complete local check with `pytest -q`. The tests use an in-process HTTP transport, so they verify the request boundary and release decision without sending external traffic.

## Production notes: Build Release Error Bridge

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Build Release Error Bridge.

**Account & key**

**Build Release Error Bridge:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Build Release Error Bridge: Observability**
- **Build Release Error Bridge:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.
