from __future__ import annotations

import time
from typing import Any, cast

import httpx

JSONDict = dict[str, Any]
JSONList = list[dict[str, Any]]
JSON = JSONDict | JSONList

_MAX_ATTEMPTS_PER_PAGE = 5
_RATE_LIMIT_SLEEP_SEC = 1.0
_DEFAULT_LIMIT = 20


class APIError(Exception):
    """
    Raised for non-retriable API errors or when retry budget is exhausted.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


class HttpTransport:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        paginate: bool = False,
    ) -> JSON:
        """
        Make a request with bounded retries for:
          - 409 (cooldown): wait remainingSeconds + small pad, retry
          - 429 (rate limit): wait 1s, retry
        If paginate=True and response 'data' is a list, fetch all pages:
          - First call omits 'page', limit=20 unless caller provided
          - Subsequent calls set page=2..N with the same limit
        Returns:
          - list when data is a list (concatenated across pages)
          - dict when data is an object
        """
        base_params: dict[str, Any] = dict(params or {})

        collected_items: JSONList = []
        page_number = 1
        first_request = True

        while True:
            request_params = dict(base_params)

            if paginate:
                request_params.setdefault("limit", _DEFAULT_LIMIT)
                if not first_request:
                    page_number += 1
                    request_params["page"] = page_number

            payload = self._send_with_retries(
                method, path, params=request_params, json=json
            )

            data = payload.get("data")
            meta = payload.get("meta") or {}

            if isinstance(data, list):
                collected_items.extend(data)
            else:
                if not paginate:
                    return cast(JSONDict, data)
                collected_items.append(
                    cast(JSONDict, data)
                    if isinstance(data, dict)
                    else {"value": data}
                )

            if not paginate:
                return (
                    collected_items
                    if isinstance(data, list)
                    else cast(JSONDict, data)
                )

            total_items = int(meta.get("total", len(collected_items)))
            limit_used = int(
                meta.get("limit", request_params.get("limit", _DEFAULT_LIMIT))
            )
            current_page = int(meta.get("page", page_number))

            if current_page * limit_used >= total_items or (
                isinstance(data, list) and len(data) == 0
            ):
                return collected_items

            first_request = False

    def _send_with_retries(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> JSONDict:
        """
        Send a single page with retries for 409/429 only. Returns full payload.
        """
        attempts = 0
        while True:
            response = self._client.request(
                method, path, params=params, json=json
            )
            content_type = response.headers.get("content-type", "")
            is_json = content_type.startswith("application/json")

            # 409 Cooldown — wait remainingSeconds (+pad), then retry
            if response.status_code == 409 and is_json:
                attempts += 1
                if attempts > _MAX_ATTEMPTS_PER_PAGE:
                    raise APIError(
                        "Retry budget exhausted (cooldown)", status=409
                    )
                error = response.json().get("error", {})
                cooldown = (error.get("data") or {}).get("cooldown") or {}
                wait_seconds = int(cooldown.get("remainingSeconds", 1))
                time.sleep(max(1, wait_seconds) + 0.25)
                continue

            # 429 Rate limit — wait fixed interval, then retry
            if response.status_code == 429:
                attempts += 1
                if attempts > _MAX_ATTEMPTS_PER_PAGE:
                    raise APIError(
                        "Retry budget exhausted (rate limit)", status=429
                    )
                time.sleep(_RATE_LIMIT_SLEEP_SEC)
                continue

            # Other errors — raise with payload if available
            if response.status_code >= 400:
                payload = response.json() if is_json else {}
                message = (payload.get("error") or {}).get(
                    "message"
                ) or response.text
                raise APIError(
                    message, status=response.status_code, payload=payload
                )

            cast(JSONDict, response.json())
