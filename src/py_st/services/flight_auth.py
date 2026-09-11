"""Local owner password verifier; plaintext passwords are never retained."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
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
