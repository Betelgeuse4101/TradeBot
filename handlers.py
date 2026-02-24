from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, Union
from decimal import Decimal

from config import Config
from bybit_client import bybit_client
from keyboards import Keyboards
from alerts_storage import AlertsStorage
from logger import get_logger, log_function_call
from utils import (
    format_price_message, format_detail_message, format_alert_message,
    format_alert_notification, get_crypto_display_name, parse_price_input,
    get_change_icon, format_price, to_decimal, format_popular_message,
    format_all_prices_message
)
from constants import (
    ALERTS_FILE, QUICK_ALERT_PERCENTS, ALERT_DIRECTION_UP, ALERT_DIRECTION_DOWN,
    DIRECTION_ICONS, WELCOME_MESSAGE, HELP_MESSAGE
)


class AlertState(StatesGroup):
    """Состояния FSM для процесса создания уведомлений."""
    waiting_for_custom_price = State()


# Создаем роутер
router = Router()

# Инициализация хранилища
alerts_storage = AlertsStorage(ALERTS_FILE)

# Глобальные переменные
bot = None  # Будет установлено при регистрации


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def safe_edit_message(message: Message, text: str,
                            reply_markup=None) -> bool:
    """
    Безопасно редактирует сообщение.

    Args:
        message: Сообщение для редактирования
        text: Новый текст
        reply_markup: Новая клавиатура

    Returns:
        bool: True если сообщение изменено
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return False
        raise e


async def save_alert(user_id: int, symbol: str, target_price: Decimal,
                     current_price: Decimal, direction: str) -> int:
    """
    Сохраняет новое уведомление.

    Args:
        user_id: ID пользователя
        symbol: Торговый символ
        target_price: Целевая цена
        current_price: Текущая цена
        direction: Направление

    Returns:
        int: ID уведомления
    """
    alert = {
        'symbol': symbol,
        'target_price': target_price,
        'current_price': current_price,
        'direction': direction,
        'user_id': user_id,
        'created_at': datetime.now()
    }

    return alerts_storage.add_alert(user_id, alert)


async def get_ticker_with_logging(symbol: str, message_obj) -> Optional[Dict]:
    """
    Получает тикер с логированием ошибок.

    Args:
        symbol: Торговый символ
        message_obj: Объект сообщения для ответа при ошибке

    Returns:
        Optional[Dict]: Данные тикера или None
    """
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await message_obj.answer(f"❌ Не удалось получить данные для {symbol}")
    return ticker


async def show_crypto_price(message: Message, symbol: str):
    """Показывает цену криптовалюты."""
    ticker = await get_ticker_with_logging(symbol, message)
    if ticker:
        await message.answer(
            format_price_message(symbol, ticker),
            reply_markup=Keyboards.get_price_actions(symbol)
        )


async def show_crypto_price_callback(callback: CallbackQuery, symbol: str):
    """Показывает цену криптовалюты в ответ на callback."""
    ticker = await get_ticker_with_logging(symbol, callback.message)
    if ticker:
        await safe_edit_message(
            callback.message,
            format_price_message(symbol, ticker),
            Keyboards.get_price_actions(symbol)
        )


# ===== ОБРАБОТЧИКИ КОМАНД =====

@router.message(Command("start"))
@log_function_call()
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    username = message.from_user.username or "без username"

    logger = get_logger('handlers')
    logger.info(f"👤 Новый пользователь: {user_id} (@{username})")

    await message.answer(WELCOME_MESSAGE, reply_markup=Keyboards.get_main_menu())


@router.message(Command("price"))
@log_function_call()
async def cmd_price(message: Message):
    """Обработчик команды /price."""
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        await message.answer("❌ Укажите символ: /price BTCUSDT")
        return

    symbol = args[1].upper()
    logger = get_logger('handlers')
    logger.info(f"💰 Пользователь {user_id} запросил цену {symbol}")

    await show_crypto_price(message, symbol)


@router.message(Command("alerts"))
@log_function_call()
async def cmd_alerts(message: Message):
    """Обработчик команды /alerts."""
    await show_my_alerts(message)


@router.message(Command("cancel"))
@log_function_call()
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel."""
    user_id = message.from_user.id
    current_state = await state.get_state()

    logger = get_logger('handlers')
    if current_state:
        logger.info(f"❌ Пользователь {user_id} отменил действие")
    else:
        logger.debug(f"❌ Пользователь {user_id} вызвал /cancel без активного состояния")

    await state.clear()
    await message.answer("❌ Действие отменено", reply_markup=Keyboards.get_main_menu())


