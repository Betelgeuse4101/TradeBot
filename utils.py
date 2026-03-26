from typing import Union, Optional, Any, List, Dict
from decimal import Decimal, InvalidOperation, getcontext, ROUND_HALF_UP
from datetime import datetime
import re

getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP


def to_decimal(value: Union[str, int, float, Decimal, None]) -> Optional[Decimal]:
    """Безопасное преобразование в Decimal"""
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    try:
        str_value = str(value).replace(',', '.').strip()
        str_value = re.sub(r'[^\d.-]', '', str_value)
        return Decimal(str_value)
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_decimal(text: str) -> Optional[Decimal]:
    """Парсинг Decimal из текста"""
    return to_decimal(text)


def validate_positive_decimal(value: Optional[Decimal], max_value: Decimal = Decimal('999999999999')) -> bool:
    """Проверка, что значение положительное Decimal и не превышает лимит БД"""
    return value is not None and 0 < value <= max_value


def format_money(value: Union[Decimal, str, int, float, None],
                 currency: str = 'RUB') -> str:
    """Форматирование денежной суммы"""
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

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
        formatted = f"{dec_value:,.2f}".replace(',', ' ')
        return f"{formatted} {currency}"


def format_percent(value: Union[Decimal, str, int, float, None]) -> str:
    """Форматирование процента"""
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

    if dec_value > 0:
        return f"+{dec_value:.2f}%"
    elif dec_value < 0:
        return f"{dec_value:.2f}%"
    else:
        return f"0.00%"







