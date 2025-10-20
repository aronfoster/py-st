#!/usr/bin/env python3
from pathlib import Path

GENERATED_DIR = Path("src/py_st/_generated/models")
OUT = Path("src/py_st/models.py")

HEADER = """# Auto-generated re-exports from _generated.models/*.py
# Order is deterministic; each symbol tries NamedClass then falls back to Model
"""


def main() -> None:
    modules = []
    for p in sorted(GENERATED_DIR.glob("*.py")):
        if p.name == "__init__.py":
            continue
        name = p.stem
        if not name.isidentifier():
            continue
        modules.append(name)

    lines = [HEADER, "__all__ = [\n"]
    for m in modules:
        lines.append(f'    "{m}",\n')
    lines.append("]\n\n")

    for m in modules:
        lines.append(
            f"try:\n"
            f"    from py_st._generated.models.{m} import {m} as {m}\n"
            f"except ImportError:\n"
            f"    from py_st._generated.models.{m} import Model as {m}\n"
        )

    OUT.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