# ===== ОБРАБОТЧИКИ ТЕКСТОВЫХ КОМАНД =====

@router.message(F.text == "💰 Котировки")
@log_function_call()
async def show_quotes(message: Message):
    """Показывает меню выбора криптовалют."""
    await message.answer(
        "📊 <b>Выберите криптовалюту:</b>\nИли используйте /price [символ] для любой пары",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "🚀 Популярные")
@log_function_call()
async def show_popular(message: Message):
    """Показывает популярные криптовалюты с объемом."""
    user_id = message.from_user.id
    logger = get_logger('handlers')
    logger.info(f"🚀 Пользователь {user_id} запросил популярные")

    await message.answer("⏳ Получаю актуальные цены...")

    symbols = list(Config.POPULAR_CRYPTO.values())[:6]
    tickers = await bybit_client.get_multiple_tickers(symbols)

    if not tickers:
        await message.answer("❌ Не удалось получить данные")
        return

    response = format_popular_message(tickers)
    await message.answer(response, reply_markup=Keyboards.get_back_button("back_to_main"))


@router.message(F.text == "🔔 Мои уведомления")
@log_function_call()
async def show_my_alerts(message: Message):
    """Показывает информацию об уведомлениях пользователя."""
    user_id = message.from_user.id
    alerts = alerts_storage.get_user_alerts(user_id)

    logger = get_logger('handlers')
    logger.info(f"🔔 Пользователь {user_id} запросил уведомления (всего: {len(alerts)})")

    if not alerts:
        response = "📭 <b>У вас нет активных уведомлений</b>\n\nНажмите '➕ Новое уведомление' чтобы создать"
        await message.answer(response, reply_markup=Keyboards.get_alerts_menu())
    else:
        await show_alerts_list(message, alerts)


@router.message(F.text == "📊 Статистика")
@log_function_call()
async def show_stats_menu(message: Message):
    """Показывает меню статистики."""
    await message.answer(
        "📈 <b>Выберите криптовалюту для подробной статистики:</b>",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "📋 Помощь")
@log_function_call()
async def show_help(message: Message):
    """Показывает справочную информацию."""
    await message.answer(HELP_MESSAGE, reply_markup=Keyboards.get_back_button("back_to_main"))


# ===== ОБРАБОТЧИКИ CALLBACK =====

@router.callback_query(F.data.startswith("crypto_"))
@log_function_call()
async def handle_crypto_selection(callback: CallbackQuery):
    """Обрабатывает выбор криптовалюты."""
    await callback.answer()

    symbol = callback.data.replace("crypto_", "")
    display_name = get_crypto_display_name(symbol)

    await safe_edit_message(
        callback.message,
        f"⏳ Получаю данные для <b>{display_name}</b>...",
        Keyboards.get_back_button("back_to_crypto")
    )

    await show_crypto_price_callback(callback, symbol)


@router.callback_query(F.data == "all_prices")
@log_function_call()
async def handle_all_prices(callback: CallbackQuery):
    """Показывает цены для всех криптовалют с объемом."""
    await callback.answer()

    await safe_edit_message(callback.message, "⏳ Получаю все котировки...")

    tickers = await bybit_client.get_multiple_tickers(Config.DEFAULT_PAIRS)

    if not tickers:
        await safe_edit_message(callback.message, "❌ Не удалось получить данные")
        return

    response = format_all_prices_message(tickers)

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_back_button("back_to_crypto")
    )


@router.callback_query(F.data.startswith("detail_"))
@log_function_call()
async def handle_detail(callback: CallbackQuery):
    """Показывает подробную информацию о криптовалюте."""
    await callback.answer()

    symbol = callback.data.replace("detail_", "")
    ticker = await bybit_client.get_ticker(symbol)

    if not ticker:
        await safe_edit_message(callback.message, "❌ Не удалось получить данные")
        return

    await safe_edit_message(
        callback.message,
        format_detail_message(symbol, ticker),
        Keyboards.get_price_actions(symbol)
    )


@router.callback_query(F.data.startswith("alert_up_percent_"))
@log_function_call()
async def handle_alert_up_percent(callback: CallbackQuery):
    """Устанавливает уведомление на рост цены."""
    await callback.answer()

    data_parts = callback.data.replace("alert_up_percent_", "").split("_")
    symbol = data_parts[0]
    percent = Decimal(data_parts[1])

    await handle_percent_alert(callback, symbol, percent, ALERT_DIRECTION_UP)


