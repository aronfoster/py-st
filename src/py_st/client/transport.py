from __future__ import annotations

import time
from typing import Any, cast

import httpx


class CooldownException(Exception):
    def __init__(self, cooldown_data: dict[str, Any]) -> None:
        self.cooldown = cooldown_data
        remaining = cooldown_data.get("remainingSeconds", 0)
        super().__init__(
            f"Ship is on cooldown. Try again in {remaining} seconds."
        )


class APIError(Exception):
    """Custom exception for API errors."""

    pass


class HttpTransport:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def request_json(
        self, method: str, url: str, json: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """
        Makes a request to the API, handling errors and cooldowns.
        """
        try:
            r = self._client.request(method, url, json=json)

            if r.status_code == 409:
                error_data = cast(dict[str, Any], r.json().get("error", {}))
                cooldown = cast(
                    dict[str, Any],
                    error_data.get("data", {}).get("cooldown", {}),
                )
                wait_time = cooldown.get("remainingSeconds", 0)

                print(f"Ship on cooldown. Waiting for {wait_time} seconds...")
                time.sleep(wait_time + 1)

                r = self._client.request(method, url, json=json)

            r.raise_for_status()
            return cast(dict[str, Any] | list[Any], r.json()["data"])

        except httpx.HTTPStatusError as e:
            error_details = e.response.json().get("error", {})
            message = error_details.get("message", e.response.text)
            raise APIError(f"API Error: {message}") from e
        except httpx.RequestError as e:
            raise APIError(f"Request failed: {e}") from e
