from typing import Union, Dict, Optional
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from config import Config
from constants import DECIMAL_PRECISION, DECIMAL_CONTEXT

# Настройка контекста Decimal
getcontext().prec = DECIMAL_CONTEXT['prec']
getcontext().rounding = DECIMAL_CONTEXT['rounding']


def to_decimal(value: Union[str, int, float, Decimal, None]) -> Optional[Decimal]:
    """
    Безопасно преобразует значение в Decimal.

    Args:
        value: Значение для преобразования

    Returns:
        Optional[Decimal]: Decimal значение или None при ошибке
    """
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    try:
        if isinstance(value, float):
            # Преобразуем float через строку для точности
            return Decimal(str(value))
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def format_decimal(value: Union[Decimal, str, int, float, None],
                   places: int = DECIMAL_PRECISION) -> str:
    """
    Форматирует Decimal значение, убирая лишние нули.

    Args:
        value: Значение для форматирования
        places: Количество знаков после запятой

    Returns:
        str: Отформатированное значение
    """
    dec_value = to_decimal(value)
    if dec_value is None:
        return "N/A"

    # Нормализуем и форматируем
    normalized = dec_value.normalize()

    if places > 0:
        # Округляем до указанного количества знаков
        quantized = normalized.quantize(Decimal(f'1.{"0" * places}'))
        formatted = f"{quantized:.{places}f}".rstrip('0').rstrip('.')
    else:
        formatted = str(int(normalized)) if normalized == normalized.to_integral() else str(normalized)

    return formatted if formatted else "0"


def format_price(price: Union[Decimal, str, int, float, None]) -> str:
    """
    Форматирует цену.

    Args:
        price: Цена для форматирования

    Returns:
        str: Отформатированная цена
    """
    return format_decimal(price, 8)


def format_volume(volume: Union[Decimal, str, int, float, None],
                  volume_type: str = "usdt") -> str:
    """
    Форматирует объем торгов с учетом единиц измерения.

    Args:
        volume: Объем для форматирования
        volume_type: "usdt" для долларов, "coins" для количества монет

    Returns:
        str: Отформатированный объем
    """
    vol = to_decimal(volume)
    if vol is None:
        return "N/A"

    if volume_type == "usdt":
        # Для долларов форматируем с сокращениями
        if vol >= 1_000_000_000:  # Миллиарды
            return f"${vol / 1_000_000_000:.2f}B"
        elif vol >= 1_000_000:  # Миллионы
            return f"${vol / 1_000_000:.2f}M"
        elif vol >= 1_000:  # Тысячи
            return f"${vol / 1_000:.2f}K"
        else:
            return f"${vol:.2f}"
    else:
        # Для монет - обычное форматирование
        if vol >= 1_000_000:
            return f"{vol / 1_000_000:.2f}M"
        elif vol >= 1_000:
            return f"{vol / 1_000:.2f}K"
        else:
            return format_decimal(vol, 4)


def get_crypto_display_name(symbol: str) -> str:
    """
    Возвращает отображаемое имя криптовалюты.

    Args:
        symbol: Торговый символ

    Returns:
        str: Отображаемое имя
    """
    for name, sym in Config.POPULAR_CRYPTO.items():
        if sym == symbol:
            return name
    return symbol


def format_price_message(symbol: str, ticker: Dict) -> str:
    """
    Форматирует сообщение с ценой криптовалюты.
    Показывает объем в USDT.

    Args:
        symbol: Торговый символ
        ticker: Данные тикера

    Returns:
        str: Отформатированное сообщение
    """
    from constants import CHANGE_ICONS

    price = to_decimal(ticker.get('lastPrice'))
    change = to_decimal(ticker.get('price24hPcnt', 0)) * 100
    high = to_decimal(ticker.get('highPrice24h'))
    low = to_decimal(ticker.get('lowPrice24h'))

    # Используем volume_usdt если есть, иначе конвертируем
    volume_usdt = to_decimal(ticker.get('volume_usdt'))
    if volume_usdt is None:
        volume_coins = to_decimal(ticker.get('volume24h'))
        volume_usdt = volume_coins * price if volume_coins and price else Decimal('0')

    change_icon = "📈" if change and change > 0 else "📉"
    change_color = CHANGE_ICONS["positive"] if change and change > 0 else CHANGE_ICONS["negative"]

    display_name = get_crypto_display_name(symbol)

    return f"""
<b>{display_name}</b>

💰 <b>Цена:</b> ${format_price(price)}
{change_icon} <b>Изменение 24ч:</b> {change_color} {change:+.2f}%
⬆️ <b>Макс 24ч:</b> ${format_price(high)}
⬇️ <b>Мин 24ч:</b> ${format_price(low)}
📊 <b>Объем 24ч:</b> {format_volume(volume_usdt, 'usdt')}

<i>Данные с биржи Bybit</i>
    """


