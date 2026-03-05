"""
parser.py — Excel parsing and PSS record structuring.
"""

import io
import json
import logging
import re
import time
from datetime import datetime, time as dtime

import openpyxl

from ai_client import AIClient, PROMPT_DEP, parse_ai_json

log = logging.getLogger(__name__)

PSS_RE = re.compile("|".join([
    r"псс", r"поисково.спасательная\s+служба", r"поисково.спасательный\s+отряд",
    r'бу\s*[«"\']*\s*псс', r"псс\s+\w+ской\s+области",
    r"псс\s+\w+ского\s+края", r"псс\s+республики\s+\w+",
    r"каменский\s+филиал", r"дачный\s+(?:псс|филиал|пост)",
]), re.IGNORECASE)


def _fmt_t(v) -> str | None:
    if v is None: return None
    if isinstance(v, dtime):    return v.strftime("%H:%M")
    if isinstance(v, datetime): return v.strftime("%H:%M")
    s = str(v).strip()
    return s[:5] if re.match(r"\d{2}:\d{2}", s) else s


def _fmt_d(v) -> str | None:
    if v is None: return None
    if isinstance(v, datetime): return v.strftime("%Y-%m-%d")
    return str(v).strip()[:10]


def _mins(t1, t2) -> int | None:
    if not t1 or not t2: return None
    try:
        h1, m1 = map(int, t1.split(":"))
        h2, m2 = map(int, t2.split(":"))
        x = (h2 * 60 + m2) - (h1 * 60 + m1)
        return x if x >= 0 else x + 1440
    except Exception:
        return None


def _pss_name(text: str) -> str:
    m = PSS_RE.search(text)
    if not m: return ""
    return text[max(0, m.start()-15): min(len(text), m.end()+100)].strip().replace("\n", " ")


def _j(v) -> str:
    return json.dumps(v if isinstance(v, list) else [], ensure_ascii=False)


def parse_excel_departures(
    file_bytes: bytes,
    filename: str,
    ai_client: AIClient | None,
) -> tuple[list[dict], int, int]:
    """
    Parse a departures Excel file and return structured records.

    Returns:
        (records, total_rows, pss_count)
        records — list of dicts ready to pass to storage.save_departures()
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active

    raw = []
    for row in ws.iter_rows(values_only=True):
        if not any(row): continue
        if isinstance(row[0], str) and any(
            w in row[0].lower() for w in ("журнал", "№", "запись", "за период")
        ):
            continue
        if not (row[0] and isinstance(row[0], (int, float)) and int(row[0]) > 100_000):
            continue
        raw.append({
            "record_id":  int(row[0]),
            "date":       row[1],
            "time_notify":row[2],
            "goal":       str(row[3]  or "").strip(),
            "description":str(row[8]  or ""),
            "units_text": str(row[10] or ""),
            "time_depart":row[11],
            "time_arrive":row[12],
            "time_return":row[13],
        })

    # Filter PSS records
    pss = []
    for r in raw:
        combined = r["description"] + " " + r["units_text"]
        if PSS_RE.search(combined):
            r["pss_unit"] = _pss_name(combined)
            r["source_file"] = filename
            pss.append(r)

    records = []
    for i, r in enumerate(pss):
        td = _fmt_t(r["time_depart"])
        ta = _fmt_t(r["time_arrive"])
        tr = _fmt_t(r["time_return"])

        ai = {}
        if ai_client:
            try:
                ai = parse_ai_json(ai_client.ask("", [{
                    "role": "user",
                    "content": PROMPT_DEP.format(
                        desc=r["description"],
                        units=r["units_text"],
                        goal=r["goal"],
                    )
                }]))
            except Exception as e:
                log.warning("AI error ID %d: %s", r["record_id"], e)
            if i < len(pss) - 1:
                time.sleep(0.3)

        records.append({
            "record_id":            r["record_id"],
            "source_file":          r["source_file"],
            "date":                 _fmt_d(r["date"]),
            "time_notify":          _fmt_t(r["time_notify"]),
            "time_depart":          td,
            "time_arrive":          ta,
            "time_return":          tr,
            "duration_travel_min":  _mins(td, ta),
            "duration_total_min":   _mins(td, tr),
            "pss_unit":             r["pss_unit"],
            "incident_type":        ai.get("incident_type",    r["goal"]),
            "address":              ai.get("address",          ""),
            "district":             ai.get("district",         ""),
            "object_type":          ai.get("object_type",      ""),
            "result":               ai.get("result",           ""),
            "victims":              ai.get("victims",          0) or 0,
            "evacuated":            ai.get("evacuated",        0) or 0,
            "personnel_pss":        ai.get("personnel_pss",    0) or 0,
            "vehicles_pss":         ai.get("vehicles_pss",     0) or 0,
            "fire_vehicles":        _j(ai.get("fire_vehicles",     [])),
            "incident_vehicles":    _j(ai.get("incident_vehicles", [])),
            "other_services":       _j(ai.get("other_services",    [])),
            "special_notes":        ai.get("special_notes",    ""),
            "description_raw":      r["description"],
            "units_raw":            r["units_text"],
        })

    return records, len(raw), len(pss)
