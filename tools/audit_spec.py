"""Explicit read-only comparison with upstream OpenAPI, without credentials."""

import json
from pathlib import Path

import httpx


def main() -> None:
    local = json.loads(
        Path("src/py_st/_generated/reference/SpaceTraders.json").read_text()
    )
    response = httpx.get(
        "https://raw.githubusercontent.com/SpaceTradersAPI/"
        "api-docs/main/reference/SpaceTraders.json",
        timeout=30,
    )
    response.raise_for_status()
    upstream = response.json()
    print(
        json.dumps(
            {
                "vendored_version": local["info"]["version"],
                "upstream_version": upstream["info"]["version"],
                "vendored_paths": len(local["paths"]),
                "upstream_paths": len(upstream["paths"]),
                "missing_paths": sorted(
                    set(upstream["paths"]) - set(local["paths"])
                ),
                "removed_paths": sorted(
                    set(local["paths"]) - set(upstream["paths"])
                ),
                "note": "Path/version audit, not full model equivalence",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