def format_detail_message(symbol: str, ticker: Dict) -> str:
    """
    Форматирует подробное сообщение о криптовалюте.
    Показывает объем в монетах и USDT.

    Args:
        symbol: Торговый символ
        ticker: Данные тикера

    Returns:
        str: Отформатированное сообщение
    """
    price = to_decimal(ticker.get('lastPrice'))
    change = to_decimal(ticker.get('price24hPcnt', 0)) * 100
    high = to_decimal(ticker.get('highPrice24h'))
    low = to_decimal(ticker.get('lowPrice24h'))
    prev_price = to_decimal(ticker.get('prevPrice24h'))

    # Объемы
    volume_coins = to_decimal(ticker.get('volume_coins', ticker.get('volume24h')))
    volume_usdt = to_decimal(ticker.get('volume_usdt'))
    if volume_usdt is None and volume_coins and price:
        volume_usdt = volume_coins * price

    price_range = (high - low) if high and low else None

    display_name = get_crypto_display_name(symbol)

    response = f"""
📊 <b>Подробная информация {display_name}</b>

💰 <b>Цена:</b> ${format_price(price)}
📈 <b>Изменение 24ч:</b> {change:+.2f}%
⬆️ <b>Максимум 24ч:</b> ${format_price(high)}
⬇️ <b>Минимум 24ч:</b> ${format_price(low)}
📅 <b>Цена открытия:</b> ${format_price(prev_price)}
🔄 <b>Диапазон:</b> ${format_price(price_range) if price_range else "N/A"}
"""

    if volume_coins:
        response += f"\n💎 <b>Объем (монеты):</b> {format_volume(volume_coins, 'coins')}"
    if volume_usdt:
        response += f"\n💰 <b>Объем (USDT):</b> {format_volume(volume_usdt, 'usdt')}"

    response += "\n\n<i>Данные с биржи Bybit</i>"

    return response


def format_popular_message(tickers: Dict[str, Dict]) -> str:
    """
    Форматирует сообщение с популярными криптовалютами.
    Показывает цену, изменение и объем.

    Args:
        tickers: Словарь с данными тикеров

    Returns:
        str: Отформатированное сообщение
    """
    from constants import CHANGE_ICONS

    response = "<b>🚀 Популярные криптовалюты:</b>\n\n"

    for symbol, ticker in tickers.items():
        price = to_decimal(ticker.get('lastPrice'))
        change = to_decimal(ticker.get('price24hPcnt', 0)) * 100
        change_icon = get_change_icon(change)
        display_name = get_crypto_display_name(symbol)

        # Объем
        volume_usdt = to_decimal(ticker.get('volume_usdt'))
        if volume_usdt is None:
            volume_coins = to_decimal(ticker.get('volume24h'))
            volume_usdt = volume_coins * price if volume_coins and price else Decimal('0')

        response += f"<b>{display_name}</b>\n"
        response += f"   💰 ${format_price(price)} {change_icon} {change:+.2f}%\n"
        response += f"   📊 Объем: {format_volume(volume_usdt, 'usdt')}\n\n"

    return response


