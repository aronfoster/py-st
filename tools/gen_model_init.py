#!/usr/bin/env python3
from pathlib import Path

ROOT = Path("src/py_st/_generated/models")
INIT = ROOT / "__init__.py"


def main() -> None:
    mods = [
        p.stem for p in sorted(ROOT.glob("*.py")) if p.name != "__init__.py"
    ]
    lines = [
        "# Auto-generated: export real model names for package imports\n",
        "__all__ = [\n",
    ]
    for m in mods:
        lines.append(f'    "{m}",\n')
    lines.append("]\n\n")
    for m in mods:
        lines.append(f"from .{m} import {m}\n")
    INIT.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
