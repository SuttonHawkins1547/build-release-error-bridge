import httpx

from release_diagnostics.infrai_client import InfraiClient


def test_capture_honors_retry_after_without_changing_idempotency_key() -> None:
    requests: list[httpx.Request] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={
                    "ok": False,
                    "data": None,
                    "error": {"code": "RATE_LIMITED", "message": "retry later"},
                    "metadata": {},
                },
            )
        return httpx.Response(
            200,
            json={
                "ok": True,
                "data": {"event_id": "evt-8", "error_group_id": "grp-2"},
                "error": None,
                "metadata": {},
            },
        )

    client = InfraiClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        sleep=delays.append,
    )
    result = client.capture_build_error(
        build_id="build-8",
        service="ledger-api",
        commit_sha="1234567",
        exception="CompileError: schema mismatch",
    )
    client.close()

    assert result["event_id"] == "evt-8"
    assert delays == [2.0]
    assert [request.headers["Idempotency-Key"] for request in requests] == [
        "build-error:build-8",
        "build-error:build-8",
    ]
