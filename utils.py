import re
from decimal import Decimal, InvalidOperation, getcontext, ROUND_HALF_UP
from typing import Union, Optional

getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP


def parse_number(text: str) -> Optional[Decimal]:
    """Простой и надежный парсинг чисел из текста."""
    if not text or not isinstance(text, str):
        return None

    original = text.strip()

    # Удаляем знак процента
    cleaned = original.replace('%', '').strip()

    # Запоминаем знак минуса
    is_negative = cleaned.startswith('-')
    if is_negative:
        cleaned = cleaned[1:].strip()

    # Удаляем все пробелы
    cleaned = cleaned.replace(' ', '').replace('\u00A0', '').replace('\t', '')

    if not cleaned:
        return None

    # Только цифры
    if cleaned.isdigit():
        result = Decimal(cleaned)
        return -result if is_negative else result

    # Обработка запятой как десятичного разделителя
    if ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) <= 3:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')

    # Оставляем только цифры, точку и минус
    cleaned = re.sub(r'[^0-9.-]', '', cleaned)

    # Убираем лишние точки
    dot_count = cleaned.count('.')
    if dot_count > 1:
        parts = cleaned.split('.')
        cleaned = parts[0] + '.' + ''.join(parts[1:])

    if cleaned.endswith('.'):
        cleaned = cleaned[:-1]
    if cleaned.startswith('.'):
        cleaned = '0' + cleaned

    if is_negative and not cleaned.startswith('-'):
        cleaned = '-' + cleaned

    try:
        if not cleaned or cleaned == '-' or cleaned == '.':
            return None

        result = Decimal(cleaned)

        if abs(result) > Decimal('999999999999'):
            return None

        return result
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def parse_decimal(text: str) -> Optional[Decimal]:
    """Алиас для parse_number"""
    return parse_number(text)


def to_decimal(value: Union[str, int, float, Decimal, None]) -> Optional[Decimal]:
    """Безопасное преобразование в Decimal"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except:
            return None
    if isinstance(value, str):
        return parse_number(value)
    return None


def validate_positive_decimal(value: Optional[Decimal], max_value: Decimal = Decimal('999999999999')) -> bool:
    """Проверка, что значение положительное Decimal и не превышает лимит БД"""
    if value is None:
        return False
    return value > 0 and value <= max_value


def format_number_with_spaces(number: Decimal, decimal_places: int = 2) -> str:
    """Форматирует число с разделением на разряды пробелами"""
    if number is None:
        return "0"

    quantize_str = '0.' + '0' * decimal_places
    rounded = number.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)

    integer_part = int(rounded)
    fractional_part = rounded - Decimal(integer_part)

    formatted_integer = f"{integer_part:,}".replace(',', ' ')

    if fractional_part != 0 and decimal_places > 0:
        frac_str = f"{fractional_part:.{decimal_places}f}".split('.')[1]
        frac_str = frac_str.rstrip('0')
        if frac_str:
            return f"{formatted_integer}.{frac_str}"

    return formatted_integer


def format_quantity(quantity: Decimal, max_decimals: int = 8) -> str:
    """Форматирование количества, убирая лишние нули"""
    if quantity is None:
        return "0"

    normalized = quantity.normalize()

    if normalized == normalized.to_integral():
        return f"{int(normalized):,}".replace(',', ' ')

    formatted = f"{normalized:f}".rstrip('0').rstrip('.')

    if '.' in formatted:
        int_part, frac_part = formatted.split('.')
        formatted_int = f"{int(int_part):,}".replace(',', ' ')
        return f"{formatted_int}.{frac_part}"
    else:
        return f"{int(formatted):,}".replace(',', ' ')


def format_money(value: Union[Decimal, str, int, float, None],
                 currency: str = 'RUB') -> str:
    """Форматирование денежной суммы с разделением на разряды пробелами"""
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

    if abs(dec_value) < 1 and dec_value != 0:
        decimal_places = 8
    elif abs(dec_value) < 100:
        decimal_places = 4
    else:
        decimal_places = 2

    formatted = format_number_with_spaces(dec_value, decimal_places)
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
        return "0.00%"