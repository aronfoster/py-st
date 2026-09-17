"""Cooperative same-host process exclusion for quiesced checkpoints."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


class StateLease:
    def __init__(self, root: Path, *, exclusive: bool = False) -> None:
        # Outside .state: restore cannot replace the locked inode.
        self.fd = os.open(
            root / ".state-lease",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        try:
            fcntl.flock(
                self.fd,
                (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                | fcntl.LOCK_NB,
            )
        except BaseException:
            os.close(self.fd)
            self.fd = -1
            raise ValueError(
                "State is in use; stop all writers first"
            ) from None

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> StateLease:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
