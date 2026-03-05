"""
db/memory.py — In-memory singleton storage backend.

Uses a module-level dict as the store — one shared instance for the
entire process. Data does NOT persist between restarts.
Useful for: running without PostgreSQL, testing, development.
"""

import copy
import logging
from collections import Counter

from .base import BaseStorage

log = logging.getLogger(__name__)

# ── Singleton store ────────────────────────────────────────────────────────────
_STORE: dict[str, dict] = {
    "departures": {},   # record_id (str) → record dict
}


class MemoryStorage(BaseStorage):

    # ── Setup ──────────────────────────────────────────────────────────

    def init(self) -> None:
        log.info("MemoryStorage ready (in-RAM, no persistence)")

    # ── Write ──────────────────────────────────────────────────────────

    def save_departures(self, records: list[dict]) -> tuple[int, int]:
        store = _STORE["departures"]
        inserted = skipped = 0
        for r in records:
            key = str(r["record_id"])
            if key in store:
                skipped += 1
            else:
                store[key] = copy.deepcopy(r)
                inserted += 1
        log.info("MemoryStorage departures → inserted: %d, skipped: %d", inserted, skipped)
        return inserted, skipped

    # ── Read ───────────────────────────────────────────────────────────

    def get_departures(self, sql_where: str = "", params: list = None) -> list[dict]:
        """
        sql_where and params are ignored in memory mode.
        Filtering is intentionally simplified — extend if needed.
        """
        rows = list(_STORE["departures"].values())
        rows.sort(key=lambda r: (r.get("date") or "", r.get("time_depart") or ""),
                  reverse=True)
        return rows

    def search_departures(self, query: str, limit: int = 20) -> list[dict]:
        q = query.lower()
        results = [
            r for r in _STORE["departures"].values()
            if q in (r.get("description_raw") or "").lower()
        ]
        results.sort(key=lambda r: r.get("date") or "", reverse=True)
        return results[:limit]

    def stats(self) -> dict:
        rows = list(_STORE["departures"].values())
        return _compute_stats(rows)

    # ── Utility ────────────────────────────────────────────────────────

    @staticmethod
    def clear() -> None:
        """Wipe all data — useful in tests."""
        _STORE["departures"].clear()

    @staticmethod
    def count() -> int:
        return len(_STORE["departures"])
