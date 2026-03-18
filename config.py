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
    DB_NAME = os.getenv("DB_NAME", "moex_bot")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Settings
    ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))  # секунд
    PRICE_CACHE_TTL = int(os.getenv("PRICE_CACHE_TTL", "300"))  # 5 минут
    MOEX_REQUEST_TIMEOUT = int(os.getenv("MOEX_REQUEST_TIMEOUT", "30"))  # 30 секунд
    MOEX_MAX_RETRIES = int(os.getenv("MOEX_MAX_RETRIES", "3"))
    MOEX_RETRY_DELAY = int(os.getenv("MOEX_RETRY_DELAY", "2"))

    # Telegram API settings - УВЕЛИЧЕННЫЕ ТАЙМАУТЫ
    TELEGRAM_API_TIMEOUT = int(os.getenv("TELEGRAM_API_TIMEOUT", "120"))  # Увеличено с 60 до 120
    TELEGRAM_CONNECT_TIMEOUT = int(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30"))  # Увеличено с 20 до 30
    TELEGRAM_READ_TIMEOUT = int(os.getenv("TELEGRAM_READ_TIMEOUT", "60"))  # Увеличено с 30 до 60
    TELEGRAM_POLLING_TIMEOUT = int(os.getenv("TELEGRAM_POLLING_TIMEOUT", "30"))  # Таймаут для long polling

    # MOEX API settings
    MOEX_API_URL = "https://iss.moex.com/iss"

    # Торговые часы MOEX (МСК)
    MOEX_TRADING_START_HOUR = int(os.getenv("MOEX_TRADING_START_HOUR", "10"))
    MOEX_TRADING_END_HOUR = int(os.getenv("MOEX_TRADING_END_HOUR", "18"))
    MOEX_TRADING_END_MINUTE = int(os.getenv("MOEX_TRADING_END_MINUTE", "45"))

    # Периоды обновления данных
    PORTFOLIO_UPDATE_INTERVAL = int(os.getenv("PORTFOLIO_UPDATE_INTERVAL", "3600"))  # 1 час
    MARKET_CHECK_INTERVAL = int(os.getenv("MARKET_CHECK_INTERVAL", "300"))  # 5 минут
    BATCH_REQUEST_DELAY = int(os.getenv("BATCH_REQUEST_DELAY", "1"))  # 1 секунда между запросами

    # Paths
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)