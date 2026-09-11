"""Real HTTPX query handling through the shared transport."""

import httpx
import pytest

from py_st.client.transport import HttpTransport


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
