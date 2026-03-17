import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Конфигурация приложения"""

    # Telegram
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

    # Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "crypto_bot")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Settings
    ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))  # секунд
    PRICE_CACHE_TTL = int(os.getenv("PRICE_CACHE_TTL", "300"))  # 5 минут для MOEX
    MOEX_REQUEST_TIMEOUT = int(os.getenv("MOEX_REQUEST_TIMEOUT", "10"))

    # MOEX API settings
    MOEX_API_URL = "https://iss.moex.com/iss"

    # Paths
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)