def format_all_prices_message(tickers: Dict[str, Dict]) -> str:
    """
    Форматирует сообщение со всеми котировками.
    Показывает цену, изменение и объем.

    Args:
        tickers: Словарь с данными тикеров

    Returns:
        str: Отформатированное сообщение
    """
    from constants import CHANGE_ICONS

    response = "<b>💰 Все котировки:</b>\n\n"

    for symbol, ticker in tickers.items():
        price = to_decimal(ticker.get('lastPrice'))
        change = to_decimal(ticker.get('price24hPcnt', 0)) * 100
        change_icon = get_change_icon(change)
        display_name = get_crypto_display_name(symbol)

        # Объем
        volume_usdt = to_decimal(ticker.get('volume_usdt'))
        if volume_usdt is None:
            volume_coins = to_decimal(ticker.get('volume24h'))
            volume_usdt = volume_coins * price if volume_coins and price else Decimal('0')

        response += f"<b>{display_name}</b>\n"
        response += f"   💰 ${format_price(price)} {change_icon} {change:+.4f}%\n"
        response += f"   📊 Объем: {format_volume(volume_usdt, 'usdt')}\n\n"

    return response


def format_alert_message(alert_id: int, display_name: str, direction: str,
                         target_price: Union[Decimal, str, float],
                         current_price: Union[Decimal, str, float]) -> str:
    """
    Форматирует сообщение о создании уведомления.

    Args:
        alert_id: ID уведомления
        display_name: Отображаемое имя криптовалюты
        direction: Направление (ВВЕРХ/ВНИЗ)
        target_price: Целевая цена
        current_price: Текущая цена

    Returns:
        str: Отформатированное сообщение
    """
    from constants import DIRECTION_ICONS

    direction_icon = DIRECTION_ICONS.get(direction, "🔔")
    target_dec = to_decimal(target_price)
    current_dec = to_decimal(current_price)

    return f"""
✅ <b>Уведомление #{alert_id} установлено!</b>

Криптовалюта: <b>{display_name}</b>
Тип: {direction_icon} <b>{direction}</b>
Текущая цена: <b>${format_price(current_dec)}</b>
Целевая цена: <b>${format_price(target_dec)}</b>

Я уведомлю вас, когда цена достигнет цели!
    """


def format_alert_notification(alert_id: int, display_name: str, direction: str,
                              target_price: Union[Decimal, str, float],
                              current_price: Union[Decimal, str, float]) -> str:
    """
    Форматирует уведомление о достижении цели.

    Args:
        alert_id: ID уведомления
        display_name: Отображаемое имя криптовалюты
        direction: Направление (ВВЕРХ/ВНИЗ)
        target_price: Целевая цена
        current_price: Текущая цена

    Returns:
        str: Отформатированное сообщение
    """
    from constants import DIRECTION_ICONS

    direction_icon = DIRECTION_ICONS.get(direction, "🔔")
    target_dec = to_decimal(target_price)
    current_dec = to_decimal(current_price)

    return f"""
🚨 <b>УВЕДОМЛЕНИЕ #{alert_id}</b>

{display_name} достиг цели!
{direction_icon} <b>{direction}</b> до ${format_price(target_dec)}
Текущая цена: <b>${format_price(current_dec)}</b>

<i>Уведомление выполнено ✅</i>
    """


def parse_price_input(price_text: str) -> Optional[Decimal]:
    """
    Парсит введенную пользователем цену.

    Args:
        price_text: Текст с ценой

    Returns:
        Optional[Decimal]: Цена или None при ошибке
    """
    try:
        # Заменяем запятую на точку и убираем пробелы
        cleaned = price_text.replace(",", ".").strip()
        return to_decimal(cleaned)
    except (ValueError, TypeError, InvalidOperation):
        return None


def get_change_icon(change_percent: Union[Decimal, float, None]) -> str:
    """
    Возвращает иконку для изменения цены.

    Args:
        change_percent: Процент изменения

    Returns:
        str: Иконка изменения
    """
    from constants import CHANGE_ICONS
    change_dec = to_decimal(change_percent)
    return CHANGE_ICONS["positive"] if change_dec and change_dec > 0 else CHANGE_ICONS["negative"]


def safe_iso_format(dt: datetime) -> str:
    """
    Безопасно форматирует datetime в ISO строку.

    Args:
        dt: Объект datetime

    Returns:
        str: ISO строка
    """
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)