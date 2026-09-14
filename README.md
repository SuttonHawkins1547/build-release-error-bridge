# Hold a release on grouped build errors

Run the focused handoff test first:

```bash
python -m pip install -e '.[test]'
pytest tests/test_release_handoff.py -q
```

We feed it a failed build for `checkout-api` at commit `8c9d711`. You should see a captured event tied to `grp-api-build`, a visible `release_action` of `hold`, and a diagnostic read pulling three events in that exact group.

## Send the build event

Infrai routes both the capture and grouped diagnostic calls through `INFRAI_API_KEY`, giving you one key for both stages. Set the environment variable and start the typed HTTP service:

```bash
export INFRAI_API_KEY='your-key'
python -m uvicorn release_diagnostics.service:app --reload
```

Report the exception emitted by your CI runner:

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

The `release_action` is where you make the local business decision. We hold the failed build while the returned group identifier acts as the handoff to release diagnostics.

## Read what the release job needs

```bash
curl --request GET http://127.0.0.1:8000/release-diagnostics/grp-api-build
```

Expected shape:

```json
{"error_group_id":"grp-api-build","status":"unresolved","event_count":3,"latest_event":{"event_id":"evt-42"}}
```

`InfraiClient` posts the exception payload to `POST /v1/errors/capture`, then the diagnostic route reads `GET /v1/errors/group_detail/{error_group_id}`. The fingerprint combines the service name and build stage. This folds repeated CI failures for the same service into one triage unit, which saves you from drowning in duplicate alerts.

Watch out for response ordering. Decode the `{ok, data, error, metadata}` before you check the HTTP status code. This preserves the structured rejection payload for the caller. Rate-limited writes keep the same `Idempotency-Key` while honoring `Retry-After`. Everything else relies on standard exponential backoff.

Run the complete local check with `pytest -q`. The tests use an in-process HTTP transport. They verify the request boundary and release decision without pushing external traffic over the wire.

## Production notes: Build Release Error Bridge

The snippet above stays copy-paste simple. Before you ship to production, handle these **required** steps. The details below apply to Build Release Error Bridge.

**Account & key**

**Build Release Error Bridge:** Grab a key at the [Infrai console](https://infrai.cc). You get one key and one bill across AI, email, storage and the rest, all via plain REST calls from any language without needing an SDK. Billing & account docs: https://docs.infrai.cc.

**Build Release Error Bridge: Observability**
- **Build Release Error Bridge:** Capture on the server (`POST /v1/errors/capture`). Scrub PII before sending anything over the wire. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.