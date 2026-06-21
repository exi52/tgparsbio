import os

from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TG_SESSION = os.getenv("TG_SESSION", "")

_allowed = os.getenv("ALLOWED_USERS", "").replace(" ", "")
ALLOWED_USERS = {int(x) for x in _allowed.split(",") if x}

# Задержка между чтением bio. Подними, если часто прилетает FloodWait.
MIN_DELAY = float(os.getenv("MIN_DELAY", "0.3"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "0.7"))

# Сколько bio тянуть параллельно. Выше = быстрее, но больше риск FloodWait.
CONCURRENCY = int(os.getenv("CONCURRENCY", "3"))

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
    "TG_SESSION": TG_SESSION,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError("Missing env vars: " + ", ".join(_missing))