@router.callback_query(F.data.startswith("alert_down_percent_"))
@log_function_call()
async def handle_alert_down_percent(callback: CallbackQuery):
    """Устанавливает уведомление на падение цены."""
    await callback.answer()

    data_parts = callback.data.replace("alert_down_percent_", "").split("_")
    symbol = data_parts[0]
    percent = Decimal(data_parts[1])

    await handle_percent_alert(callback, symbol, percent, ALERT_DIRECTION_DOWN)


async def handle_percent_alert(callback: CallbackQuery, symbol: str,
                               percent: Decimal, direction: str):
    """
    Обрабатывает процентное уведомление.

    Args:
        callback: Callback запрос
        symbol: Торговый символ
        percent: Процент изменения
        direction: Направление
    """
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await safe_edit_message(callback.message, "❌ Не удалось получить данные")
        return

    current_price = ticker['lastPrice']

    if direction == ALERT_DIRECTION_UP:
        target_price = current_price * (1 + percent / 100)
    else:
        target_price = current_price * (1 - percent / 100)

    alert_id = await save_alert(
        user_id=callback.from_user.id,
        symbol=symbol,
        target_price=target_price,
        current_price=current_price,
        direction=direction
    )

    display_name = get_crypto_display_name(symbol)

    await safe_edit_message(
        callback.message,
        format_alert_message(alert_id, display_name, direction, target_price, current_price),
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data.startswith("alert_custom_"))
@log_function_call()
async def handle_alert_custom(callback: CallbackQuery, state: FSMContext):
    """Запрашивает ввод своей цены."""
    await callback.answer()

    symbol = callback.data.replace("alert_custom_", "")
    await state.update_data(symbol=symbol)
    await state.set_state(AlertState.waiting_for_custom_price)

    ticker = await bybit_client.get_ticker(symbol)
    display_name = get_crypto_display_name(symbol)

    if ticker:
        current_price = ticker['lastPrice']

        await safe_edit_message(
            callback.message,
            f"💰 <b>Установка своей цены для {display_name}</b>\n\n"
            f"Текущая цена: <b>${format_price(current_price)}</b>\n\n"
            f"<b>Введите желаемую цену:</b>\n"
            f"• Для роста - цена ВЫШЕ текущей\n"
            f"• Для падения - цена НИЖЕ текущей\n\n"
            f"Пример: <code>50000</code> или <code>2500.50</code>\n\n"
            f"Для отмены нажмите /cancel",
            Keyboards.get_cancel_keyboard(f"cancel_custom_{symbol}")
        )
    else:
        await safe_edit_message(callback.message, "❌ Не удалось получить текущую цену")
        await state.clear()


@router.callback_query(F.data.startswith("cancel_custom_"))
@log_function_call()
async def handle_cancel_custom(callback: CallbackQuery, state: FSMContext):
    """Отменяет установку своей цены."""
    await callback.answer()

    symbol = callback.data.replace("cancel_custom_", "")
    await state.clear()

    display_name = get_crypto_display_name(symbol)

    await safe_edit_message(
        callback.message,
        f"❌ Установка уведомления для {display_name} отменена",
        Keyboards.get_back_button(f"back_to_price_{symbol}")
    )


@router.callback_query(F.data == "new_alert")
@router.callback_query(F.data == "new_alert_from_select")
@log_function_call()
async def handle_new_alert(callback: CallbackQuery):
    """Начинает создание нового уведомления."""
    await callback.answer()

    await safe_edit_message(
        callback.message,
        "🔔 <b>Создание нового уведомления</b>\n\n👇 <b>Выберите криптовалюту:</b>",
        Keyboards.get_crypto_selection()
    )


@router.callback_query(F.data == "list_alerts")
@log_function_call()
async def handle_list_alerts(callback: CallbackQuery):
    """Показывает список всех уведомлений пользователя."""
    await callback.answer()

    user_id = callback.from_user.id
    alerts = alerts_storage.get_user_alerts(user_id)

    await show_alerts_list(callback.message, alerts, is_callback=True)


async def show_alerts_list(message_obj, alerts: list, is_callback: bool = False):
    """
    Показывает список уведомлений пользователя.

    Args:
        message_obj: Объект сообщения
        alerts: Список уведомлений
        is_callback: True если это callback запрос
    """
    if not alerts:
        response = "📭 <b>У вас нет активных уведомлений</b>"
        if is_callback:
            await safe_edit_message(message_obj, response, Keyboards.get_alerts_menu())
        else:
            await message_obj.answer(response, reply_markup=Keyboards.get_alerts_menu())
        return

    response = "<b>🔔 Ваши уведомления:</b>\n\n"

    for i, alert in enumerate(alerts[:10], 1):
        direction_icon = DIRECTION_ICONS.get(alert['direction'], "🔔")
        display_name = get_crypto_display_name(alert['symbol'])

        target_price = alert['target_price']
        current_price = alert['current_price']

        response += f"<b>#{i}. {display_name}</b>\n"
        response += f"   {direction_icon} {alert['direction']} до ${format_price(target_price)}\n"

        diff_percent = ((target_price - current_price) / current_price) * 100
        response += f"   Осталось: {abs(diff_percent):.2}%\n\n"

    if len(alerts) > 10:
        response += f"<i>И еще {len(alerts) - 10} уведомлений...</i>\n\n"

    if is_callback:
        await safe_edit_message(message_obj, response, Keyboards.get_alerts_menu())
    else:
        await message_obj.answer(response, reply_markup=Keyboards.get_alerts_menu())


