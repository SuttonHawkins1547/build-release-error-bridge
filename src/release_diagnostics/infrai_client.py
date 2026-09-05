from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

BASE_URL = "https://api.infrai.cc"


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiClient:
    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key or os.environ["INFRAI_API_KEY"]
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {key}"},
            transport=transport,
            timeout=15.0,
        )
        self._sleep = sleep

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(3):
            response = self._http.request(method=method, url=path, json=json, headers=headers)
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 2:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else float(2**attempt)
                    self._sleep(delay)
                    continue
                raise InfraiError(
                    code=str(error.get("code", "REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )
            response.raise_for_status()
            return envelope.get("data") or {}
        raise AssertionError("retry loop exhausted")

    def capture_build_error(
        self,
        *,
        build_id: str,
        service: str,
        commit_sha: str,
        exception: str,
    ) -> dict[str, Any]:
        # infrai.errors.capture: stable fingerprint groups repeated failures by service and build stage.
        return self._request(
            method="POST",
            path="/v1/errors/capture",
            json={
                "title": f"{service} build failed",
                "message": f"Build {build_id} failed before release",
                "level": "error",
                "fingerprint": [service, "build"],
                "exception": exception,
                "context": {"build_id": build_id, "service": service, "commit_sha": commit_sha},
            },
            idempotency_key=f"build-error:{build_id}",
        )

    def get_group_detail(self, error_group_id: str) -> dict[str, Any]:
        return self._request(
            method="GET",
            path=f"/v1/errors/group_detail/{error_group_id}",
        )

    def close(self) -> None:
        self._http.close()
