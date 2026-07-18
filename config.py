import os
import time
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_CHAT_ID = int((os.getenv("ADMIN_CHAT_ID") or "0").strip() or "0")
WEBAPP_URL = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
WEBAPP_PORT = int((os.getenv("WEBAPP_PORT") or "5000").strip() or "5000")
REMINDER_HOUR = int((os.getenv("REMINDER_HOUR") or "8").strip() or "8")

# Часовой пояс для напоминаний / дедлайна (на хостинге сервер часто в UTC).
# Примеры: Asia/Almaty, Asia/Aqtobe, Europe/Moscow
TIMEZONE = (os.getenv("TZ") or os.getenv("TIMEZONE") or "Asia/Almaty").strip() or "Asia/Almaty"
# На Linux (Bothost) это влияет на datetime.date.today() и cron.
os.environ["TZ"] = TIMEZONE
if hasattr(time, "tzset"):
    try:
        time.tzset()
    except Exception:
        pass

# Мини-апп с персонажем временно скрыт из меню (код и webapp не удалены).
# Когда персонаж будет готов — поставь true в .env: CHARACTER_ENABLED=true
CHARACTER_ENABLED = (os.getenv("CHARACTER_ENABLED") or "false").strip().lower() in ("1", "true", "yes")

# Штраф за срыв стрика (фиксированная сумма) и контакт для оплаты.
PENALTY_AMOUNT_RUB = int(os.getenv("PENALTY_AMOUNT_RUB", "500"))
PENALTY_AMOUNT_KZT = int(os.getenv("PENALTY_AMOUNT_KZT", "3000"))
COACH_USERNAME = os.getenv("COACH_USERNAME", "jimon_000").lstrip("@")
PAYMENT_LINK = f"https://t.me/{COACH_USERNAME}"
PENALTY_TEXT = f"{PENALTY_AMOUNT_RUB} ₽ (или {PENALTY_AMOUNT_KZT} ₸)"

# ИИ-психолог (бесплатный тариф Mistral AI — ключ получить на console.mistral.ai)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
# Модель с поддержкой изображений — для проверки фото-подтверждений тренировки
MISTRAL_VISION_MODEL = os.getenv("MISTRAL_VISION_MODEL", "pixtral-12b-2409")

# Путь к SQLite. На Bothost лучше Volume, например DB_PATH=/data/no_skip.db
_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no_skip.db")
DB_PATH = (os.getenv("DB_PATH") or "").strip() or _DEFAULT_DB

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Задай переменную окружения BOT_TOKEN "
        "(локально — в .env, на Bothost — в панели Env)."
    )
