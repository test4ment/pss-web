"""
main.py — FastAPI application. Routes only — no business logic here.
"""

import logging
from collections import Counter

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai_client import get_ai
from .charts    import chart_types, chart_districts, chart_timeline
from .db        import get_storage
from .parser    import parse_excel_departures

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="МЧС ПСС Аналитика", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Shared state ───────────────────────────────────────────────────────────────
storage = get_storage(use_postgres=True)   # swap to get_storage(False) for in-memory
chat_sessions: dict[str, list[dict]] = {}  # session_id → message history

SYSTEM_PROMPT = """\
Ты — аналитический ИИ-ассистент МЧС для анализа журналов выездов Поисково-спасательной службы (ПСС).
Отвечай только на русском языке. Давай точные конкретные ответы: считай количество, проценты, среднее время.
Время в формате ЧЧ:ММ; разницу выражай в минутах. Если данных недостаточно — так и скажи.

{context}"""


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    global storage
    try:
        storage.init()
        log.info("Storage initialised")
    except Exception as e:
        log.error("Storage init error: %s — falling back to MemoryStorage", e)
        from .db import MemoryStorage
        storage = MemoryStorage()
        storage.init()


# ── Helpers ────────────────────────────────────────────────────────────────────

def build_context() -> str:
    rows = storage.query_departures(
        "SELECT * FROM pss_departures ORDER BY date, time_depart"
    )
    if not rows:
        return "База данных пуста. Загрузите Excel-файл журнала выездов."
    by_type = Counter(r["incident_type"] for r in rows if r["incident_type"])
    by_dist = Counter(r["district"]      for r in rows if r["district"])
    dates   = [r["date"] for r in rows if r["date"]]
    lines = [
        "ДАННЫЕ ЖУРНАЛА ВЫЕЗДОВ МЧС ПСС",
        f"Всего записей: {len(rows)} | Период: {min(dates)} — {max(dates)}" if dates
        else f"Всего записей: {len(rows)}",
        "", "Типы происшествий:",
    ] + [f"  {t}: {c}" for t, c in by_type.most_common()] + [
        "", "Районы:",
    ] + [f"  {d}: {c}" for d, c in by_dist.most_common()] + [
        "", "Все записи ПСС:",
    ] + [
        f"  ID {r['record_id']} | {r['date']} | выезд {r['time_depart']} -> "
        f"{r['time_arrive']} | {r['incident_type']} | {r['district']} | "
        f"{str(r.get('description_raw') or '')[:200]}"
        for r in rows
    ]
    return "\n".join(lines)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Нужен файл .xlsx")
    content = await file.read()
    ai = get_ai()
    try:
        records, total, pss_count = parse_excel_departures(content, file.filename, ai)
        added, skipped = storage.save_departures(records)
        return {"total": total, "added": added, "pss_count": pss_count,
                "skipped": skipped, "filename": file.filename}
    except Exception as e:
        log.exception("Upload error")
        raise HTTPException(500, str(e))


@app.get("/api/stats")
async def get_stats():
    rows = storage.query_departures("SELECT * FROM pss_departures")
    if not rows:
        return {"total": 0, "by_type": {}, "by_district": {},
                "date_min": None, "date_max": None}
    by_type       = Counter(r["incident_type"] for r in rows if r["incident_type"])
    by_dist       = Counter(r["district"]      for r in rows if r["district"])
    dates         = [str(r["date"]) for r in rows if r["date"]]
    total_victims = sum(int(r["victims"] or 0) for r in rows)
    avg_travel    = [int(r["duration_travel_min"]) for r in rows if r["duration_travel_min"]]
    return {
        "total":          len(rows),
        "by_type":        dict(by_type.most_common()),
        "by_district":    dict(by_dist.most_common(10)),
        "date_min":       min(dates) if dates else None,
        "date_max":       max(dates) if dates else None,
        "total_victims":  total_victims,
        "avg_travel_min": round(sum(avg_travel) / len(avg_travel)) if avg_travel else 0,
    }


@app.get("/api/departures")
async def get_departures(limit: int = 50, offset: int = 0,
                         district: str = None, incident_type: str = None):
    sql    = "SELECT * FROM pss_departures WHERE 1=1"
    params = []
    if district:
        sql += " AND district ILIKE %s";      params.append(f"%{district}%")
    if incident_type:
        sql += " AND incident_type ILIKE %s"; params.append(f"%{incident_type}%")
    sql += " ORDER BY date DESC, time_depart DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    return storage.query_departures(sql, params)


@app.get("/api/search")
async def search(q: str, limit: int = 20):
    return storage.query_departures(
        "SELECT * FROM pss_departures WHERE description_raw ILIKE %s "
        "ORDER BY date DESC LIMIT %s",
        [f"%{q}%", limit]
    )


class ChatRequest(BaseModel):
    message:    str
    session_id: str = "default"

@app.post("/api/chat")
async def chat(req: ChatRequest):
    ai = get_ai()
    if not ai:
        raise HTTPException(503, "ИИ временно недоступен. Проверьте настройки провайдера в .env")
    history = chat_sessions.setdefault(req.session_id, [])
    history.append({"role": "user", "content": req.message})
    try:
        reply = ai.ask(SYSTEM_PROMPT.format(context=build_context()), history)
        history.append({"role": "assistant", "content": reply})
        if len(history) > 20:
            chat_sessions[req.session_id] = history[-20:]
        return {"reply": reply}
    except Exception as e:
        log.exception("Chat error")
        raise HTTPException(500, f"Ошибка ИИ: {e}")


@app.delete("/api/chat/{session_id}")
async def clear_chat(session_id: str = "default"):
    chat_sessions.pop(session_id, None)
    return {"ok": True}


@app.get("/api/chart/{chart_type}")
async def get_chart(chart_type: str):
    fn = {"types": chart_types, "districts": chart_districts, "timeline": chart_timeline}.get(chart_type)
    if not fn:
        raise HTTPException(404, "Неизвестный тип графика")
    buf = fn(storage)
    if not buf:
        raise HTTPException(404, "Нет данных для графика")
    return StreamingResponse(buf, media_type="image/png")


# Serve frontend
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # .../pss-web
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
