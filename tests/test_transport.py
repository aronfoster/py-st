"""Real HTTPX query handling through the shared transport."""

import httpx
import pytest

from py_st.client.transport import HttpTransport


def test_fractional_cooldown_is_not_truncated() -> None:
    waits: list[float] = []
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                409,
                json={
                    "error": {
                        "code": 4000,
                        "data": {"cooldown": {"remainingSeconds": 1.75}},
                    }
                },
            )
        return httpx.Response(200, json={"data": {"ok": True}})

    with httpx.Client(
        base_url="https://offline.invalid",
        transport=httpx.MockTransport(handler),
    ) as client:
        transport = HttpTransport(client, interval=0, wait=waits.append)
        transport.request_json("POST", "/orbit")
    assert attempts == 2
    assert 2.0 in waits


def test_transport_failure_preserves_pacing_without_mutation_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("py_st.client.transport.time.monotonic", lambda: 10.0)
    waits: list[float] = []
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadError("Synthetic lost response")
        return httpx.Response(200, json={"data": {"ok": True}})

    with httpx.Client(
        base_url="https://offline.invalid",
        transport=httpx.MockTransport(handler),
    ) as client:
        transport = HttpTransport(client, interval=0.55, wait=waits.append)
        with pytest.raises(httpx.ReadError):
            transport.request_json("POST", "/orbit")
        assert attempts == 1
        transport.request_json("GET", "/ship")
    assert attempts == 2
    assert waits[-1] == pytest.approx(0.55)


@pytest.mark.parametrize("params,expected", [(None, "page=3"), ({}, "")])
def test_nonpaginated_query_preserves_absent_params(
    params: dict[str, str] | None, expected: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": {"ok": True}})

    with httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        transport = HttpTransport(client, interval=0)
        assert transport.request_json(
            "GET", "/waypoints?page=3", params=params
        ) == {"ok": True}

    assert len(requests) == 1
    assert requests[0].url.query.decode() == expected
