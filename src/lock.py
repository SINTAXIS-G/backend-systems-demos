"""A single flock-based mutual-exclusion lock shared by the worker and the
maintenance timer, so a maintenance pass can never dispatch queued work by
accident and a live dispatch can never run mid-maintenance.

Deliberately simple: one host, one lock file. Not a distributed lock — see
README limitations.
"""
from __future__ import annotations

import contextlib
import fcntl
import os
from pathlib import Path


class LockBusy(Exception):
    pass


@contextlib.contextmanager
def exclusive(lock_path: Path, blocking: bool = False):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            raise LockBusy(f"{lock_path} is held by another process") from exc
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
