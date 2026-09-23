"""Explicit hosted trust boundary; proxy headers never grant authority."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from py_st.services.flight_auth import validate_owner
from py_st.services.flight_queue import FlightQueue
from py_st.services.intelligence import Intelligence


@dataclass(frozen=True)
class PublicOrigin:
    origin: str
    authority: str

    @classmethod
    def parse(cls, value: str) -> PublicOrigin:
        error = "Public origin must be one unambiguous HTTPS origin"
        if not value.isascii() or any(c.isspace() for c in value):
            raise ValueError(error)
        if any(c in value for c in "\\%?#@"):
            raise ValueError(error)
        try:
            parsed = urlsplit(value)
            host, port = parsed.hostname, parsed.port
        except ValueError:
            raise ValueError(error) from None
        if parsed.scheme != "https" or not host or parsed.path:
            raise ValueError(error)
        if parsed.netloc.endswith(":") or port == 0:
            raise ValueError(error)
        if ":" in host:
            try:
                host = f"[{ipaddress.IPv6Address(host).compressed}]"
            except ValueError:
                raise ValueError(error) from None
        else:
            # WHATWG browsers interpret numeric terminal labels as IPv4,
            # including hexadecimal spellings not accepted by ipaddress.
            tail = host.rsplit(".", 1)[-1]
            if re.fullmatch(
                r"(?:[0-9]+|0x[0-9a-f]+)", tail
            ) and not re.fullmatch(r"[0-9.]+", host):
                raise ValueError(error)
            if re.fullmatch(r"[0-9.]+", host):
                try:
                    host = str(ipaddress.IPv4Address(host))
                except ValueError:
                    raise ValueError(error) from None
            elif len(host) > 253 or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                for part in host.split(".")
            ):
                raise ValueError(error)
        authority = host + (f":{port}" if port not in (None, 443) else "")
        # Reject URL-parser/browser disagreements (including numeric aliases,
        # bracket suffixes, leading-zero ports and normalized IPv6 spelling).
        allowed = (
            {authority, authority + ":443"} if port == 443 else {authority}
        )
        if parsed.netloc.lower() not in allowed:
            raise ValueError(error)
        return cls(f"https://{authority}", authority)


def validate_hosted_state(root: Path, *, read_only: bool = False) -> None:
    """Open existing compatible state only; never initialize a missing file."""
    validate_owner(root, hosted=True)
    queue = FlightQueue(root, read_only=read_only)
    try:
        store = Intelligence(
            root / ".state/intelligence.sqlite3",
            existing_only=True,
            read_only=read_only,
        )
        try:
            if queue.scope not in store.scopes():
                raise ValueError("Managed scope absent from intelligence")
        finally:
            store.close()
    finally:
        queue.close()
