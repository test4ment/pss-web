"""
МЧС ПСС — Веб-платформа аналитики
Backend: FastAPI + PostgreSQL + GigaChat
"""

import re, json, time, os, io, logging
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional

import openpyxl
import psycopg2
import psycopg2.extras
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="МЧС ПСС Аналитика", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── КОНФИГУРАЦИЯ ─────────────────────────────────────────────────────────────
AI_PROVIDER    = os.environ.get("AI_PROVIDER",         "gigachat").lower()
GIGACHAT_CREDS = os.environ.get("GIGACHAT_CREDENTIALS","")
GIGACHAT_SCOPE = os.environ.get("GIGACHAT_SCOPE",      "GIGACHAT_API_PERS")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY",   "")

PG = dict(
    host=os.environ.get("PG_HOST","localhost"), port=int(os.environ.get("PG_PORT",5432)),
    dbname=os.environ.get("PG_DB","pss_db"),   user=os.environ.get("PG_USER","postgres"),
    password=os.environ.get("PG_PASSWORD",""),
)

PSS_RE = re.compile("|".join([
    r"псс", r"поисково.спасательная\s+служба", r"поисково.спасательный\s+отряд",
    r'бу\s*[«"\']*\s*псс', r"псс\s+\w+ской\s+области",
    r"псс\s+\w+ского\s+края", r"псс\s+республики\s+\w+",
    r"каменский\s+филиал", r"дачный\s+(?:псс|филиал|пост)",
]), re.IGNORECASE)

# История чата (in-memory, на каждую сессию браузера)
chat_sessions: dict[str, list[dict]] = {}

# ─── ИИ-КЛИЕНТ ───────────────────────────────────────────────────────────────
class AI:
    """
    Единая точка переключения ИИ-провайдеров.
    По умолчанию: GigaChat.
    Для тестирования без токенов: AI_PROVIDER=anthropic в .env
    """
    def __init__(self):
        self.p = AI_PROVIDER
        if self.p == "gigachat":
            from gigachat import GigaChat
            from gigachat.models import Chat, Messages, MessagesRole
            self._GC = GigaChat; self._Chat = Chat
            self._Msg = Messages; self._Role = MessagesRole
            log.info("ИИ: GigaChat")
        elif self.p == "anthropic":
            import anthropic
            self._c = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            log.info("ИИ: Anthropic Claude")
        else:
            raise ValueError(f"Неизвестный AI_PROVIDER: {self.p!r}")

    def ask(self, system: str, messages: list[dict]) -> str:
        if self.p == "gigachat":
            from gigachat.models import Messages as Msg, MessagesRole as Role
            gc_msgs = [Msg(role=Role.SYSTEM, content=system)]
            for m in messages[-10:]:
                role = Role.USER if m["role"] == "user" else Role.ASSISTANT
                gc_msgs.append(Msg(role=role, content=m["content"]))
            with self._GC(credentials=GIGACHAT_CREDS, scope=GIGACHAT_SCOPE,
                          verify_ssl_certs=False) as gc:
                r = gc.chat(self._Chat(messages=gc_msgs))
            return r.choices[0].message.content

        elif self.p == "anthropic":
            r = self._c.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=1024,
                system=system, messages=messages[-10:],
            )
            return r.content[0].text.strip()


def get_ai():
    try:
        return AI()
    except Exception as e:
        log.warning("ИИ недоступен: %s", e)
        return None

# ─── БД ───────────────────────────────────────────────────────────────────────
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

def dbconn(): return psycopg2.connect(**PG)

def db_init():
    with dbconn() as c, c.cursor() as cur: cur.execute(SCHEMA)

def db_query(sql, params=None, fetchall=True):
    with dbconn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall() if fetchall else cur.fetchone()

# ─── ПАРСЕР EXCEL (Этап 1) ────────────────────────────────────────────────────
def fmt_t(v):
    if v is None: return None
    if isinstance(v, dtime): return v.strftime("%H:%M")
    if isinstance(v, datetime): return v.strftime("%H:%M")
    s=str(v).strip(); return s[:5] if re.match(r"\d{2}:\d{2}",s) else s

