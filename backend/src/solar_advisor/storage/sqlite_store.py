# src/solar_advisor/storage/sqlite_store.py
from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields
from datetime import datetime, timedelta
from pathlib import Path

from solar_advisor.domain.telemetry import Telemetry

_FIELDS = [f.name for f in fields(Telemetry) if f.name != "ts"]


class SqliteTelemetryStore:
    """Wide-row telemetry store with ingest-time downsampling and retention pruning.

    Timestamp contract: ``Telemetry.ts`` must be timezone-consistent across every
    snapshot handed to a single store instance (the collector always stamps
    ``datetime.now(UTC)``). Mixing naive and tz-aware timestamps in one store would
    break both the downsample subtraction (``TypeError`` on ``snapshot.ts - last``)
    and the ISO-string range ordering used by ``query_range``/``prune_before``.
    """

    def __init__(self, path: Path | str, min_interval: timedelta = timedelta(seconds=10)) -> None:
        # check_same_thread=False so the read-only API request path (served from a
        # threadpool by uvicorn/TestClient) can call query_range on the same store the
        # async collector writes to. sqlite3 serialises access internally; writes come
        # only from the single collector thread, the API only reads.
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._min_interval = min_interval
        self._last_saved_ts: datetime | None = None
        columns = ", ".join(f"{name} REAL" for name in _FIELDS)
        self._conn.execute(f"CREATE TABLE IF NOT EXISTS telemetry (ts TEXT PRIMARY KEY, {columns})")
        self._conn.commit()

    def save(self, snapshot: Telemetry) -> bool:
        if (
            self._last_saved_ts is not None
            # An out-of-order (older) sample yields a negative delta < min_interval,
            # so it is also dropped here.
            and snapshot.ts - self._last_saved_ts < self._min_interval
        ):
            return False
        data = asdict(snapshot)
        placeholders = ", ".join(["?"] * (len(_FIELDS) + 1))
        cols = "ts, " + ", ".join(_FIELDS)
        values = [snapshot.ts.isoformat()] + [data[name] for name in _FIELDS]
        self._conn.execute(
            f"INSERT OR REPLACE INTO telemetry ({cols}) VALUES ({placeholders})", values
        )
        self._conn.commit()
        self._last_saved_ts = snapshot.ts
        return True

    def query_range(self, start: datetime, end: datetime) -> list[Telemetry]:
        cur = self._conn.execute(
            "SELECT * FROM telemetry WHERE ts >= ? AND ts <= ? ORDER BY ts",
            (start.isoformat(), end.isoformat()),
        )
        rows = cur.fetchall()
        out: list[Telemetry] = []
        for row in rows:
            ts = datetime.fromisoformat(row[0])
            kwargs = dict(zip(_FIELDS, row[1:], strict=True))
            out.append(Telemetry(ts=ts, **kwargs))
        return out

    def prune_before(self, cutoff: datetime) -> int:
        cur = self._conn.execute("DELETE FROM telemetry WHERE ts < ?", (cutoff.isoformat(),))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        """Close the underlying connection for graceful shutdown / test teardown."""
        self._conn.close()
