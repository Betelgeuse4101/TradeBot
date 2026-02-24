from typing import Dict, List, Tuple
from decimal import Decimal

# Константы для Bybit API
BYBIT_API_URLS: List[str] = [
    "https://api.bybit.com",
    "https://api.bytick.com",
    "https://api-demo.bybit.com"
]
BYBIT_API_TIMEOUT: int = 10
BYBIT_SPOT_CATEGORY: str = "spot"

# Константы для уведомлений
ALERT_DIRECTION_UP: str = "ВВЕРХ"
ALERT_DIRECTION_DOWN: str = "ВНИЗ"

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

# Проценты для быстрых уведомлений
QUICK_ALERT_PERCENTS: List[Decimal] = [Decimal('5'), Decimal('10')]

# Пути к файлам
ALERTS_FILE: str = "alerts.json"

# Форматы для логирования
LOG_DETAILED_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
LOG_SIMPLE_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT: str = '%Y-%m-%d %H:%M:%S'

# Разделители для логов
LOG_SEPARATOR: str = "=" * 80

# Настройки точности Decimal
DECIMAL_PRECISION = 8
DECIMAL_CONTEXT = {
    'prec': 28,
    'rounding': 'ROUND_HALF_UP'
}

# Сообщения для пользователя
WELCOME_MESSAGE: str = """
🤖 <b>Крипто-трейдинг бот с Bybit</b>

🎯 <b>Полностью кнопочный интерфейс!</b>

📈 <b>Основные функции:</b>
• Текущие цены криптовалют
• Уведомления о ценах
• Статистика за 24 часа
• Быстрый доступ к популярным парам

👇 <b>Используйте кнопки ниже для навигации</b>
"""

HELP_MESSAGE: str = """
📚 <b>Помощь по боту</b>

🎯 <b>Основные разделы:</b>
• <b>💰 Котировки</b> - выбор криптовалюты для просмотра цены
• <b>🚀 Популярные</b> - быстрый просмотр топ-криптовалют
• <b>🔔 Мои уведомления</b> - управление уведомлениями о ценах
• <b>📊 Статистика</b> - детальная статистика по парам

📈 <b>Работа с уведомлениями:</b>
1. Выберите "💰 Котировки"
2. Выберите криптовалюту
3. Нажмите "🔔 Уведомить"
4. Выберите тип уведомления
5. Укажите цену

🔄 <b>Команды:</b>
/start - Главное меню
/price [символ] - Цена любой пары (BTCUSDT, ETHUSDT и т.д.)
/alerts - Мои уведомления
/cancel - Отмена текущего действия

🤖 <b>Данные с биржи Bybit в реальном времени</b>
"""