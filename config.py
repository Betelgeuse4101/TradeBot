import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Класс конфигурации приложения.
    """

    # Telegram Bot Token
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

    # Настройки
    ALERT_INTERVAL = int(os.getenv("ALERT_INTERVAL", 30))

    # Популярные криптовалюты (базовый набор)
    POPULAR_CRYPTO = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "BNB": "BNBUSDT",
        "XRP": "XRPUSDT",
        "ADA": "ADAUSDT",
        "DOGE": "DOGEUSDT",
        "DOT": "DOTUSDT",
        "LINK": "LINKUSDT"
    }

    # Основные пары для отображения по умолчанию
    DEFAULT_PAIRS = list(POPULAR_CRYPTO.values())

    # Путь к файлу с пользовательскими монетами
    USER_COINS_FILE = Path("user_coins.json")