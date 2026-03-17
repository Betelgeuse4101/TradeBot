from typing import Dict, List
from decimal import Decimal

# Константы для MOEX API
MOEX_ENGINES = {
    'stock': 'stock',  # фондовый рынок
    'bond': 'stock',   # облигации тоже на фондовом
    'etf': 'stock',    # ETF на фондовом
    'currency': 'currency',  # валютный рынок
    'futures': 'futures'     # срочный рынок
}

MOEX_MARKETS = {
    'stock': 'shares',      # акции
    'bond': 'bonds',        # облигации
    'etf': 'etf',           # ETF
    'currency': 'selt',     # валютный рынок
    'futures': 'forts'      # фьючерсы
}

# Типы активов
ASSET_TYPES = {
    'stock': 'Акция',
    'bond': 'Облигация',
    'etf': 'ETF',
    'currency': 'Валюта',
    'futures': 'Фьючерс',
    'other': 'Другое'
}

# Валюты
CURRENCIES = ['RUB', 'USD', 'EUR', 'CNY', 'KZT']

# Направления уведомлений
ALERT_DIRECTION_UP: str = "up"
ALERT_DIRECTION_DOWN: str = "down"

# Эмодзи для разных типов уведомлений
DIRECTION_ICONS: Dict[str, str] = {
    ALERT_DIRECTION_UP: "📈",
    ALERT_DIRECTION_DOWN: "📉"
}

# Цветовые индикаторы для изменений цен
CHANGE_ICONS: Dict[str, str] = {
    "positive": "🟢",
    "negative": "🔴"
}

# Пути к файлам
ALERTS_FILE: str = "alerts.json"

# Форматы для логирования
LOG_DETAILED_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
LOG_SIMPLE_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT: str = '%Y-%m-%d %H:%M:%S'

# Разделители для логов
LOG_SEPARATOR: str = "=" * 80

# Сообщения для пользователя
WELCOME_MESSAGE: str = """
🤖 <b>Инвестиционный бот с MOEX</b>

📈 <b>Отслеживайте свой портфель на Московской бирже!</b>

🎯 <b>Основные функции:</b>
• Создание нескольких портфелей
• Добавление российских и иностранных акций
• Уведомления о достижении целей
• Статистика и аналитика портфеля
• Актуальные котировки с MOEX

📊 <b>Поддерживаемые активы:</b>
• Акции (SBER, GAZP, YNDX и др.)
• Облигации
• ETF (FXUS, FXIT и др.)
• Валюты (USD/RUB, EUR/RUB)

👇 <b>Используйте кнопки ниже для навигации</b>
"""

HELP_MESSAGE: str = """
📚 <b>Помощь по боту</b>

🎯 <b>Основные разделы:</b>
• <b>📊 Мои портфели</b> - просмотр и управление портфелями
• <b>➕ Создать портфель</b> - создание нового портфеля
• <b>🔔 Мои уведомления</b> - управление уведомлениями о ценах

📈 <b>Работа с портфелем:</b>
1. Создайте портфель
2. Добавьте активы (тикер, количество, цена покупки)
3. Отслеживайте текущую стоимость и прибыль
4. Устанавливайте уведомления на цели

🔔 <b>Типы уведомлений:</b>
• По цене актива (выше/ниже заданной)
• По проценту изменения (выше/ниже на X%)
• По стоимости портфеля

📝 <b>Команды:</b>
/start - Главное меню
/cancel - Отмена текущего действия

📊 <b>Данные с Московской биржи в реальном времени</b>
"""