def fmt_d(v):
    if v is None: return None
    if isinstance(v, datetime): return v.strftime("%Y-%m-%d")
    return str(v).strip()[:10]

def mins(t1, t2):
    if not t1 or not t2: return None
    try:
        h1,m1=map(int,t1.split(":")); h2,m2=map(int,t2.split(":"))
        x=(h2*60+m2)-(h1*60+m1); return x if x>=0 else x+1440
    except: return None

def pss_name(text):
    m=PSS_RE.search(text)
    if not m: return ""
    return text[max(0,m.start()-15):min(len(text),m.end()+100)].strip().replace("\n"," ")

def jparse(raw):
    c=re.sub(r"^```(?:json)?\s*|\s*```$","",raw,flags=re.MULTILINE).strip()
    try: return json.loads(c)
    except:
        m=re.search(r"\{.*\}",c,re.DOTALL)
        if m:
            try: return json.loads(m.group(0))
            except: pass
    return {}


PROMPT_DEP = """\
Ты — парсер журналов выездов МЧС России.
Извлеки из текста ВСЮ возможную информацию. Верни ТОЛЬКО JSON без markdown.

ОПИСАНИЕ: {desc}
ПОДРАЗДЕЛЕНИЯ: {units}
ЦЕЛЬ: {goal}

{{"incident_type":"Пожар/ДТП/Ложная сигнализация/Поисково-спасательные работы/Техническое обслуживание/Дежурство/Учения/Заправка/Другое",
"address":"полный адрес","district":"только район",
"object_type":"тип объекта","result":"результат выезда",
"victims":0,"evacuated":0,"personnel_pss":0,"vehicles_pss":0,
"fire_vehicles":[],"incident_vehicles":[],"other_services":[],
"special_notes":"всё важное что не вошло выше"}}"""


