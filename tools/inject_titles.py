#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def pascal(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    out = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if not out:
        out = "Model"
    if out[0].isdigit():
        out = f"X{out}"
    return out


def main() -> None:
    root = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("src/py_st/_generated/reference/models")
    )
    updated = 0

    for path in sorted(root.glob("*.json")):
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue  # only handle schema objects
        if data.get("title"):
            continue  # already has a title; leave it alone

        data["title"] = pascal(path.stem)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        updated += 1

    print(f"set title in {updated} files under {root}")


if __name__ == "__main__":
    main()
