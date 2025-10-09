from __future__ import annotations

import httpx
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential


class Agent(BaseModel):
    symbol: str


class SpaceTraders:
    def __init__(self, token: str) -> None:
        self._client = httpx.Client(
            base_url="https://api.spacetraders.io/v2",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=30,
        )

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5))
    def get_agent(self) -> Agent:
        r = self._client.get("/my/agent")
        r.raise_for_status()
        return Agent.model_validate(r.json()["data"])