def parse_excel_departures(file_bytes: bytes, filename: str, ai_client) -> tuple[int, int, int]:
    """Парсит журнал выездов, сохраняет в БД. Возвращает (всего, добавлено, ПСС)."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    raw = []
    for row in ws.iter_rows(values_only=True):
        if not any(row): continue
        if isinstance(row[0],str) and any(w in row[0].lower() for w in("журнал","№","запись","за период")): continue
        if not(row[0] and isinstance(row[0],(int,float)) and int(row[0])>100000): continue
        raw.append({"record_id":int(row[0]),"date":row[1],"time_notify":row[2],
                    "goal":str(row[3] or "").strip(),
                    "description":str(row[8] or ""),"units_text":str(row[10] or ""),
                    "time_depart":row[11],"time_arrive":row[12],"time_return":row[13]})

    pss=[]; [
        (r.update({"pss_unit":pss_name(r["description"]+" "+r["units_text"]),"source_file":filename}), pss.append(r))
        for r in raw if PSS_RE.search(r["description"]+" "+r["units_text"])
    ]

    SQL="""INSERT INTO pss_departures(record_id,source_file,date,time_notify,time_depart,
        time_arrive,time_return,duration_travel_min,duration_total_min,pss_unit,
        incident_type,address,district,object_type,result,victims,evacuated,
        personnel_pss,vehicles_pss,fire_vehicles,incident_vehicles,other_services,
        special_notes,description_raw,units_raw)
        VALUES(%(record_id)s,%(source_file)s,%(date)s,%(time_notify)s,%(time_depart)s,
        %(time_arrive)s,%(time_return)s,%(duration_travel_min)s,%(duration_total_min)s,
        %(pss_unit)s,%(incident_type)s,%(address)s,%(district)s,%(object_type)s,%(result)s,
        %(victims)s,%(evacuated)s,%(personnel_pss)s,%(vehicles_pss)s,
        %(fire_vehicles)s::jsonb,%(incident_vehicles)s::jsonb,%(other_services)s::jsonb,
        %(special_notes)s,%(description_raw)s,%(units_raw)s)
        ON CONFLICT(record_id) DO NOTHING"""

    added = 0
    with dbconn() as c, c.cursor() as cur:
        for i, r in enumerate(pss):
            td=fmt_t(r["time_depart"]); ta=fmt_t(r["time_arrive"]); tr=fmt_t(r["time_return"])
            ai={}
            if ai_client:
                try:
                    ai=jparse(ai_client.ask("",
                        [{"role":"user","content":PROMPT_DEP.format(
                            desc=r["description"],units=r["units_text"],goal=r["goal"]
                        )}]
                    ))
                except Exception as e:
                    log.warning("ИИ ошибка ID %d: %s", r["record_id"], e)
                if i < len(pss)-1: time.sleep(0.3)

            rec = {
                "record_id":r["record_id"],"source_file":r["source_file"],
                "date":fmt_d(r["date"]),"time_notify":fmt_t(r["time_notify"]),
                "time_depart":td,"time_arrive":ta,"time_return":tr,
                "duration_travel_min":mins(td,ta),"duration_total_min":mins(td,tr),
                "pss_unit":r["pss_unit"],
                "incident_type":ai.get("incident_type",r["goal"]),
                "address":ai.get("address",""),"district":ai.get("district",""),
                "object_type":ai.get("object_type",""),"result":ai.get("result",""),
                "victims":ai.get("victims",0) or 0,"evacuated":ai.get("evacuated",0) or 0,
                "personnel_pss":ai.get("personnel_pss",0) or 0,
                "vehicles_pss":ai.get("vehicles_pss",0) or 0,
                "fire_vehicles":json.dumps(ai.get("fire_vehicles",[]),ensure_ascii=False),
                "incident_vehicles":json.dumps(ai.get("incident_vehicles",[]),ensure_ascii=False),
                "other_services":json.dumps(ai.get("other_services",[]),ensure_ascii=False),
                "special_notes":ai.get("special_notes",""),
                "description_raw":r["description"],"units_raw":r["units_text"],
            }
            cur.execute(SQL, rec)
            added += cur.rowcount

    return len(raw), added, len(pss)


# ─── ГРАФИКИ ─────────────────────────────────────────────────────────────────
DARK="#0a0f1a"; CARD="#0e1e2e"; RED="#ff4444"; BLUE="#3a6ea5"; TXT="#ccdde8"; SUB="#7a99b8"; ACCENT="#00d4aa"

def _fig(w=10,h=5):
    fig,ax=plt.subplots(figsize=(w,h))
    fig.patch.set_facecolor(DARK); ax.set_facecolor(CARD)
    ax.tick_params(colors=SUB,labelsize=9)
    for s in ax.spines.values(): s.set_color("#1e3a5a")
    return fig,ax

def _buf(fig):
    b=io.BytesIO(); plt.savefig(b,format="png",dpi=150,bbox_inches="tight"); plt.close(fig); b.seek(0); return b

def chart_types():
    rows = db_query("""
        SELECT incident_type,
               SUM(CASE WHEN is_pss THEN 1 ELSE 0 END) AS pss,
               COUNT(*) AS total
        FROM (SELECT incident_type, TRUE as is_pss FROM pss_departures) t
        GROUP BY incident_type ORDER BY total DESC LIMIT 15""")
    if not rows: return None
    import pandas as pd
    df=pd.DataFrame(rows)
    fig,ax=_fig(10,max(4,len(df)*0.55))
    y=range(len(df))
    other=df["total"].astype(int)-df["pss"].astype(int)
    ax.barh(list(y),other,color=BLUE,label="Другие")
    ax.barh(list(y),df["pss"].astype(int),left=other,color=RED,label="ПСС")
    ax.set_yticks(list(y)); ax.set_yticklabels(df["incident_type"],color=TXT,fontsize=9)
    ax.set_xlabel("Выездов",color=SUB); ax.set_title("Типы происшествий",color=TXT,fontsize=13,pad=12)
    ax.legend(facecolor=CARD,labelcolor=TXT,edgecolor="#1e3a5a",fontsize=9)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True)); plt.tight_layout()
    return _buf(fig)

def chart_districts():
    rows = db_query("SELECT district, COUNT(*) AS cnt FROM pss_departures GROUP BY district ORDER BY cnt DESC LIMIT 12")
    if not rows: return None
    import pandas as pd
    df=pd.DataFrame(rows)
    colors=[ACCENT,BLUE,"#ff6644","#ffaa44","#aa44ff","#44aaff","#ff4488","#44ff88","#ffee44","#ff8844","#88ffee","#ee88ff"]
    fig,ax=_fig(8,6)
    _,_,autos=ax.pie(df["cnt"].astype(int),labels=df["district"],autopct="%1.0f%%",
                     colors=colors[:len(df)],startangle=140,textprops={"color":TXT,"fontsize":8})
    for a in autos: a.set_color(DARK); a.set_fontweight("bold")
    ax.set_title("По районам",color=TXT,fontsize=13,pad=16); plt.tight_layout()
    return _buf(fig)

def chart_timeline():
    rows = db_query("SELECT date, COUNT(*) AS total FROM pss_departures WHERE date IS NOT NULL GROUP BY date ORDER BY date")
    if not rows: return None
    import pandas as pd
    df=pd.DataFrame(rows); df["date"]=pd.to_datetime(df["date"]); df["total"]=df["total"].astype(int)
    fig,ax=_fig(10,4)
    ax.fill_between(df["date"],df["total"],alpha=0.25,color=RED)
    ax.plot(df["date"],df["total"],color=RED,lw=2,label="Выезды ПСС")
    ax.set_xlabel("Дата",color=SUB); ax.set_ylabel("Выездов",color=SUB)
    ax.set_title("Динамика выездов ПСС",color=TXT,fontsize=13,pad=12)
    ax.legend(facecolor=CARD,labelcolor=TXT,edgecolor="#1e3a5a",fontsize=9); plt.tight_layout()
    return _buf(fig)


# ─── КОНТЕКСТ ДЛЯ ИИ-ЧАТА ────────────────────────────────────────────────────
def build_context() -> str:
    rows = db_query("SELECT * FROM pss_departures ORDER BY date, time_depart")
    if not rows:
        return "База данных пуста. Загрузите Excel-файл журнала выездов."
    from collections import Counter
    by_type  = Counter(r["incident_type"] for r in rows if r["incident_type"])
    by_dist  = Counter(r["district"] for r in rows if r["district"])
    dates    = [r["date"] for r in rows if r["date"]]
    lines = [
        "ДАННЫЕ ЖУРНАЛА ВЫЕЗДОВ МЧС ПСС",
        f"Всего записей: {len(rows)} | Период: {min(dates)} — {max(dates)}" if dates else f"Всего записей: {len(rows)}",
        "", "Типы происшествий:"
    ] + [f"  {t}: {c}" for t,c in by_type.most_common()] + [
        "", "Районы:"
    ] + [f"  {d}: {c}" for d,c in by_dist.most_common()] + [
        "", "Все записи ПСС:"
    ]
    for r in rows:
        lines.append(
            f"  ID {r['record_id']} | {r['date']} | выезд {r['time_depart']} -> {r['time_arrive']} "
            f"| {r['incident_type']} | {r['district']} | {str(r['description_raw'] or '')[:200]}"
        )
    return "\n".join(lines)


SYSTEM_PROMPT = """\
Ты — аналитический ИИ-ассистент МЧС для анализа журналов выездов Поисково-спасательной службы (ПСС).
Отвечай только на русском языке. Давай точные конкретные ответы: считай количество, проценты, среднее время.
Время в формате ЧЧ:ММ; разницу выражай в минутах. Если данных недостаточно — так и скажи.

