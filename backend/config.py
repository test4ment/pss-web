"""
config.py — Central configuration loaded from .env
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── AI ─────────────────────────────────────────────────────────────────────────
AI_PROVIDER:     str = os.environ.get("AI_PROVIDER",          "gigachat").lower()
GIGACHAT_CREDS:  str = os.environ.get("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE:  str = os.environ.get("GIGACHAT_SCOPE",       "GIGACHAT_API_PERS")
ANTHROPIC_KEY:   str = os.environ.get("ANTHROPIC_API_KEY",    "")

# ── PostgreSQL ─────────────────────────────────────────────────────────────────
PG_HOST:     str = os.environ.get("PG_HOST",     "localhost")
PG_PORT:     int = int(os.environ.get("PG_PORT", "5432"))
PG_DB:       str = os.environ.get("PG_DB",       "pss_db")
PG_USER:     str = os.environ.get("PG_USER",     "postgres")
PG_PASSWORD: str = os.environ.get("PG_PASSWORD", "")
