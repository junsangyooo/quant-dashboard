"""One job at a time: an advisory file lock next to the database (data/autotrade.db-jobs.lock).

The tick skips its turn when another job holds the lock (the next tick comes in 5 minutes); a
command run by hand waits for it. The database's own write lock already keeps the ledger
consistent; this lock keeps two processes from deciding the same task is due and from
downloading the same data twice. The name falls under the 'data/autotrade.db-*' line of
.gitignore. The web API does not take it (it writes sessions and preferences only).
"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def lock_path(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + "-jobs.lock")


def ai_lock_path(db_path: Path) -> Path:
    """The AI runner's own lock: a model call may take minutes and must not hold up the tick."""
    return db_path.with_name(db_path.name + "-ai.lock")


@contextmanager
def job_lock(path: Path, wait_s: float = 0.0, poll_s: float = 0.2) -> Iterator[bool]:
    """Hold the lock for the block. Yields False (and holds nothing) when it stayed busy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(poll_s)
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