{context}"""

# ─── API ЭНДПОИНТЫ ───────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    try:
        db_init()
        log.info("БД инициализирована")
    except Exception as e:
        log.error("Ошибка БД: %s", e)


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Загрузка и парсинг журнала выездов."""
    if not file.filename.lower().endswith((".xlsx",".xls")):
        raise HTTPException(400, "Нужен файл .xlsx")
    content = await file.read()
    ai = get_ai()
    try:
        total, added, pss_count = parse_excel_departures(content, file.filename, ai)
        return {"total": total, "added": added, "pss_count": pss_count,
                "skipped": pss_count - added, "filename": file.filename}
    except Exception as e:
        log.exception("Ошибка парсинга")
        raise HTTPException(500, str(e))


@app.get("/api/stats")
async def get_stats():
    """Общая статистика."""
    rows = db_query("SELECT * FROM pss_departures")
    if not rows:
        return {"total": 0, "by_type": {}, "by_district": {}, "date_min": None, "date_max": None}
    from collections import Counter
    by_type = Counter(r["incident_type"] for r in rows if r["incident_type"])
    by_dist = Counter(r["district"] for r in rows if r["district"])
    dates   = [str(r["date"]) for r in rows if r["date"]]
    total_victims = sum(int(r["victims"] or 0) for r in rows)
    avg_travel = [int(r["duration_travel_min"]) for r in rows if r["duration_travel_min"]]
    return {
        "total":        len(rows),
        "by_type":      dict(by_type.most_common()),
        "by_district":  dict(by_dist.most_common(10)),
        "date_min":     min(dates) if dates else None,
        "date_max":     max(dates) if dates else None,
        "total_victims":total_victims,
        "avg_travel_min": round(sum(avg_travel)/len(avg_travel)) if avg_travel else 0,
    }


