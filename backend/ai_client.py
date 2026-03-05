"""
ai_client.py — GigaChat / Anthropic AI client for the web backend.
"""

import json
import logging
import re

from .config import AI_PROVIDER, GIGACHAT_CREDS, GIGACHAT_SCOPE, ANTHROPIC_KEY

log = logging.getLogger(__name__)

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

SYSTEM_PROMPT = """\
Ты — аналитический ИИ-ассистент МЧС для анализа журналов выездов Поисково-спасательной службы (ПСС).
Отвечай только на русском языке. Давай точные конкретные ответы: считай количество, проценты, среднее время.
Время в формате ЧЧ:ММ; разницу выражай в минутах. Если данных недостаточно — так и скажи.


{context}"""


# --- NEW: helpers for anthropic typing + safe text extraction
def _to_str(x) -> str:
    return "" if x is None else str(x)


def _anthropic_extract_text(resp) -> str:
    # resp.content is a list of ContentBlock; only blocks with type=="text" have .text [web:132]
    parts: list[str] = []
    for b in getattr(resp, "content", []) or []:
        if getattr(b, "type", None) == "text":
            parts.append(_to_str(getattr(b, "text", "")))
    return "".join(parts).strip()


def _anthropic_normalize_messages(messages: list[dict]):
    """
    Convert list[dict] into list[MessageParam]-compatible dicts.
    Using string for content is valid shorthand for one text block. [web:136]
    """
    try:
        from anthropic.types import MessageParam  # type: ignore
    except Exception:
        MessageParam = dict  # fallback for runtime; keeps behavior

    out = []
    for m in messages[-10:]:
        role = m.get("role")
        if role not in ("user", "assistant"):
            # ignore "system"/unknown; system prompt is passed via system=
            continue
        out.append({"role": role, "content": _to_str(m.get("content"))})
    return out


class AIClient:
    """Unified AI client — supports GigaChat and Anthropic."""

    def __init__(self):
        self.provider = AI_PROVIDER
        if self.provider == "gigachat":
            from gigachat import GigaChat
            from gigachat.models import Chat, Messages, MessagesRole
            self._GC = GigaChat
            self._Chat = Chat
            self._Msg = Messages
            self._Role = MessagesRole
            log.info("AI: GigaChat")
        elif self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            log.info("AI: Anthropic Claude")
        else:
            raise ValueError(f"Unknown AI_PROVIDER: {self.provider!r}")

    def ask(self, system: str, messages: list[dict]) -> str:
        """Send a chat request. Returns the assistant reply as a string."""
        if self.provider == "gigachat":
            from gigachat.models import Messages as Msg, MessagesRole as Role
            gc_msgs = []
            if system:
                gc_msgs.append(Msg(role=Role.SYSTEM, content=system))
            for m in messages[-10:]:
                role = Role.USER if m["role"] == "user" else Role.ASSISTANT
                gc_msgs.append(Msg(role=role, content=m["content"]))
            with self._GC(
                credentials=GIGACHAT_CREDS,
                scope=GIGACHAT_SCOPE,
                verify_ssl_certs=False,
            ) as gc:
                r = gc.chat(self._Chat(messages=gc_msgs))
            return r.choices[0].message.content

        elif self.provider == "anthropic":
            anthropic_messages = _anthropic_normalize_messages(messages)
            r = self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=_to_str(system),
                messages=anthropic_messages,
            )
            return _anthropic_extract_text(r)

        return ""


def parse_ai_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from AI response."""
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except Exception:
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def get_ai() -> AIClient | None:
    """Safe factory — returns None if AI is unavailable."""
    try:
        return AIClient()
    except Exception as e:
        log.warning("AI unavailable: %s", e)
        return None
