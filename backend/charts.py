"""charts.py — Matplotlib chart generators."""

import io
import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

log = logging.getLogger(__name__)

# ── Theme ──────────────────────────────────────────────────────────────────────
DARK   = "#0a0f1a"
CARD   = "#0e1e2e"
RED    = "#ff4444"
BLUE   = "#3a6ea5"
TXT    = "#ccdde8"
SUB    = "#7a99b8"
ACCENT = "#00d4aa"


def _fig(w=10, h=5):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(DARK)
    ax.set_facecolor(CARD)
    ax.tick_params(colors=SUB, labelsize=9)
    for s in ax.spines.values():
        s.set_color("#1e3a5a")
    return fig, ax


def _buf(fig) -> io.BytesIO:
    b = io.BytesIO()
    plt.savefig(b, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    b.seek(0)
    return b


def chart_types(storage) -> io.BytesIO | None:
    rows = storage.query_departures("""
        SELECT incident_type,
               SUM(CASE WHEN is_pss THEN 1 ELSE 0 END) AS pss,
               COUNT(*) AS total
        FROM (SELECT incident_type, TRUE AS is_pss FROM pss_departures) t
        GROUP BY incident_type ORDER BY total DESC LIMIT 15
    """)
    if not rows: return None
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        fig, ax = _fig(10, max(4, len(df) * 0.55))
        y = range(len(df))
        other = df["total"].astype(int) - df["pss"].astype(int)
        ax.barh(list(y), other, color=BLUE, label="Другие")
        ax.barh(list(y), df["pss"].astype(int), left=other, color=RED, label="ПСС")
        ax.set_yticks(list(y))
        ax.set_yticklabels(df["incident_type"], color=TXT, fontsize=9)
        ax.set_xlabel("Выездов", color=SUB)
        ax.set_title("Типы происшествий", color=TXT, fontsize=13, pad=12)
        ax.legend(facecolor=CARD, labelcolor=TXT, edgecolor="#1e3a5a", fontsize=9)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        plt.tight_layout()
        return _buf(fig)
    except Exception as e:
        log.error("chart_types error: %s", e)
        return None


def chart_districts(storage) -> io.BytesIO | None:
    rows = storage.query_departures(
        "SELECT district, COUNT(*) AS cnt FROM pss_departures "
        "GROUP BY district ORDER BY cnt DESC LIMIT 12"
    )
    if not rows: return None
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        colors = [ACCENT, BLUE, "#ff6644", "#ffaa44", "#aa44ff", "#44aaff",
                  "#ff4488", "#44ff88", "#ffee44", "#ff8844", "#88ffee", "#ee88ff"]
        fig, ax = _fig(8, 6)
        _, _, autos = ax.pie(
            df["cnt"].astype(int), labels=df["district"],
            autopct="%1.0f%%", colors=colors[:len(df)],
            startangle=140, textprops={"color": TXT, "fontsize": 8}
        )
        for a in autos:
            a.set_color(DARK)
            a.set_fontweight("bold")
        ax.set_title("По районам", color=TXT, fontsize=13, pad=16)
        plt.tight_layout()
        return _buf(fig)
    except Exception as e:
        log.error("chart_districts error: %s", e)
        return None


def chart_timeline(storage) -> io.BytesIO | None:
    rows = storage.query_departures(
        "SELECT date, COUNT(*) AS total FROM pss_departures "
        "WHERE date IS NOT NULL GROUP BY date ORDER BY date"
    )
    if not rows: return None
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        df["date"]  = pd.to_datetime(df["date"])
        df["total"] = df["total"].astype(int)
        fig, ax = _fig(10, 4)
        ax.fill_between(df["date"], df["total"], alpha=0.25, color=RED)
        ax.plot(df["date"], df["total"], color=RED, lw=2, label="Выезды ПСС")
        ax.set_xlabel("Дата", color=SUB)
        ax.set_ylabel("Выездов", color=SUB)
        ax.set_title("Динамика выездов ПСС", color=TXT, fontsize=13, pad=12)
        ax.legend(facecolor=CARD, labelcolor=TXT, edgecolor="#1e3a5a", fontsize=9)
        plt.tight_layout()
        return _buf(fig)
    except Exception as e:
        log.error("chart_timeline error: %s", e)
        return None