@app.get("/api/departures")
async def get_departures(limit: int = 50, offset: int = 0,
                         district: str = None, incident_type: str = None):
    """Список выездов с фильтрами."""
    sql  = "SELECT * FROM pss_departures WHERE 1=1"
    params = []
    if district:
        sql += " AND district ILIKE %s"; params.append(f"%{district}%")
    if incident_type:
        sql += " AND incident_type ILIKE %s"; params.append(f"%{incident_type}%")
    sql += " ORDER BY date DESC, time_depart DESC LIMIT %s OFFSET %s"
    params += [limit, offset]
    rows = db_query(sql, params)
    return [dict(r) for r in rows]


@app.get("/api/search")
async def search(q: str, limit: int = 20):
    """Поиск в описаниях."""
    rows = db_query(
        "SELECT * FROM pss_departures WHERE description_raw ILIKE %s ORDER BY date DESC LIMIT %s",
        [f"%{q}%", limit]
    )
    return [dict(r) for r in rows]


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Чат с ИИ-аналитиком."""
    ai = get_ai()
    if not ai:
        raise HTTPException(503, "ИИ временно недоступен. Проверьте настройки провайдера в .env")

    history = chat_sessions.setdefault(req.session_id, [])
    history.append({"role": "user", "content": req.message})
    context = build_context()
    try:
        reply = ai.ask(SYSTEM_PROMPT.format(context=context), history)
        history.append({"role": "assistant", "content": reply})
        if len(history) > 20:
            chat_sessions[req.session_id] = history[-20:]
        return {"reply": reply}
    except Exception as e:
        log.exception("Ошибка ИИ-чата")
        raise HTTPException(500, f"Ошибка ИИ: {e}")


@app.delete("/api/chat/{session_id}")
async def clear_chat(session_id: str = "default"):
    chat_sessions.pop(session_id, None)
    return {"ok": True}


@app.get("/api/chart/{chart_type}")
async def get_chart(chart_type: str):
    """Генерация графиков в PNG."""
    fn = {"types": chart_types, "districts": chart_districts, "timeline": chart_timeline}.get(chart_type)
    if not fn:
        raise HTTPException(404, "Неизвестный тип графика")
    buf = fn()
    if not buf:
        raise HTTPException(404, "Нет данных для графика")
    return StreamingResponse(buf, media_type="image/png")


# Статические файлы фронтенда
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
