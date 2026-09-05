import httpx
from fastapi.testclient import TestClient

from release_diagnostics.infrai_client import InfraiClient
from release_diagnostics.service import create_app


def test_failed_build_is_held_and_handed_to_group_diagnostics() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v1/errors/capture":
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "data": {"event_id": "evt-42", "error_group_id": "grp-api-build"},
                    "error": None,
                    "metadata": {},
                },
            )
        return httpx.Response(
            200,
            json={
                "ok": True,
                "data": {
                    "is_resolved": False,
                    "count": 3,
                    "representative_event": {"event_id": "evt-42"},
                },
                "error": None,
                "metadata": {},
            },
        )

    infrai = InfraiClient(api_key="test-key", transport=httpx.MockTransport(handler))
    with TestClient(create_app(infrai)) as service:
        capture = service.post(
            "/build-events/failed",
            json={
                "build_id": "build-1042",
                "service": "checkout-api",
                "commit_sha": "8c9d711",
                "exception": "CompileError: generated client is stale",
            },
        )
        diagnostic = service.get("/release-diagnostics/grp-api-build")

    assert capture.status_code == 200
    assert capture.json() == {
        "event_id": "evt-42",
        "error_group_id": "grp-api-build",
        "release_action": "hold",
    }
    assert diagnostic.json()["count"] == 3
    assert [request.method for request in calls] == ["POST", "GET"]
    assert calls[0].headers["Idempotency-Key"] == "build-error:build-1042"
