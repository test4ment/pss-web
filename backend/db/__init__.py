"""
db/ — Storage abstraction layer.

Usage:
    from db import get_storage
    storage = get_storage()        # reads USE_MEMORY env var
    storage.init()
    storage.save_departures(recs)
    rows = storage.get_departures("WHERE district = %s", ["Омский район"])
"""

import os
from .base     import BaseStorage
from .postgres import PostgresStorage
from .memory   import MemoryStorage


def _compute_stats(rows: list) -> dict:
    """Shared stats computation used by both backends."""
    from collections import Counter
    if not rows:
        return {"total": 0, "by_type": {}, "by_district": {},
                "date_min": None, "date_max": None,
                "total_victims": 0, "avg_travel_min": 0}
    by_type = Counter(r.get("incident_type") for r in rows if r.get("incident_type"))
    by_dist = Counter(r.get("district")      for r in rows if r.get("district"))
    dates   = [str(r["date"]) for r in rows if r.get("date")]
    victims = sum(int(r.get("victims") or 0) for r in rows)
    travel  = [int(r["duration_travel_min"]) for r in rows if r.get("duration_travel_min")]
    return {
        "total":          len(rows),
        "by_type":        dict(by_type.most_common()),
        "by_district":    dict(by_dist.most_common(10)),
        "date_min":       min(dates) if dates else None,
        "date_max":       max(dates) if dates else None,
        "total_victims":  victims,
        "avg_travel_min": round(sum(travel) / len(travel)) if travel else 0,
    }


# Patch _compute_stats into both backends (avoids circular imports)
from . import postgres as _pg
from . import memory   as _mem
_pg._compute_stats  = _compute_stats
_mem._compute_stats = _compute_stats


def get_storage(use_postgres: bool | None = None) -> BaseStorage:
    """
    Factory — returns the right backend.

    Priority:
      1. use_postgres argument (explicit)
      2. USE_MEMORY=1 env var  → MemoryStorage
      3. default               → PostgresStorage
    """
    if use_postgres is None:
        use_postgres = os.environ.get("USE_MEMORY", "0") != "1"

    if use_postgres:
        try:
            import psycopg2  # noqa — just check it's available
            return PostgresStorage(
                host     = os.environ.get("PG_HOST",     "localhost"),
                port     = int(os.environ.get("PG_PORT", "5432")),
                dbname   = os.environ.get("PG_DB",       "pss_db"),
                user     = os.environ.get("PG_USER",     "postgres"),
                password = os.environ.get("PG_PASSWORD", ""),
            )
        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "psycopg2 not installed — falling back to MemoryStorage"
            )

    return MemoryStorage()


__all__ = ["BaseStorage", "PostgresStorage", "MemoryStorage", "get_storage"]
