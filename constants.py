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

ASSET_TYPES = {
    'stock': 'Акция',
    'bond': 'Облигация',
    'etf': 'ETF',
    'currency': 'Валюта',
    'futures': 'Фьючерс',
    'other': 'Другое'
}

CURRENCIES = ['RUB', 'USD', 'EUR', 'CNY', 'KZT']

ALERT_DIRECTION_UP: str = "up"
ALERT_DIRECTION_DOWN: str = "down"

DIRECTION_ICONS: Dict[str, str] = {
    ALERT_DIRECTION_UP: "📈",
    ALERT_DIRECTION_DOWN: "📉"
}

CHANGE_ICONS: Dict[str, str] = {
    "positive": "🟢",
    "negative": "🔴"
}

ALERTS_FILE: str = "alerts.json"

LOG_DETAILED_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
LOG_SIMPLE_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT: str = '%Y-%m-%d %H:%M:%S'

LOG_SEPARATOR: str = "=" * 80

WELCOME_MESSAGE: str = """
🤖 <b>Привет! Это бот, который сделает твое инвестирование комфортным!</b>

📈 <b>Отслеживай свой портфель с удобными уведомлениями!</b>
<b>Смоделируй свой портфель из другого сервиса для отслеживания прямо в мессенджере!</b>

🎯 <b>Основные функции:</b>
• Создание нескольких портфелей
• Добавление российских и иностранных акций
• Уведомления о достижении целей
• Статистика и аналитика портфеля
• Актуальные котировки с MOEX

<b>НЕ ЗАБУДЬТЕ ВКЛЮЧИТЬ УВЕДОМЛЕНИЯ ДЛЯ ЭТОГО БОТА!</b>

👇 Используйте кнопки ниже для навигации
"""

HELP_MESSAGE: str = """
📚 <b>Помощь по боту</b>

🎯 <b>Основные разделы:</b>
• <b>📊 Мои портфели</b> - просмотр и управление портфелями
• <b>➕ Создать портфель</b> - создание нового портфеля
• <b>🔔 Мои уведомления</b> - управление уведомлениями о ценах
• <b>📈 Популярные активы</b> - Просмотр Тикеров самых популярных активов

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
"""

SYSTEM_COMMANDS = [
    "📊 Мои портфели",
    "➕ Создать портфель",
    "🔔 Мои уведомления",
    "📈 Популярные активы",
    "📋 Помощь",
    "/start",
    "/help",
    "/cancel"
]

