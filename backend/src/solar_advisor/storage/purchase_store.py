# src/solar_advisor/storage/purchase_store.py
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

from solar_advisor.domain.purchase import Purchase
from solar_advisor.storage.connection import connect


@runtime_checkable
class PurchaseStore(Protocol):
    def add(self, purchase: Purchase) -> Purchase: ...
    def list_all(self) -> list[Purchase]: ...
    def list_since(self, cutoff: date) -> list[Purchase]: ...
    def delete(self, purchase_id: int) -> bool: ...
    def update(self, purchase_id: int, purchase: Purchase) -> Purchase | None: ...


class SqlitePurchaseStore:
    """User-entered prepaid purchase log.

    This is the app's only write target besides telemetry, and it is NOT the
    inverter — writing purchases here does not relax the read-only-against-the-
    inverter invariant (no MQTT publish path is added). It shares the telemetry
    database file via its own connection, opened through storage.connection.

    This docstring used to claim lock contention with the collector was
    "negligible" because manual entry makes purchase writes rare. That was the
    wrong variable: the contention was never purchase *writes*, it was this
    process *reading* at all. Under the default rollback journal a reader blocks a
    writer, so ordinary history queries from the API were killing the collector's
    commits. See storage.connection.

    ISO date strings sort lexicographically in chronological order, so range
    comparisons (``purchased_at >= ?``) and ``ORDER BY`` work directly on the text.
    """

    def __init__(self, path: Path | str) -> None:
        self._conn = connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS purchases ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "purchased_at TEXT NOT NULL, "
            "rand REAL NOT NULL, "
            "units_kwh REAL NOT NULL, "
            "note TEXT)"
        )
        self._conn.commit()

    def add(self, purchase: Purchase) -> Purchase:
        cur = self._conn.execute(
            "INSERT INTO purchases (purchased_at, rand, units_kwh, note) VALUES (?, ?, ?, ?)",
            (
                purchase.purchased_at.isoformat(),
                purchase.rand,
                purchase.units_kwh,
                purchase.note,
            ),
        )
        self._conn.commit()
        return Purchase(
            id=cur.lastrowid,
            purchased_at=purchase.purchased_at,
            rand=purchase.rand,
            units_kwh=purchase.units_kwh,
            note=purchase.note,
        )

    def list_all(self) -> list[Purchase]:
        cur = self._conn.execute(
            "SELECT id, purchased_at, rand, units_kwh, note FROM purchases "
            "ORDER BY purchased_at DESC, id DESC"
        )
        return [self._row(r) for r in cur.fetchall()]

    def list_since(self, cutoff: date) -> list[Purchase]:
        cur = self._conn.execute(
            "SELECT id, purchased_at, rand, units_kwh, note FROM purchases "
            "WHERE purchased_at >= ? ORDER BY purchased_at DESC, id DESC",
            (cutoff.isoformat(),),
        )
        return [self._row(r) for r in cur.fetchall()]

    def delete(self, purchase_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def update(self, purchase_id: int, purchase: Purchase) -> Purchase | None:
        cur = self._conn.execute(
            "UPDATE purchases SET purchased_at = ?, rand = ?, units_kwh = ?, note = ? WHERE id = ?",
            (
                purchase.purchased_at.isoformat(),
                purchase.rand,
                purchase.units_kwh,
                purchase.note,
                purchase_id,
            ),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            return None
        return Purchase(
            id=purchase_id,
            purchased_at=purchase.purchased_at,
            rand=purchase.rand,
            units_kwh=purchase.units_kwh,
            note=purchase.note,
        )

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row(r: tuple[int, str, float, float, str | None]) -> Purchase:
        return Purchase(
            id=r[0],
            purchased_at=date.fromisoformat(r[1]),
            rand=r[2],
            units_kwh=r[3],
            note=r[4],
        )
