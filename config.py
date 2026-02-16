import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    Класс конфигурации приложения.

    Загружает настройки из переменных окружения (.env файла)
    и предоставляет их для использования в других модулях.

    Attributes:
        BOT_TOKEN (str): Токен Telegram бота из переменных окружения
        ALERT_INTERVAL (int): Интервал проверки уведомлений в секундах
        POPULAR_CRYPTO (dict): Словарь популярных криптовалют
                               {название: торговый символ}
        DEFAULT_PAIRS (list): Список торговых символов для отображения по умолчанию
    """

    # Telegram Bot Token
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

    # Настройки
    ALERT_INTERVAL = int(os.getenv("ALERT_INTERVAL", 30))

    # Популярные криптовалюты
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

    # Основные пары для отображения
    DEFAULT_PAIRS = list(POPULAR_CRYPTO.values())