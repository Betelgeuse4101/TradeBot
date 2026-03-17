from typing import Union, Optional, Any, List, Dict
from decimal import Decimal, InvalidOperation, getcontext, ROUND_HALF_UP
from datetime import datetime
import re

# Настройки Decimal
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP


def to_decimal(value: Union[str, int, float, Decimal, None]) -> Optional[Decimal]:
    """Безопасное преобразование в Decimal"""
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    try:
        # Заменяем запятую на точку и убираем пробелы
        str_value = str(value).replace(',', '.').strip()
        # Убираем все кроме цифр, точки и минуса
        str_value = re.sub(r'[^\d.-]', '', str_value)
        return Decimal(str_value)
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_decimal(text: str) -> Optional[Decimal]:
    """Парсинг Decimal из текста"""
    return to_decimal(text)


def validate_positive_decimal(value: Optional[Decimal]) -> bool:
    """Проверка, что значение положительное Decimal"""
    return value is not None and value > 0


def format_decimal(value: Union[Decimal, str, int, float, None],
                   places: int = 2) -> str:
    """Форматирование Decimal с заданным количеством знаков"""
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

    # Округляем
    rounded = dec_value.quantize(Decimal(f'1.{"0" * places}'))

    # Убираем лишние нули
    formatted = f"{rounded:.{places}f}".rstrip('0').rstrip('.')

    return formatted if formatted else "0"


def format_money(value: Union[Decimal, str, int, float, None],
                 currency: str = 'RUB') -> str:
    """Форматирование денежной суммы"""
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

    # Определяем формат в зависимости от размера
    if dec_value >= 1_000_000_000:
        billions = dec_value / 1_000_000_000
        return f"{billions:.2f} млрд {currency}"
    elif dec_value >= 1_000_000:
        millions = dec_value / 1_000_000
        return f"{millions:.2f} млн {currency}"
    elif dec_value >= 1_000:
        thousands = dec_value / 1_000
        return f"{thousands:.2f} тыс {currency}"
    else:
        # Добавляем разделители тысяч
        formatted = f"{dec_value:,.2f}".replace(',', ' ')
        return f"{formatted} {currency}"


def format_percent(value: Union[Decimal, str, int, float, None]) -> str:
    """Форматирование процента"""
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

    if dec_value > 0:
        return f"🟢 +{dec_value:.2f}%"
    elif dec_value < 0:
        return f"🔴 {dec_value:.2f}%"
    else:
        return f"⚪ 0.00%"


def format_large_number(value: Union[Decimal, str, int, float, None]) -> str:
    """Форматирование больших чисел (объемы, капитализация)"""
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

    if dec_value >= 1_000_000_000_000:
        trillions = dec_value / 1_000_000_000_000
        return f"{trillions:.2f} трлн"
    elif dec_value >= 1_000_000_000:
        billions = dec_value / 1_000_000_000
        return f"{billions:.2f} млрд"
    elif dec_value >= 1_000_000:
        millions = dec_value / 1_000_000
        return f"{millions:.2f} млн"
    elif dec_value >= 1_000:
        thousands = dec_value / 1_000
        return f"{thousands:.2f} тыс"
    else:
        return str(dec_value)


def safe_iso_format(dt: datetime) -> str:
    """Безопасное форматирование datetime в ISO"""
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def calculate_change_percent(old_value: Decimal, new_value: Decimal) -> Decimal:
    """Расчет процентного изменения"""
    if old_value == 0:
        return Decimal('0')
    return ((new_value - old_value) / old_value) * 100


def group_assets_by_type(assets: List[Dict]) -> Dict[str, List[Dict]]:
    """Группировка активов по типу"""
    result = {}
    for asset in assets:
        asset_type = asset.get('asset_type', 'other')
        if asset_type not in result:
            result[asset_type] = []
        result[asset_type].append(asset)
    return result


def calculate_portfolio_diversification_score(assets: List[Dict]) -> float:
    """Расчет скора диверсификации портфеля (0-100)"""
    if not assets:
        return 0

    total_value = sum(a.get('current_value', 0) for a in assets)
    if total_value == 0:
        return 0

    # Считаем HHI (сумма квадратов долей)
    hhi = sum((a.get('current_value', 0) / total_value) ** 2 for a in assets) * 10000

    # Преобразуем HHI в скор (чем меньше HHI, тем лучше)
    # HHI < 1500 - хорошо диверсифицировано
    # HHI > 2500 - высокая концентрация
    if hhi < 1500:
        score = 100 - (hhi / 1500 * 20)  # 80-100
    elif hhi < 2500:
        score = 60 - ((hhi - 1500) / 1000 * 30)  # 30-60
    else:
        score = max(0, 30 - ((hhi - 2500) / 1000 * 30))  # 0-30

    return max(0, min(100, score))