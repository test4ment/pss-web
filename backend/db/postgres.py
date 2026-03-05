"""
db/postgres.py — PostgreSQL storage backend using psycopg2.
"""

import json
import logging

import psycopg2
import psycopg2.extras

from .base import BaseStorage

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS pss_departures (
    record_id BIGINT PRIMARY KEY, source_file TEXT, date DATE,
    time_notify TIME, time_depart TIME, time_arrive TIME, time_return TIME,
    duration_travel_min INTEGER, duration_total_min INTEGER, pss_unit TEXT,
    incident_type TEXT, address TEXT, district TEXT, object_type TEXT,
    result TEXT, victims INTEGER DEFAULT 0, evacuated INTEGER DEFAULT 0,
    personnel_pss INTEGER DEFAULT 0, vehicles_pss INTEGER DEFAULT 0,
    fire_vehicles JSONB DEFAULT '[]', incident_vehicles JSONB DEFAULT '[]',
    other_services JSONB DEFAULT '[]', special_notes TEXT,
    description_raw TEXT, units_raw TEXT,
    loaded_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_d_date ON pss_departures(date);
CREATE INDEX IF NOT EXISTS idx_d_dist ON pss_departures(district);
CREATE INDEX IF NOT EXISTS idx_d_type ON pss_departures(incident_type);

CREATE TABLE IF NOT EXISTS pss_lessons (
    id BIGSERIAL PRIMARY KEY, source_file TEXT, date DATE,
    time_start TIME, time_end TIME, duration_min INTEGER, pss_unit TEXT,
    lesson_type TEXT, normative_name TEXT, location TEXT, instructor TEXT,
    participants_count INTEGER DEFAULT 0, result_grade TEXT,
    special_notes TEXT, description_raw TEXT,
    loaded_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_file, date, time_start, pss_unit)
);
"""

INSERT_SQL = """
    INSERT INTO pss_departures(
        record_id, source_file, date, time_notify, time_depart,
        time_arrive, time_return, duration_travel_min, duration_total_min,
        pss_unit, incident_type, address, district, object_type, result,
        victims, evacuated, personnel_pss, vehicles_pss,
        fire_vehicles, incident_vehicles, other_services,
        special_notes, description_raw, units_raw)
    VALUES(
        %(record_id)s, %(source_file)s, %(date)s, %(time_notify)s, %(time_depart)s,
        %(time_arrive)s, %(time_return)s, %(duration_travel_min)s, %(duration_total_min)s,
        %(pss_unit)s, %(incident_type)s, %(address)s, %(district)s, %(object_type)s,
        %(result)s, %(victims)s, %(evacuated)s, %(personnel_pss)s, %(vehicles_pss)s,
        %(fire_vehicles)s::jsonb, %(incident_vehicles)s::jsonb, %(other_services)s::jsonb,
        %(special_notes)s, %(description_raw)s, %(units_raw)s)
    ON CONFLICT(record_id) DO NOTHING
"""


class PostgresStorage(BaseStorage):

    def __init__(self, host: str, port: int, dbname: str, user: str, password: str):
        self._params = dict(host=host, port=port, dbname=dbname,
                            user=user, password=password)

    def _conn(self):
        return psycopg2.connect(**self._params)

    def _query(self, sql: str, params=None, fetchall: bool = True):
        with self._conn() as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params or [])
                return cur.fetchall() if fetchall else cur.fetchone()

    # ── Setup ──────────────────────────────────────────────────────────

    def init(self) -> None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(SCHEMA)
        p = self._params
        log.info("PostgreSQL ready: %s@%s:%s/%s", p["user"], p["host"], p["port"], p["dbname"])

    # ── Write ──────────────────────────────────────────────────────────

    def save_departures(self, records: list[dict]) -> tuple[int, int]:
        inserted = skipped = 0
        with self._conn() as c, c.cursor() as cur:
            for r in records:
                cur.execute(INSERT_SQL, r)
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped += 1
        log.info("pss_departures → inserted: %d, skipped: %d", inserted, skipped)
        return inserted, skipped

    # ── Read ───────────────────────────────────────────────────────────

    def get_departures(self, sql_where: str = "", params: list = None) -> list[dict]:
        sql = "SELECT * FROM pss_departures"
        if sql_where:
            sql += " " + sql_where
        return [dict(r) for r in self._query(sql, params)]

    def search_departures(self, query: str, limit: int = 20) -> list[dict]:
        rows = self._query(
            "SELECT * FROM pss_departures WHERE description_raw ILIKE %s "
            "ORDER BY date DESC LIMIT %s",
            [f"%{query}%", limit]
        )
        return [dict(r) for r in rows]
    
    def query_departures(self, sql: str, params: list | None = None) -> list[dict]:
        rows = self._query(sql, params or [])
        return [dict(r) for r in rows]   

    def stats(self) -> dict:
        rows = self._query("SELECT * FROM pss_departures")
        return _compute_stats(rows)