POPULAR_TICKERS = [
    {"symbol": "SBER", "name": "Сбербанк", "type": "stock", "sector": "Финансы"},
    {"symbol": "SBERP", "name": "Сбербанк-п", "type": "stock", "sector": "Финансы"},
    {"symbol": "GAZP", "name": "Газпром", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "LKOH", "name": "Лукойл", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "GMKN", "name": "ГМК НорНикель", "type": "stock", "sector": "Металлы"},
    {"symbol": "ROSN", "name": "Роснефть", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "NVTK", "name": "НОВАТЭК", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "TATN", "name": "Татнефть", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "TATNP", "name": "Татнефть-п", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "PLZL", "name": "Полюс", "type": "stock", "sector": "Металлы"},
    {"symbol": "VTBR", "name": "ВТБ", "type": "stock", "sector": "Финансы"},
    {"symbol": "MGNT", "name": "Магнит", "type": "stock", "sector": "Ритейл"},
    {"symbol": "SNGS", "name": "Сургутнефтегаз", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "SNGSP", "name": "Сургутнефтегаз-п", "type": "stock", "sector": "Нефтегаз"},
    {"symbol": "ALRS", "name": "АЛРОСА", "type": "stock", "sector": "Металлы"},
    {"symbol": "MTLR", "name": "Мечел", "type": "stock", "sector": "Металлы"},
    {"symbol": "MTLRP", "name": "Мечел-п", "type": "stock", "sector": "Металлы"},
    {"symbol": "CHMF", "name": "Северсталь", "type": "stock", "sector": "Металлы"},
    {"symbol": "NLMK", "name": "НЛМК", "type": "stock", "sector": "Металлы"},
    {"symbol": "MAGN", "name": "ММК", "type": "stock", "sector": "Металлы"},
    {"symbol": "RUAL", "name": "РУСАЛ", "type": "stock", "sector": "Металлы"},
    {"symbol": "POLY", "name": "Полиметалл", "type": "stock", "sector": "Металлы"},
    {"symbol": "PHOR", "name": "ФосАгро", "type": "stock", "sector": "Химия"},
    {"symbol": "AKRN", "name": "Акрон", "type": "stock", "sector": "Химия"},
    {"symbol": "FIVE", "name": "X5 Group", "type": "stock", "sector": "Ритейл"},
    {"symbol": "FIXP", "name": "Fix Price", "type": "stock", "sector": "Ритейл"},
    {"symbol": "OZON", "name": "OZON", "type": "stock", "sector": "ИТ"},
    {"symbol": "YDEX", "name": "Яндекс", "type": "stock", "sector": "ИТ"},
    {"symbol": "VKCO", "name": "ВК", "type": "stock", "sector": "ИТ"},
    {"symbol": "POSI", "name": "Positive Technologies", "type": "stock", "sector": "ИТ"},
    {"symbol": "HEAD", "name": "HeadHunter", "type": "stock", "sector": "ИТ"},
    {"symbol": "CARM", "name": "Кармани", "type": "stock", "sector": "ИТ"},
    {"symbol": "SOFL", "name": "Софтлайн", "type": "stock", "sector": "ИТ"},
    {"symbol": "DIAS", "name": "Диасофт", "type": "stock", "sector": "ИТ"},
    {"symbol": "ASTRA", "name": "Группа Астра", "type": "stock", "sector": "ИТ"},
    {"symbol": "AFKS", "name": "АФК Система", "type": "stock", "sector": "Холдинги"},
    {"symbol": "MOEX", "name": "Московская биржа", "type": "stock", "sector": "Финансы"},
    {"symbol": "TCSG", "name": "ТКС Холдинг", "type": "stock", "sector": "Финансы"},
    {"symbol": "ROSB", "name": "Росбанк", "type": "stock", "sector": "Финансы"},
    {"symbol": "BSPB", "name": "Банк Санкт-Петербург", "type": "stock", "sector": "Финансы"},
    {"symbol": "RENI", "name": "Ренессанс Страхование", "type": "stock", "sector": "Финансы"},
    {"symbol": "FLOT", "name": "Совкомфлот", "type": "stock", "sector": "Транспорт"},
    {"symbol": "NMTP", "name": "НМТП", "type": "stock", "sector": "Транспорт"},
    {"symbol": "DVEC", "name": "ДВМП", "type": "stock", "sector": "Транспорт"},
    {"symbol": "AFLT", "name": "Аэрофлот", "type": "stock", "sector": "Транспорт"},
    {"symbol": "TRMK", "name": "ТМК", "type": "stock", "sector": "Металлы"},
    {"symbol": "SGZH", "name": "Сегежа", "type": "stock", "sector": "Лесная пром."},
    {"symbol": "BELU", "name": "Белуга Групп", "type": "stock", "sector": "Потребительский"},
    {"symbol": "ABIO", "name": "АРТГЕН", "type": "stock", "sector": "Биотех"},
    {"symbol": "GEMC", "name": "МКПАО ЮМГ", "type": "stock", "sector": "Потребительский"},
    {"symbol": "EUTR", "name": "ЕвроТранс", "type": "stock", "sector": "Транспорт"},
    {"symbol": "UGLD", "name": "Южуралзолото", "type": "stock", "sector": "Металлы"},
    {"symbol": "SELG", "name": "Селигдар", "type": "stock", "sector": "Металлы"},
    {"symbol": "PIKK", "name": "ПИК", "type": "stock", "sector": "Строительство"},
    {"symbol": "LSNG", "name": "ЛСР", "type": "stock", "sector": "Строительство"},
    {"symbol": "ETLN", "name": "Этал", "type": "stock", "sector": "Строительство"},
    {"symbol": "SMLT", "name": "Самолет", "type": "stock", "sector": "Строительство"},
    {"symbol": "HYDR", "name": "РусГидро", "type": "stock", "sector": "Энергетика"},
    {"symbol": "FEES", "name": "Россети", "type": "stock", "sector": "Энергетика"},
    {"symbol": "UPRO", "name": "Юнипро", "type": "stock", "sector": "Энергетика"},
    {"symbol": "OGKB", "name": "ОГК-2", "type": "stock", "sector": "Энергетика"},
    {"symbol": "IRGZ", "name": "Иркутскэнерго", "type": "stock", "sector": "Энергетика"},
    {"symbol": "MRKV", "name": "МРСК Волги", "type": "stock", "sector": "Энергетика"},
    {"symbol": "MRKP", "name": "МРСК Центра", "type": "stock", "sector": "Энергетика"},
    {"symbol": "GRNT", "name": "Группа Черкизово", "type": "stock", "sector": "Потребительский"},
    {"symbol": "RSTI", "name": "Россети", "type": "stock", "sector": "Энергетика"},
    {"symbol": "HHRU", "name": "HeadHunter Group", "type": "stock", "sector": "ИТ"},
    {"symbol": "DELI", "name": "Делимобиль", "type": "stock", "sector": "Транспорт"},
    {"symbol": "WUSH", "name": "ВУШ Холдинг", "type": "stock", "sector": "Транспорт"},
    {"symbol": "CIAN", "name": "Циан", "type": "stock", "sector": "ИТ"},
    {"symbol": "GECO", "name": "Генетико", "type": "stock", "sector": "Биотех"},
    {"symbol": "LVHK", "name": "Левенгук", "type": "stock", "sector": "Потребительский"},
    {"symbol": "MRKK", "name": "МРСК Северного Кавказа", "type": "stock", "sector": "Энергетика"},
    {"symbol": "KMEZ", "name": "КМЗ", "type": "stock", "sector": "Машиностроение"},
    {"symbol": "BLNG", "name": "Белон", "type": "stock", "sector": "Металлы"},
    {"symbol": "KROT", "name": "Красный Октябрь", "type": "stock", "sector": "Потребительский"},
    {"symbol": "LIFE", "name": "Фармсинтез", "type": "stock", "sector": "Фармацевтика"},
    {"symbol": "ELFV", "name": "ЭЛ5-Энерго", "type": "stock", "sector": "Энергетика"},
    {"symbol": "TGKA", "name": "ТГК-1", "type": "stock", "sector": "Энергетика"},
    {"symbol": "MVID", "name": "М.Видео", "type": "stock", "sector": "Ритейл"},
    {"symbol": "HNFG", "name": "Хэндерсон", "type": "stock", "sector": "Ритейл"},
    {"symbol": "VEON", "name": "VEON", "type": "stock", "sector": "Телеком"},
    {"symbol": "RTKM", "name": "Ростелеком", "type": "stock", "sector": "Телеком"},
    {"symbol": "RTKMP", "name": "Ростелеком-п", "type": "stock", "sector": "Телеком"},
    {"symbol": "MTSS", "name": "МТС", "type": "stock", "sector": "Телеком"},
    {"symbol": "CBOM", "name": "МКБ", "type": "stock", "sector": "Финансы"},
    {"symbol": "SFIN", "name": "СФИ", "type": "stock", "sector": "Финансы"},
    {"symbol": "RGSS", "name": "Росгосстрах", "type": "stock", "sector": "Финансы"},
    {"symbol": "MGKL", "name": "МГКЛ", "type": "stock", "sector": "Финансы"},
    {"symbol": "LNZL", "name": "Лензолото", "type": "stock", "sector": "Металлы"},
    {"symbol": "LNZLP", "name": "Лензолото-п", "type": "stock", "sector": "Металлы"},
    {"symbol": "CNTL", "name": "Центральная Телеграф", "type": "stock", "sector": "Телеком"},
    {"symbol": "PRMD", "name": "Промомед", "type": "stock", "sector": "Фармацевтика"},
    {"symbol": "GEMA", "name": "МКПАО ИСКЧ", "type": "stock", "sector": "ИТ"},
    {"symbol": "VSEH", "name": "ВИ.ру", "type": "stock", "sector": "Ритейл"},
    {"symbol": "ZAYM", "name": "Займер", "type": "stock", "sector": "Финансы"},
    {"symbol": "OKEY", "name": "О'КЕЙ", "type": "stock", "sector": "Ритейл"},
    {"symbol": "LENT", "name": "Лента", "type": "stock", "sector": "Ритейл"},
    {"symbol": "RBCM", "name": "РБК", "type": "stock", "sector": "Медиа"},
    {"symbol": "SPBE", "name": "СПБ Биржа", "type": "stock", "sector": "Финансы"},
]