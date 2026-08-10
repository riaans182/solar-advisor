# src/solar_advisor/storage/connection.py
from __future__ import annotations

import sqlite3
from pathlib import Path

# How long a blocked writer waits for the lock before giving up. Generous: the
# writes here are single small rows, so anything that takes seconds is a stall
# worth riding out rather than a queue worth abandoning.
BUSY_TIMEOUT_S = 5.0


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the shared database configured for MULTI-PROCESS access.

    Every store must go through this. The collector and the API are separate
    *processes* — separate containers in docker-compose, sharing one file on the
    `sa_data` volume — so sqlite3's in-process serialisation buys nothing between
    them, which is what the older per-store docstrings assumed and got wrong.

    Two settings do the work:

    ``journal_mode=WAL``
        Readers and one writer proceed concurrently. Under the default rollback
        journal a reader holds a SHARED lock that blocks the writer's EXCLUSIVE
        lock, so the API merely *reading* history was enough to fail the
        collector's next write. WAL is a persistent property of the database
        file, so it survives reopen and only has to be set once — setting it on
        every connect is harmless and keeps it true for a fresh file.

    ``timeout`` (sqlite's busy_timeout)
        Covers the case WAL does not: two *writers* colliding, telemetry from the
        collector against a purchase from the API. The loser now waits and
        retries instead of raising immediately. The default is 0, which is why
        the failure mode was an instant crash rather than a pause.

    Both are needed. WAL alone still lets concurrent writers collide, and a busy
    timeout alone would merely turn a fast crash into a slow one under the
    reader-blocks-writer case above.
    """
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=BUSY_TIMEOUT_S)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