@router.callback_query(F.data.startswith("delete_alert_"))
@log_function_call()
async def handle_delete_alert(callback: CallbackQuery):
    """Удаляет конкретное уведомление."""
    await callback.answer()

    try:
        alert_id = int(callback.data.replace("delete_alert_", ""))
        user_id = callback.from_user.id

        alert = alerts_storage.get_alert(user_id, alert_id)

        if alert and alerts_storage.remove_alert(user_id, alert_id):
            display_name = get_crypto_display_name(alert['symbol'])

            await safe_edit_message(
                callback.message,
                f"🗑️ <b>Уведомление #{alert_id} удалено</b>\n\n"
                f"Криптовалюта: {display_name}\n"
                f"Цель: ${format_price(alert['target_price'])}",
                Keyboards.get_back_button("back_to_alerts_list")
            )
        else:
            await callback.answer("❌ Не удалось удалить уведомление")

    except ValueError:
        await callback.answer("❌ Неверный ID уведомления")


@router.callback_query(F.data == "clear_alerts")
@log_function_call()
async def handle_clear_alerts(callback: CallbackQuery):
    """Удаляет все уведомления пользователя."""
    await callback.answer()

    user_id = callback.from_user.id

    if alerts_storage.has_user_alerts(user_id):
        alert_count = alerts_storage.remove_all_user_alerts(user_id)

        await safe_edit_message(
            callback.message,
            f"🗑️ <b>Удалено {alert_count} уведомлений</b>\n\nВсе ваши уведомления были очищены.",
            Keyboards.get_back_button("back_to_main")
        )
    else:
        await callback.answer("✅ У вас нет уведомлений")


@router.callback_query(F.data == "back_to_alerts_list")
@log_function_call()
async def handle_back_to_alerts_list(callback: CallbackQuery):
    """Возвращает к списку уведомлений."""
    await callback.answer()
    await handle_list_alerts(callback)


@router.callback_query(F.data == "alert_help")
@log_function_call()
async def handle_alert_help(callback: CallbackQuery):
    """Показывает справку по уведомлениям."""
    await callback.answer()

    help_text = f"""
❓ <b>Помощь по уведомлениям</b>

📈 <b>Типы уведомлений:</b>
• <b>Выше на X%</b> - сработает при росте на X%
• <b>Ниже на X%</b> - сработает при падении на X%
• <b>Своя цена</b> - сработает при указанной цене

💡 <b>Как работают уведомления:</b>
1. Бот отслеживает цены в реальном времени
2. Проверка происходит каждые {Config.ALERT_INTERVAL} секунд
3. При достижении цели вы получите сообщение
4. Уведомление автоматически удаляется

⚙️ <b>Управление:</b>
• Список уведомлений - "📋 Список уведомлений"
• Удалить одно - нажмите на него и выберите "🗑️ Удалить"
• Очистить все - "🗑️ Очистить все"
    """

    await safe_edit_message(
        callback.message,
        help_text,
        Keyboards.get_back_button("back_to_alerts_list")
    )


@router.callback_query(F.data.startswith("alert_"))
@log_function_call()
async def handle_alert_setup(callback: CallbackQuery):
    """Показывает меню настройки уведомления."""
    await callback.answer()

    # Игнорируем другие типы alert_
    if callback.data in ["alert_settings", "alert_help", "new_alert",
                         "new_alert_from_select", "list_alerts", "clear_alerts",
                         "back_to_alerts_list"]:
        return

    if "_percent_" in callback.data:
        return

    symbol = callback.data.replace("alert_", "")
    display_name = get_crypto_display_name(symbol)

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await safe_edit_message(callback.message, "❌ Не удалось получить данные")
        return

    current_price = ticker['lastPrice']

    response = f"""
🔔 <b>Настройка уведомления для {display_name}</b>

💰 Текущая цена: <b>${format_price(current_price)}</b>

👇 <b>Выберите тип уведомления:</b>
    """

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_alert_setup(symbol)
    )


