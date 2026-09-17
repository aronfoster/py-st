"""Local owner password verifier; plaintext passwords are never retained."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from functools import lru_cache
from pathlib import Path


def save_password(root: Path, password: str) -> None:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 600000
    )
    path = root / ".state/owner.json"
    with open(
        path, "x", opener=lambda p, flags: os.open(p, flags, 0o600)
    ) as file:
        json.dump({"salt": salt, "digest": digest.hex()}, file)


def verify_password(root: Path, password: str) -> bool:
    record = json.loads((root / ".state/owner.json").read_text())
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), record["salt"].encode(), 600000
    ).hex()
    return secrets.compare_digest(digest, record["digest"])


def validate_owner(root: Path, *, hosted: bool = False) -> None:
    path = root / ".state/owner.json"
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError
        record = json.loads(path.read_text())
        if (
            not isinstance(record, dict)
            or set(record) != {"salt", "digest"}
            or not isinstance(record["salt"], str)
            or not isinstance(record["digest"], str)
            or not re.fullmatch(r"[a-f0-9]{32}", record["salt"])
            or not re.fullmatch(r"[a-f0-9]{64}", record["digest"])
            or (hosted and path.stat().st_mode & 0o077)
            or (hosted and _blank(record["salt"], record["digest"]))
        ):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError(
            "Owner authentication missing, malformed, public or blank"
        ) from None


@lru_cache(maxsize=16)
def _blank(salt: str, digest: str) -> bool:
    return secrets.compare_digest(
        hashlib.pbkdf2_hmac("sha256", b"", salt.encode(), 600000).hex(),
        digest,
    )
