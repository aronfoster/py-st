import os

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential


class Agent(BaseModel):
    symbol: str


class SpaceTraders:
    def __init__(self, token: str | None = None):
        load_dotenv()
        if token is None:
            token = os.getenv("ST_TOKEN")
            if not token:
                raise ValueError("ST_TOKEN not found in environment variables")
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
        return Agent.model_validate(r.json().get("data"))


if __name__ == "__main__":
    print("py_st import OK")
