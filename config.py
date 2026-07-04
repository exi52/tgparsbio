import os

from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TG_SESSION = os.getenv("TG_SESSION", "")


def _clean_session(value):
    return value.strip().strip("\"'") if value else ""


def _numbered_sessions():
    items = []
    for idx in range(1, 21):
        value = _clean_session(os.getenv(f"TG_SESSION_{idx}", ""))
        if value:
            items.append(value)
    return items


_sessions = os.getenv("TG_SESSIONS", "").strip()
if _sessions.startswith("TG_SESSIONS="):
    _sessions = _sessions.split("=", 1)[1]
_sessions = (
    _sessions.replace("\\n", ";")
    .replace("\n", ";")
    .replace(",", ";")
    .replace("|", ";")
)
TG_SESSIONS = _numbered_sessions()
if not TG_SESSIONS:
    TG_SESSIONS = [_clean_session(s) for s in _sessions.split(";") if _clean_session(s)]
if not TG_SESSIONS and TG_SESSION:
    TG_SESSIONS = [_clean_session(TG_SESSION)]

_allowed = os.getenv("ALLOWED_USERS", "").replace(" ", "")
ALLOWED_USERS = {int(x) for x in _allowed.split(",") if x}

# Задержка между чтением bio. Подними, если часто прилетает FloodWait.
MIN_DELAY = float(os.getenv("MIN_DELAY", "0.6"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "1.4"))

# Пауза между чатами в очереди (секунды).
BATCH_MIN_DELAY = float(os.getenv("BATCH_MIN_DELAY", "45"))
BATCH_MAX_DELAY = float(os.getenv("BATCH_MAX_DELAY", "120"))


def _as_bool(value, default):
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on", "да")


# Выходить из чата после парса (только из тех, куда зашли в этом прогоне).
AUTO_LEAVE = _as_bool(os.getenv("AUTO_LEAVE"), True)

_required = {
    "API_ID": API_ID,
    "API_HASH": API_HASH,
    "BOT_TOKEN": BOT_TOKEN,
    "TG_SESSIONS": TG_SESSIONS,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError("Missing env vars: " + ", ".join(_missing))