@router.callback_query(F.data.startswith("back_to_"))
@log_function_call()
async def handle_back_button(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает кнопки "Назад"."""
    await callback.answer()

    back_to = callback.data

    if back_to == "back_to_main":
        await state.clear()
        await safe_edit_message(callback.message, "↩️ Возвращаемся в главное меню...", None)
        await callback.message.answer(
            "🏠 <b>Главное меню</b>",
            reply_markup=Keyboards.get_main_menu()
        )

    elif back_to == "back_to_crypto":
        await safe_edit_message(
            callback.message,
            "📊 <b>Выберите криптовалюту:</b>",
            Keyboards.get_crypto_selection()
        )

    elif back_to.startswith("back_to_price_"):
        symbol = back_to.replace("back_to_price_", "")
        await show_crypto_price_callback(callback, symbol)


# ===== ОБРАБОТЧИКИ FSM =====

@router.message(AlertState.waiting_for_custom_price)
@log_function_call()
async def process_custom_price(message: Message, state: FSMContext):
    """Обрабатывает введенную пользователем цену."""
    user_id = message.from_user.id

    target_price = parse_price_input(message.text)

    if target_price is None:
        await message.answer("❌ Неверный формат цены. Введите число, например: 50000 или 2500.50")
        return

    data = await state.get_data()
    symbol = data.get("symbol")

    if not symbol:
        await message.answer("❌ Ошибка данных")
        await state.clear()
        return

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await message.answer("❌ Не удалось получить текущую цену")
        await state.clear()
        return

    current_price = ticker['lastPrice']
    direction = ALERT_DIRECTION_UP if target_price > current_price else ALERT_DIRECTION_DOWN

    alert_id = await save_alert(
        user_id=message.from_user.id,
        symbol=symbol,
        target_price=target_price,
        current_price=current_price,
        direction=direction
    )

    display_name = get_crypto_display_name(symbol)

    await message.answer(
        format_alert_message(alert_id, display_name, direction, target_price, current_price),
        reply_markup=Keyboards.get_main_menu()
    )

    await state.clear()


# ===== ФОНОВАЯ ЗАДАЧА =====

async def check_alerts_task():
    """Фоновая задача для проверки уведомлений."""
    logger = get_logger('alerts_checker')
    logger.info("🚀 Запуск фоновой задачи проверки уведомлений")

    while True:
        try:
            active_users = len(alerts_storage.get_all_users())
            total_alerts = alerts_storage.get_total_alerts_count()

            logger.info(f"🔍 Проверка уведомлений... Пользователей: {active_users}, уведомлений: {total_alerts}")

            completed_alerts = []

            for user_id in alerts_storage.get_all_users():
                alerts = alerts_storage.get_user_alerts(user_id)

                for alert in alerts:
                    symbol = alert['symbol']

                    ticker = await bybit_client.get_ticker(symbol, use_cache=True)
                    if ticker:
                        current_price = ticker['lastPrice']
                        alert['current_price'] = current_price

                        target_reached = False
                        if alert['direction'] == ALERT_DIRECTION_UP and current_price >= alert['target_price']:
                            target_reached = True
                        elif alert['direction'] == ALERT_DIRECTION_DOWN and current_price <= alert['target_price']:
                            target_reached = True

                        if target_reached:
                            display_name = get_crypto_display_name(symbol)

                            try:
                                await bot.send_message(
                                    user_id,
                                    format_alert_notification(
                                        alert['id'], display_name, alert['direction'],
                                        alert['target_price'], current_price
                                    )
                                )

                                logger.info(f"📨 Отправлено уведомление #{alert['id']} пользователю {user_id}")
                                completed_alerts.append((user_id, alert['id']))

                            except Exception as e:
                                logger.error(f"❌ Ошибка отправки уведомления пользователю {user_id}: {e}")

            if completed_alerts:
                alerts_storage.cleanup_completed_alerts(completed_alerts)
                logger.info(f"🗑️ Удалено {len(completed_alerts)} выполненных уведомлений")

            await asyncio.sleep(Config.ALERT_INTERVAL)

        except Exception as e:
            logger.error(f"❌ Ошибка в задаче проверки уведомлений: {e}", exc_info=True)
            await asyncio.sleep(60)


# ===== РЕГИСТРАЦИЯ =====

def register_handlers(dp, bot_instance):
    """Регистрирует все обработчики."""
    dp.include_router(router)

    global bot
    bot = bot_instance

    asyncio.create_task(check_alerts_task())