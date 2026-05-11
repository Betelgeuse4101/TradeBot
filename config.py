import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Конфигурация приложения"""

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

    # Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "moex_bot")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Telegram API
    TELEGRAM_API_TIMEOUT = int(os.getenv("TELEGRAM_API_TIMEOUT", "120"))
    TELEGRAM_CONNECT_TIMEOUT = int(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30"))
    TELEGRAM_READ_TIMEOUT = int(os.getenv("TELEGRAM_READ_TIMEOUT", "60"))
    TELEGRAM_POLLING_TIMEOUT = int(os.getenv("TELEGRAM_POLLING_TIMEOUT", "30"))
    TELEGRAM_MAX_RETRIES = int(os.getenv("TELEGRAM_MAX_RETRIES", "3"))

    # MOEX API
    MOEX_API_URL = "https://iss.moex.com/iss"
    MOEX_REQUEST_TIMEOUT = int(os.getenv("MOEX_REQUEST_TIMEOUT", "30"))
    MOEX_CONNECT_TIMEOUT = int(os.getenv("MOEX_CONNECT_TIMEOUT", "15"))
    MOEX_MAX_RETRIES = int(os.getenv("MOEX_MAX_RETRIES", "3"))
    MOEX_RETRY_DELAY = int(os.getenv("MOEX_RETRY_DELAY", "2"))
    MOEX_RATE_LIMIT_PER_MIN = int(os.getenv("MOEX_RATE_LIMIT_PER_MIN", "60"))

    # Кэширование и фоновые задачи
    PRICE_CACHE_TTL = int(os.getenv("PRICE_CACHE_TTL", "300"))
    PORTFOLIO_CACHE_TTL = int(os.getenv("PORTFOLIO_CACHE_TTL", "60"))
    PRICE_UPDATE_INTERVAL = int(os.getenv("PRICE_UPDATE_INTERVAL", "14400"))

    # Уведомления
    ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))
    ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "5"))
    ALERT_ERROR_DELAY = int(os.getenv("ALERT_ERROR_DELAY", "60"))

    # Торговые часы MOEX
    MOEX_TRADING_START_HOUR = int(os.getenv("MOEX_TRADING_START_HOUR", "10"))
    MOEX_TRADING_END_HOUR = int(os.getenv("MOEX_TRADING_END_HOUR", "18"))
    MOEX_TRADING_END_MINUTE = int(os.getenv("MOEX_TRADING_END_MINUTE", "45"))


    # Paths
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)