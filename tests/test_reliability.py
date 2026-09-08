from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from py_st import cache
from py_st.client.transport import APIError, HttpTransport
from py_st.services import contracts, ships


@pytest.mark.parametrize("code,status", [(4214, 409), (4113, 400), (0, 401)])
def test_non_retryable_errors(code: int, status: int) -> None:
    # Arrange
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": code}})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://test"
    )
    transport = HttpTransport(client, interval=0)
    # Act
    with pytest.raises(APIError) as caught:
        transport.request_json("POST", "/mutation")
    # Assert
    assert len(calls) == 1
    assert caught.value.code == code
    assert caught.value.authentication_failed == (
        code == 4113 or status == 401
    )


@pytest.mark.parametrize("status,delay", [(429, 3.0), (409, 2.25)])
def test_semantic_retry(status: int, delay: float) -> None:
    # Arrange
    waits: list[float] = []
    responses = iter(
        [
            httpx.Response(
                status,
                headers={"Retry-After": "3"},
                json={
                    "error": {
                        "code": 4000,
                        "data": {"cooldown": {"remainingSeconds": 2}},
                    }
                },
            ),
            httpx.Response(200, json={"data": {"ok": True}}),
        ]
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: next(responses)),
        base_url="https://test",
    )
    # Act
    result = HttpTransport(client, interval=0, wait=waits.append).request_json(
        "POST", "/mutation"
    )
    # Assert
    assert result == {"ok": True}
    assert delay in waits


def test_atomic_cache_preserves_previous_on_replace_failure(
    tmp_path: Path,
) -> None:
    # Arrange
    target = tmp_path / "data.json"
    target.write_text('{"old": true}')
    with (
        patch.object(cache, "CACHE_DIR", tmp_path),
        patch.object(cache, "CACHE_FILE", target),
        patch("py_st.cache.os.replace", side_effect=OSError("disk")),
    ):
        # Act
        cache.save_cache({"new": True})
        # Assert
        assert cache.load_cache() == {"old": True}
        assert list(tmp_path.iterdir()) == [target]


def test_authentication_failure_latches_even_with_malformed_body() -> None:
    # Arrange
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            401, content="broken", headers={"Content-Type": "application/json"}
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://test"
    )
    transport = HttpTransport(client, interval=0)
    # Act
    for _ in range(2):
        with pytest.raises(APIError) as exc:
            transport.request_json("GET", "/my/agent")
        assert exc.value.authentication_failed
    # Assert
    assert len(calls) == 1


def test_repeating_pagination_metadata_stops() -> None:
    # Arrange
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "data": [{"id": 1}],
                    "meta": {"total": 100, "limit": 1, "page": 1},
                },
            )
        ),
        base_url="https://test",
    )
    # Act / Assert
    with pytest.raises(APIError, match="pagination"):
        HttpTransport(client, interval=0).request_json(
            "GET", "/list", paginate=True
        )


def test_nonfinite_retry_header_stops() -> None:
    # Arrange
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                429,
                headers={"Retry-After": "nan"},
                json={"error": {"code": 429}},
            )
        ),
        base_url="https://test",
    )
    # Act / Assert
    with pytest.raises(APIError, match="Retry-After"):
        HttpTransport(client, interval=0).request_json("GET", "/list")


@pytest.mark.parametrize("operation", ["purchase", "deliver"])
def test_legacy_mutation_invalidates_before_uncertain_failure(
    tmp_path: Path,
    operation: str,
) -> None:
    # Arrange
    client = MagicMock()
    client.ships.purchase_cargo.side_effect = httpx.ReadTimeout("uncertain")
    client.contracts.deliver_contract.side_effect = httpx.ReadTimeout(
        "uncertain"
    )
    with (
        patch.object(cache, "CACHE_DIR", tmp_path),
        patch.object(cache, "CACHE_FILE", tmp_path / "cache.json"),
        patch.object(ships, "SpaceTradersClient", return_value=client),
        patch.object(contracts, "SpaceTradersClient", return_value=client),
    ):
        cache.save_cache(
            {
                "agent_info": {"credits": 100000},
                "ship_list": {"is_dirty": False},
                "market_X-A-1": {"price": 1},
                "contract_list": {"is_dirty": False},
            }
        )
        # Act
        with pytest.raises(httpx.ReadTimeout):
            if operation == "purchase":
                ships.purchase_cargo("T", "S", "IRON", 1)
            else:
                contracts.deliver_contract("T", "C", "S", "IRON", 1)
        # Assert
        data = cache.load_cache()
        assert "agent_info" not in data
        assert "market_X-A-1" not in data
        assert data["ship_list"]["is_dirty"]
        assert data["contract_list"]["is_dirty"] == (operation == "deliver")
