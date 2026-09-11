from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
        error = self.payload.get("error")
        self.code = error.get("code") if isinstance(error, dict) else None
        self.authentication_failed = status == 401 or self.code == 4113


class RequestAborted(APIError):
    """Interrupted before dispatch; all earlier attempts were rejected."""


class HttpTransport:
    def __init__(
        self,
        client: httpx.Client,
        *,
        interval: float = 0.55,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._interval = interval
        self._wait = wait
        self._next_request = 0.0
        self._auth_error: APIError | None = None

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
          - 409 / code 4000: wait remainingSeconds + small pad, retry
          - 429: honor Retry-After header or payload, with a 1s minimum
        If paginate=True and response 'data' is a list, fetch all pages:
          - First call omits 'page', limit=20 unless caller provided
          - Subsequent calls set page=2..N with the same limit
        Returns:
          - list when data is a list (concatenated across pages)
          - dict when data is an object
        """
        base_params: dict[str, Any] = dict(params or {})

        collected_items: JSONList = []
        page_number = int(base_params.get("page", 1))
        first_request = True

        while True:
            request_params = dict(base_params)

            if paginate:
                request_params.setdefault("limit", _DEFAULT_LIMIT)
                if not first_request:
                    page_number += 1
                    request_params["page"] = page_number
                if page_number > 10_000:
                    raise APIError("Pagination budget exhausted")

            payload = self._send_with_retries(
                method,
                path,
                params=(
                    None if params is None and not paginate else request_params
                ),
                json=json,
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
            if current_page != page_number or limit_used <= 0:
                raise APIError(
                    "Invalid pagination metadata; refusing repeated pages"
                )

            if current_page * limit_used >= total_items or (
                isinstance(data, list) and len(data) == 0
            ):
                return collected_items

            first_request = False

    def _wait_before_dispatch(
        self, seconds: float, rejection_status: int | None
    ) -> None:
        # Only call between attempts, never around network I/O or parsing.
        try:
            self._wait(seconds)
        except BaseException as exc:
            raise RequestAborted(
                "Interrupted before dispatch", status=rejection_status
            ) from exc

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
        rejection_status: int | None = None
        while True:
            if self._auth_error is not None:
                raise self._auth_error
            self._wait_before_dispatch(
                max(0, self._next_request - time.monotonic()), rejection_status
            )
            response = self._client.request(
                method, path, params=params, json=json
            )
            self._next_request = time.monotonic() + self._interval
            content_type = response.headers.get("content-type", "")
            is_json = content_type.startswith("application/json")

            try:
                payload = response.json() if is_json else {}
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            error = payload.get("error") or {}
            if not isinstance(error, dict):
                error = {}
            if response.status_code == 401 or error.get("code") == 4113:
                self._auth_error = APIError(
                    "Authentication/reset mismatch: update ST_TOKEN; "
                    "automation stopped without registration.",
                    status=response.status_code,
                    payload=payload,
                )
                raise self._auth_error

            # Negotiation is one attempt, followed by fresh offer review.
            negotiate = method == "POST" and path.endswith(
                "/negotiate/contract"
            )
            # Only a documented cooldown rejection is safe to replay.
            if (
                not negotiate
                and response.status_code == 409
                and error.get("code") == 4000
            ):
                rejection_status = 409
                attempts += 1
                if attempts > _MAX_ATTEMPTS_PER_PAGE:
                    raise APIError(
                        "Retry budget exhausted (cooldown)", status=409
                    )
                cooldown = (error.get("data") or {}).get("cooldown") or {}
                wait_seconds = int(cooldown.get("remainingSeconds", 1))
                self._wait_before_dispatch(
                    max(1, wait_seconds) + 0.25, rejection_status
                )
                continue

            # A 429 is a definitive rejection, not an uncertain mutation.
            if response.status_code == 429 and not negotiate:
                rejection_status = 429
                attempts += 1
                if attempts > _MAX_ATTEMPTS_PER_PAGE:
                    raise APIError(
                        "Retry budget exhausted (rate limit)", status=429
                    )
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = float(retry_after)
                except ValueError:
                    try:
                        delay = (
                            parsedate_to_datetime(retry_after)
                            - datetime.now(UTC)
                        ).total_seconds()
                    except (ValueError, TypeError):
                        data = error.get("data")
                        fallback = (
                            data.get("retryAfter", _RATE_LIMIT_SLEEP_SEC)
                            if isinstance(data, dict)
                            else _RATE_LIMIT_SLEEP_SEC
                        )
                        try:
                            delay = float(fallback)
                        except (TypeError, ValueError):
                            raise APIError(
                                "Invalid Retry-After", status=429
                            ) from None
                if not math.isfinite(delay):
                    raise APIError("Invalid Retry-After", status=429)
                self._wait_before_dispatch(
                    max(_RATE_LIMIT_SLEEP_SEC, delay), rejection_status
                )
                continue

            # Other errors — raise with payload if available
            if response.status_code >= 400:
                message = (
                    error.get("message")
                    or response.text
                    or "API request failed"
                )
                raise APIError(
                    message, status=response.status_code, payload=payload
                )

            if not payload:
                raise APIError(
                    "Missing JSON response object", status=response.status_code
                )
            return cast(JSONDict, payload)
