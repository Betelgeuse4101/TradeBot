from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest

from config import Config
from bybit_client import bybit_client
from keyboards import Keyboards
from alerts_storage import AlertsStorage
from logger import get_logger, log_function_call

# Получаем логгер для handlers
logger = get_logger('handlers')


class AlertState(StatesGroup):
    """
    Состояния FSM для процесса создания уведомлений.
    """
    waiting_for_custom_price = State()


# Создаем роутер для регистрации обработчиков
router = Router()

# Инициализация хранилища уведомлений
alerts_storage = AlertsStorage("alerts.json")

# Глобальные переменные
bot = None  # Будет установлено при регистрации


# Вспомогательная функция для безопасного редактирования сообщений
async def safe_edit_message(message, text, reply_markup=None):
    """
    Безопасно редактирует сообщение, игнорируя ошибку "message is not modified".
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        logger.debug("✏️ Сообщение отредактировано")
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.debug("📝 Сообщение не изменилось, пропускаем")
            return False
        else:
            logger.error(f"❌ Ошибка при редактировании сообщения: {e}")
            raise e


# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ =====

@router.message(Command("start"))
@log_function_call()
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    """
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    logger.info(f"👤 Новый пользователь: {user_id} (@{username})")

    welcome_text = """
🤖 <b>Крипто-трейдинг бот с Bybit</b>

🎯 <b>Полностью кнопочный интерфейс!</b>

📈 <b>Основные функции:</b>
• Текущие цены криптовалют
• Уведомления о ценах
• Статистика за 24 часа
• Быстрый доступ к популярным парам

👇 <b>Используйте кнопки ниже для навигации</b>
    """

    await message.answer(
        welcome_text,
        reply_markup=Keyboards.get_main_menu()
    )


@router.message(F.text == "💰 Котировки")
@log_function_call()
async def show_quotes(message: Message):
    """
    Показывает меню выбора криптовалют для просмотра котировок.
    """
    user_id = message.from_user.id
    logger.info(f"💰 Пользователь {user_id} открыл меню котировок")

    await message.answer(
        "📊 <b>Выберите криптовалюту:</b>\n"
        "Или используйте /price [символ] для любой пары",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "🚀 Популярные")
@log_function_call()
async def show_popular(message: Message):
    """
    Показывает текущие цены на популярные криптовалюты.
    """
    user_id = message.from_user.id
    logger.info(f"🚀 Пользователь {user_id} запросил популярные криптовалюты")

    await message.answer("⏳ Получаю актуальные цены...")

    symbols = list(Config.POPULAR_CRYPTO.values())[:6]
    tickers = await bybit_client.get_multiple_tickers(symbols)

    if not tickers:
        logger.error(f"❌ Не удалось получить данные для пользователя {user_id}")
        await message.answer("❌ Не удалось получить данные")
        return

    response = "<b>🚀 Популярные криптовалюты:</b>\n\n"

    for symbol, ticker in tickers.items():
        price = float(ticker['lastPrice'])
        # Форматируем цену
        price_str = f"{int(price)}" if price.is_integer() else f"{price:.8f}".rstrip('0').rstrip('.')

        change = float(ticker['price24hPcnt']) * 100
        change_icon = "🟢" if change > 0 else "🔴"

        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

        response += f"<b>{short_name}</b> (${price_str}) {change_icon} {change:+.4f}%\n"

    await message.answer(
        response,
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.message(F.text == "🔔 Мои уведомления")
@log_function_call()
async def show_my_alerts(message: Message):
    """
    Показывает информацию об уведомлениях пользователя.
    """
    user_id = message.from_user.id
    alerts = alerts_storage.get_user_alerts(user_id)

    logger.info(f"🔔 Пользователь {user_id} запросил уведомления (всего: {len(alerts)})")

    if not alerts:
        response = "📭 <b>У вас нет активных уведомлений</b>\n\n"
        response += "Нажмите '➕ Новое уведомление' чтобы создать"

        await message.answer(
            response,
            reply_markup=Keyboards.get_alerts_menu()
        )
    else:
        response = f"<b>🔔 У вас {len(alerts)} уведомлений</b>\n\n"

        # Группируем по крипте
        crypto_counts = {}
        for alert in alerts:
            crypto_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == alert['symbol']]
            display_name = crypto_name[0] if crypto_name else alert['symbol']

            if display_name not in crypto_counts:
                crypto_counts[display_name] = {'up': 0, 'down': 0}

            if alert['direction'] == 'ВВЕРХ':
                crypto_counts[display_name]['up'] += 1
            else:
                crypto_counts[display_name]['down'] += 1

        for crypto, counts in crypto_counts.items():
            total = counts['up'] + counts['down']
            response += f"<b>{crypto}</b>: {total} увед.\n"
            if counts['up']:
                response += f"   📈 Вверх: {counts['up']} увед.\n"
            if counts['down']:
                response += f"   📉 Вниз: {counts['down']} увед.\n"

        response += "\n👇 <b>Используйте кнопки для управления:</b>"

        await message.answer(
            response,
            reply_markup=Keyboards.get_alerts_menu()
        )


@router.message(F.text == "📊 Статистика")
@log_function_call()
async def show_stats_menu(message: Message):
    """
    Показывает меню выбора криптовалюты для просмотра статистики.
    """
    user_id = message.from_user.id
    logger.info(f"📊 Пользователь {user_id} открыл меню статистики")

    await message.answer(
        "📈 <b>Выберите криптовалюту для подробной статистики:</b>",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "📋 Помощь")
@log_function_call()
async def show_help(message: Message):
    """
    Показывает справочную информацию по использованию бота.
    """
    user_id = message.from_user.id
    logger.info(f"📋 Пользователь {user_id} запросил помощь")

    help_text = """
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

    await message.answer(
        help_text,
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.message(Command("price"))
@log_function_call()
async def cmd_price(message: Message):
    """
    Обработчик команды /price для получения цены по символу.
    """
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        logger.warning(f"⚠️ Пользователь {user_id} ввел /price без символа")
        await message.answer("❌ Укажите символ: /price BTCUSDT")
        return

    symbol = args[1].upper()
    logger.info(f"💰 Пользователь {user_id} запросил цену {symbol} через команду")
    await show_crypto_price(message, symbol)


@router.message(Command("alerts"))
@log_function_call()
async def cmd_alerts(message: Message):
    """
    Обработчик команды /alerts для показа уведомлений.
    """
    user_id = message.from_user.id
    logger.info(f"🔔 Пользователь {user_id} вызвал /alerts")
    await show_my_alerts(message)


@router.message(Command("cancel"))
@log_function_call()
async def cmd_cancel(message: Message, state: FSMContext):
    """
    Обработчик команды /cancel для отмены текущего действия.
    """
    user_id = message.from_user.id
    current_state = await state.get_state()

    if current_state:
        logger.info(f"❌ Пользователь {user_id} отменил действие (состояние: {current_state})")
    else:
        logger.debug(f"❌ Пользователь {user_id} вызвал /cancel без активного состояния")

    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=Keyboards.get_main_menu()
    )


# ===== ОБРАБОТЧИКИ CALLBACK ДЛЯ КРИПТОВАЛЮТ =====

@router.callback_query(F.data.startswith("crypto_"))
@log_function_call()
async def handle_crypto_selection(callback: CallbackQuery):
    """
    Обрабатывает выбор криптовалюты из списка.
    """
    user_id = callback.from_user.id
    await callback.answer()

    symbol = callback.data.replace("crypto_", "")
    logger.info(f"👤 Пользователь {user_id} выбрал криптовалюту {symbol}")

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    await safe_edit_message(
        callback.message,
        f"⏳ Получаю данные для <b>{display_name}</b>...",
        Keyboards.get_back_button("back_to_crypto")
    )

    await show_crypto_price_callback(callback, symbol)


@router.callback_query(F.data == "all_prices")
@log_function_call()
async def handle_all_prices(callback: CallbackQuery):
    """
    Показывает цены для всех доступных криптовалют.
    """
    user_id = callback.from_user.id
    await callback.answer()

    logger.info(f"👤 Пользователь {user_id} запросил все котировки")

    await safe_edit_message(
        callback.message,
        "⏳ Получаю все котировки..."
    )

    tickers = await bybit_client.get_multiple_tickers(Config.DEFAULT_PAIRS)

    if not tickers:
        logger.error(f"❌ Не удалось получить данные для пользователя {user_id}")
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    response = "<b>💰 Все котировки:</b>\n\n"

    for symbol, ticker in tickers.items():
        price = float(ticker['lastPrice'])
        # Форматируем цену
        price_str = f"{int(price)}" if price.is_integer() else f"{price:.8f}".rstrip('0').rstrip('.')

        change = float(ticker['price24hPcnt']) * 100
        change_icon = "🟢" if change > 0 else "🔴"

        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
        display_name = short_name[0] if short_name else symbol

        response += f"<b>{display_name}</b>: ${price_str} {change_icon} {change:+.4f}%\n"

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_back_button("back_to_crypto")
    )


@router.callback_query(F.data.startswith("detail_"))
@log_function_call()
async def handle_detail(callback: CallbackQuery):
    """
    Показывает подробную информацию о выбранной криптовалюте.
    """
    user_id = callback.from_user.id
    await callback.answer()

    symbol = callback.data.replace("detail_", "")
    logger.info(f"👤 Пользователь {user_id} запросил детали для {symbol}")

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        logger.error(f"❌ Не удалось получить данные для {symbol}")
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    price = float(ticker['lastPrice'])
    # Форматируем цены
    price_str = f"{int(price)}" if price.is_integer() else f"{price:.8f}".rstrip('0').rstrip('.')

    change = float(ticker['price24hPcnt']) * 100
    high = float(ticker['highPrice24h'])
    high_str = f"{int(high)}" if high.is_integer() else f"{high:.8f}".rstrip('0').rstrip('.')

    low = float(ticker['lowPrice24h'])
    low_str = f"{int(low)}" if low.is_integer() else f"{low:.8f}".rstrip('0').rstrip('.')

    volume = float(ticker['volume24h'])
    volume_str = f"{int(volume)}" if volume.is_integer() else f"{volume:.2f}".rstrip('0').rstrip('.')

    prev_price = float(ticker['prevPrice24h'])
    prev_price_str = f"{int(prev_price)}" if prev_price.is_integer() else f"{prev_price:.8f}".rstrip('0').rstrip('.')

    price_range = high - low
    price_range_str = f"{int(price_range)}" if price_range.is_integer() else f"{price_range:.8f}".rstrip('0').rstrip(
        '.')

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    response = f"""
📊 <b>Подробная информация {display_name}</b>

💰 <b>Цена:</b> ${price_str}
📈 <b>Изменение 24ч:</b> {change:+.4f}%
⬆️ <b>Максимум 24ч:</b> ${high_str}
⬇️ <b>Минимум 24ч:</b> ${low_str}
💎 <b>Объем 24ч:</b> ${volume_str}
📅 <b>Цена открытия:</b> ${prev_price_str}
🔄 <b>Диапазон:</b> ${price_range_str}

<i>Данные с биржи Bybit</i>
    """

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_price_actions(symbol)
    )


@router.callback_query(F.data.startswith("chart_"))
@log_function_call()
async def handle_chart(callback: CallbackQuery):
    """
    Показывает информацию о функции графиков (в разработке).
    """
    user_id = callback.from_user.id
    await callback.answer()

    symbol = callback.data.replace("chart_", "")
    logger.info(f"👤 Пользователь {user_id} запросил график для {symbol} (в разработке)")

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    await safe_edit_message(
        callback.message,
        f"📈 <b>График {display_name}</b>\n\n"
        f"🚧 <i>Функция графиков в разработке...</i>\n\n"
        f"Скоро здесь будут:\n"
        f"• Свечные графики\n"
        f"• Трендовые линии\n"
        f"• Индикаторы RSI, MACD\n"
        f"• Уровни поддержки/сопротивления",
        Keyboards.get_back_button(f"back_to_price_{symbol}")
    )


@router.callback_query(F.data.startswith("fav_"))
@log_function_call()
async def handle_favorite(callback: CallbackQuery):
    """
    Добавляет криптовалюту в избранное пользователя.
    """
    user_id = callback.from_user.id
    symbol = callback.data.replace("fav_", "")

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    logger.info(f"👤 Пользователь {user_id} добавил {display_name} в избранное")
    await callback.answer(f"✅ {display_name} добавлен в избранное!")


# ===== ОБРАБОТЧИКИ ДЛЯ УВЕДОМЛЕНИЙ =====

@router.callback_query(F.data.startswith("alert_up_percent_"))
@log_function_call()
async def handle_alert_up_percent(callback: CallbackQuery):
    """
    Устанавливает уведомление на рост цены на заданный процент.
    """
    user_id = callback.from_user.id
    await callback.answer()

    data_parts = callback.data.replace("alert_up_percent_", "").split("_")
    symbol = data_parts[0]
    percent = float(data_parts[1])

    logger.info(f"📈 Пользователь {user_id} устанавливает уведомление на рост {symbol} +{percent}%")

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        logger.error(f"❌ Не удалось получить данные для {symbol}")
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    current_price = float(ticker['lastPrice'])
    target_price = current_price * (1 + percent / 100)

    alert_id = await save_alert(
        user_id=callback.from_user.id,
        symbol=symbol,
        target_price=target_price,
        current_price=current_price,
        direction="ВВЕРХ"
    )

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

    await safe_edit_message(
        callback.message,
        f"✅ <b>Уведомление #{alert_id} установлено!</b>\n\n"
        f"Криптовалюта: <b>{short_name}</b>\n"
        f"Тип: 📈 <b>Выше на {percent}%</b>\n"
        f"Текущая цена: <b>${current_price:.4f}</b>\n"
        f"Целевая цена: <b>${target_price:.4f}</b>\n\n"
        f"Я уведомлю вас, когда цена достигнет цели!",
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data.startswith("alert_down_percent_"))
@log_function_call()
async def handle_alert_down_percent(callback: CallbackQuery):
    """
    Устанавливает уведомление на падение цены на заданный процент.
    """
    user_id = callback.from_user.id
    await callback.answer()

    data_parts = callback.data.replace("alert_down_percent_", "").split("_")
    symbol = data_parts[0]
    percent = float(data_parts[1])

    logger.info(f"📉 Пользователь {user_id} устанавливает уведомление на падение {symbol} -{percent}%")

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        logger.error(f"❌ Не удалось получить данные для {symbol}")
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    current_price = float(ticker['lastPrice'])
    target_price = current_price * (1 - percent / 100)

    alert_id = await save_alert(
        user_id=callback.from_user.id,
        symbol=symbol,
        target_price=target_price,
        current_price=current_price,
        direction="ВНИЗ"
    )

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

    await safe_edit_message(
        callback.message,
        f"✅ <b>Уведомление #{alert_id} установлено!</b>\n\n"
        f"Криптовалюта: <b>{short_name}</b>\n"
        f"Тип: 📉 <b>Ниже на {percent}%</b>\n"
        f"Текущая цена: <b>${current_price:.4f}</b>\n"
        f"Целевая цена: <b>${target_price:.4f}</b>\n\n"
        f"Я уведомлю вас, когда цена достигнет цели!",
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data.startswith("alert_custom_"))
@log_function_call()
async def handle_alert_custom(callback: CallbackQuery, state: FSMContext):
    """
    Запрашивает у пользователя ввод своей цены для уведомления.
    """
    user_id = callback.from_user.id
    await callback.answer()

    symbol = callback.data.replace("alert_custom_", "")
    logger.info(f"⚙️ Пользователь {user_id} начал установку своей цены для {symbol}")

    await state.update_data(symbol=symbol)
    await state.set_state(AlertState.waiting_for_custom_price)

    ticker = await bybit_client.get_ticker(symbol)
    if ticker:
        current_price = float(ticker['lastPrice'])

        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

        await safe_edit_message(
            callback.message,
            f"💰 <b>Установка своей цены для {short_name}</b>\n\n"
            f"Текущая цена: <b>${current_price:.4f}</b>\n\n"
            f"<b>Введите желаемую цену:</b>\n"
            f"• Для уведомления о росте - цена ВЫШЕ текущей\n"
            f"• Для уведомления о падении - цена НИЖЕ текущей\n\n"
            f"Пример: <code>50000</code> или <code>2500.50</code>\n\n"
            f"Для отмены нажмите /cancel",
            Keyboards.get_cancel_keyboard(f"cancel_custom_{symbol}")
        )
    else:
        logger.error(f"❌ Не удалось получить текущую цену для {symbol}")
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить текущую цену"
        )
        await state.clear()


@router.callback_query(F.data.startswith("cancel_custom_"))
@log_function_call()
async def handle_cancel_custom(callback: CallbackQuery, state: FSMContext):
    """
    Отменяет процесс установки своей цены для уведомления.
    """
    user_id = callback.from_user.id
    await callback.answer()

    symbol = callback.data.replace("cancel_custom_", "")
    await state.clear()

    logger.info(f"❌ Пользователь {user_id} отменил установку своей цены для {symbol}")

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

    await safe_edit_message(
        callback.message,
        f"❌ Установка уведомления для {short_name} отменена",
        Keyboards.get_back_button(f"back_to_price_{symbol}")
    )


@router.callback_query(F.data == "new_alert")
@log_function_call()
async def handle_new_alert(callback: CallbackQuery):
    """
    Начинает процесс создания нового уведомления из меню уведомлений.
    """
    user_id = callback.from_user.id
    await callback.answer()

    logger.info(f"➕ Пользователь {user_id} начал создание нового уведомления")

    await safe_edit_message(
        callback.message,
        "🔔 <b>Создание нового уведомления</b>\n\n"
        "👇 <b>Выберите криптовалюту:</b>",
        Keyboards.get_crypto_selection()
    )


@router.callback_query(F.data == "new_alert_from_select")
@log_function_call()
async def handle_new_alert_from_select(callback: CallbackQuery):
    """
    Начинает процесс создания нового уведомления из меню выбора криптовалют.
    """
    user_id = callback.from_user.id
    await callback.answer()

    logger.info(f"➕ Пользователь {user_id} начал создание нового уведомления из меню выбора")

    await safe_edit_message(
        callback.message,
        "🔔 <b>Создание нового уведомления</b>\n\n"
        "👇 <b>Выберите криптовалюту:</b>",
        Keyboards.get_crypto_selection()
    )


@router.callback_query(F.data == "list_alerts")
@log_function_call()
async def handle_list_alerts(callback: CallbackQuery):
    """
    Показывает список всех уведомлений пользователя с подробной информацией.
    """
    user_id = callback.from_user.id
    await callback.answer()

    logger.info(f"📋 Пользователь {user_id} запросил список уведомлений")

    alerts = alerts_storage.get_user_alerts(user_id)

    if not alerts:
        await safe_edit_message(
            callback.message,
            "📭 <b>У вас нет активных уведомлений</b>\n\n"
            "Нажмите '➕ Новое уведомление' чтобы создать",
            Keyboards.get_alerts_menu()
        )
        return

    response = "<b>🔔 Ваши уведомления:</b>\n\n"

    for i, alert in enumerate(alerts[:10], 1):
        direction_icon = "📈" if alert['direction'] == 'ВВЕРХ' else "📉"

        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == alert['symbol']]
        display_name = short_name[0] if short_name else alert['symbol']

        response += f"<b>#{i}. {display_name}</b>\n"
        response += f"   {direction_icon} {alert['direction']} до ${alert['target_price']:.4f}\n"
        response += f"   Текущая: ${alert['current_price']:.4f}\n"

        diff_percent = ((alert['target_price'] - alert['current_price']) / alert['current_price']) * 100
        response += f"   Осталось: {abs(diff_percent):.1f}%\n\n"

    if len(alerts) > 10:
        response += f"<i>И еще {len(alerts) - 10} уведомлений...</i>\n\n"

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_alerts_menu()
    )


@router.callback_query(F.data.startswith("delete_alert_"))
@log_function_call()
async def handle_delete_alert(callback: CallbackQuery):
    """
    Удаляет конкретное уведомление пользователя по его ID.
    """
    user_id = callback.from_user.id
    await callback.answer()

    try:
        alert_id = int(callback.data.replace("delete_alert_", ""))

        logger.info(f"🗑️ Пользователь {user_id} удаляет уведомление #{alert_id}")

        alert = alerts_storage.get_alert(user_id, alert_id)

        if alert:
            short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == alert['symbol']]
            display_name = short_name[0] if short_name else alert['symbol']

            if alerts_storage.remove_alert(user_id, alert_id):
                await safe_edit_message(
                    callback.message,
                    f"🗑️ <b>Уведомление #{alert_id} удалено</b>\n\n"
                    f"Криптовалюта: {display_name}\n"
                    f"Цель: ${alert['target_price']:.4f}",
                    Keyboards.get_back_button("back_to_alerts_list")
                )
            else:
                await callback.answer("❌ Не удалось удалить уведомление")
        else:
            await callback.answer("❌ Уведомление не найдено")

    except ValueError:
        await callback.answer("❌ Неверный ID уведомления")


@router.callback_query(F.data == "clear_alerts")
@log_function_call()
async def handle_clear_alerts(callback: CallbackQuery):
    """
    Удаляет все уведомления пользователя.
    """
    user_id = callback.from_user.id
    await callback.answer()

    logger.info(f"🗑️ Пользователь {user_id} очищает все уведомления")

    if alerts_storage.has_user_alerts(user_id):
        alert_count = alerts_storage.remove_all_user_alerts(user_id)

        await safe_edit_message(
            callback.message,
            f"🗑️ <b>Удалено {alert_count} уведомлений</b>\n\n"
            f"Все ваши уведомления были очищены.",
            Keyboards.get_back_button("back_to_main")
        )
    else:
        await callback.answer("✅ У вас нет уведомлений")


@router.callback_query(F.data == "back_to_alerts_list")
@log_function_call()
async def handle_back_to_alerts_list(callback: CallbackQuery):
    """
    Возвращает пользователя к списку уведомлений.
    """
    await callback.answer()
    await handle_list_alerts(callback)


@router.callback_query(F.data == "alert_help")
@log_function_call()
async def handle_alert_help(callback: CallbackQuery):
    """
    Показывает справку по уведомлениям.
    """
    user_id = callback.from_user.id
    await callback.answer()

    logger.info(f"❓ Пользователь {user_id} запросил помощь по уведомлениям")

    help_text = f"""
❓ <b>Помощь по уведомлениям</b>

📈 <b>Типы уведомлений:</b>
• <b>Выше на X%</b> - сработает, когда цена вырастет на указанный процент от текущей
• <b>Ниже на X%</b> - сработает, когда цена упадет на указанный процент от текущей
• <b>Своя цена</b> - сработает при достижении указанной вами цены

💡 <b>Как работают уведомления:</b>
1. Бот отслеживает цены в реальном времени
2. Проверка происходит каждые {Config.ALERT_INTERVAL} секунд
3. При достижении цели вы получите сообщение
4. Уведомление автоматически удаляется после срабатывания

⚙️ <b>Управление:</b>
• Список всех уведомлений - "📋 Список уведомлений"
• Удалить одно - нажмите на него и выберите "🗑️ Удалить"
• Очистить все - "🗑️ Очистить все"
    """

    await safe_edit_message(
        callback.message,
        help_text,
        Keyboards.get_back_button("back_to_alerts_list")
    )


# Обработчик для alert_ (должен быть после всех специфичных alert_ обработчиков)
@router.callback_query(F.data.startswith("alert_"))
@log_function_call()
async def handle_alert_setup(callback: CallbackQuery):
    """
    Показывает меню настройки уведомления для выбранной криптовалюты.
    """
    user_id = callback.from_user.id
    await callback.answer()

    # Проверяем, что это не другие типы alert_
    if callback.data in ["alert_settings", "alert_help", "new_alert", "new_alert_from_select",
                         "list_alerts", "clear_alerts", "back_to_alerts_list"]:
        return

    if "_percent_" in callback.data:
        return

    symbol = callback.data.replace("alert_", "")

    logger.info(f"🔔 Пользователь {user_id} настраивает уведомление для {symbol}")

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        logger.error(f"❌ Не удалось получить данные для {symbol}")
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    current_price = float(ticker['lastPrice'])

    response = f"""
🔔 <b>Настройка уведомления для {display_name}</b>

💰 Текущая цена: <b>${current_price:,.4f}</b>

👇 <b>Выберите тип уведомления:</b>
• 📈 Выше на 5% - когда вырастет на 5%
• 📉 Ниже на 5% - когда упадет на 5%
• 📈 Выше на 10% - когда вырастет на 10%
• 📉 Ниже на 10% - когда упадет на 10%
• ⚙️ Своя цена - введите свою цену
    """

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_alert_setup(symbol)
    )


# ===== ОБРАБОТЧИКИ КНОПОК НАЗАД =====

@router.callback_query(F.data.startswith("back_to_"))
@log_function_call()
async def handle_back_button(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает различные кнопки "Назад" в приложении.
    """
    user_id = callback.from_user.id
    await callback.answer()

    back_to = callback.data
    logger.debug(f"↩️ Пользователь {user_id} нажал кнопку 'Назад': {back_to}")

    if back_to == "back_to_main":
        await state.clear()
        await safe_edit_message(
            callback.message,
            "↩️ Возвращаемся в главное меню...",
            None
        )
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


# ===== ОБРАБОТЧИКИ СООБЩЕНИЙ ДЛЯ FSM =====

@router.message(AlertState.waiting_for_custom_price)
@log_function_call()
async def process_custom_price(message: Message, state: FSMContext):
    """
    Обрабатывает введенную пользователем цену для уведомления.
    """
    user_id = message.from_user.id

    try:
        target_price = float(message.text.replace(",", "."))

        data = await state.get_data()
        symbol = data.get("symbol")

        if not symbol:
            logger.error(f"❌ Ошибка данных в состоянии для пользователя {user_id}")
            await message.answer("❌ Ошибка данных")
            await state.clear()
            return

        logger.info(f"💰 Пользователь {user_id} ввел свою цену {target_price} для {symbol}")

        ticker = await bybit_client.get_ticker(symbol)
        if not ticker:
            logger.error(f"❌ Не удалось получить текущую цену для {symbol}")
            await message.answer("❌ Не удалось получить текущую цену")
            await state.clear()
            return

        current_price = float(ticker['lastPrice'])

        direction = "ВВЕРХ" if target_price > current_price else "ВНИЗ"

        alert_id = await save_alert(
            user_id=message.from_user.id,
            symbol=symbol,
            target_price=target_price,
            current_price=current_price,
            direction=direction
        )

        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]
        direction_icon = "📈" if direction == "ВВЕРХ" else "📉"

        response = f"""
✅ <b>Уведомление #{alert_id} установлено!</b>

Криптовалюта: <b>{short_name}</b>
Тип: {direction_icon} <b>{direction}</b>
Текущая цена: <b>${current_price:.4f}</b>
Целевая цена: <b>${target_price:.4f}</b>

Я уведомлю вас, когда цена достигнет цели!
        """

        await message.answer(
            response,
            reply_markup=Keyboards.get_main_menu()
        )

        await state.clear()

    except ValueError:
        logger.warning(f"⚠️ Пользователь {user_id} ввел некорректную цену: {message.text}")
        await message.answer("❌ Неверный формат цены. Введите число, например: 50000 или 2500.50")


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def save_alert(user_id: int, symbol: str, target_price: float, current_price: float, direction: str) -> int:
    """
    Сохраняет новое уведомление в хранилище.
    """
    alert = {
        'symbol': symbol,
        'target_price': target_price,
        'current_price': current_price,
        'direction': direction,
        'user_id': user_id,
        'created_at': datetime.now().isoformat()
    }

    alert_id = alerts_storage.add_alert(user_id, alert)
    logger.info(f"✅ Уведомление #{alert_id} сохранено для пользователя {user_id}: {symbol} {direction} до {target_price:.4f}")
    return alert_id


async def show_crypto_price(message, symbol: str):
    """
    Показывает цену криптовалюты в ответ на текстовое сообщение.
    """
    ticker = await bybit_client.get_ticker(symbol)

    if not ticker:
        await message.answer(f"❌ Не удалось получить данные для {symbol}")
        return

    await format_and_send_price(message, symbol, ticker, is_callback=False)


async def show_crypto_price_callback(callback: CallbackQuery, symbol: str):
    """
    Показывает цену криптовалюты в ответ на callback запрос.
    """
    ticker = await bybit_client.get_ticker(symbol)

    if not ticker:
        await safe_edit_message(
            callback.message,
            f"❌ Не удалось получить данные для {symbol}"
        )
        return

    await format_and_send_price(callback.message, symbol, ticker, is_callback=True)


async def format_and_send_price(message_obj, symbol: str, ticker: dict, is_callback: bool = False):
    """
    Форматирует данные о цене и отправляет их пользователю.
    """
    price = float(ticker['lastPrice'])

    # Форматируем цену без лишних нулей
    if price.is_integer():
        price_str = f"{int(price)}"
    else:
        price_str = f"{price:.8f}".rstrip('0').rstrip('.')

    change = float(ticker['price24hPcnt']) * 100
    high = float(ticker['highPrice24h'])
    low = float(ticker['lowPrice24h'])

    # Форматируем остальные числа
    high_str = f"{int(high)}" if high.is_integer() else f"{high:.8f}".rstrip('0').rstrip('.')
    low_str = f"{int(low)}" if low.is_integer() else f"{low:.8f}".rstrip('0').rstrip('.')
    volume = float(ticker['volume24h'])
    volume_str = f"{int(volume)}" if volume.is_integer() else f"{volume:.2f}".rstrip('0').rstrip('.')

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    change_icon = "📈" if change > 0 else "📉"
    change_color = "🟢" if change > 0 else "🔴"

    response = f"""
<b>{display_name}</b>

💰 <b>Цена:</b> ${price_str}
{change_icon} <b>Изменение 24ч:</b> {change_color} {change:+.4f}%
⬆️ <b>Макс 24ч:</b> ${high_str}
⬇️ <b>Мин 24ч:</b> ${low_str}
📊 <b>Объем 24ч:</b> ${volume_str}

<i>Данные с биржи Bybit</i>
    """

    if is_callback:
        await safe_edit_message(
            message_obj,
            response,
            Keyboards.get_price_actions(symbol)
        )
    else:
        await message_obj.answer(
            response,
            reply_markup=Keyboards.get_price_actions(symbol)
        )


# ===== ФУНКЦИЯ ДЛЯ ПРОВЕРКИ УВЕДОМЛЕНИЙ =====

async def check_alerts_task():
    """
    Фоновая задача для проверки уведомлений пользователей.
    """
    logger.info("🚀 Запуск фоновой задачи проверки уведомлений")

    while True:
        try:
            active_users = len(alerts_storage.get_all_users())
            total_alerts = alerts_storage.get_total_alerts_count()

            logger.info(f"🔍 Проверка уведомлений... Активных пользователей: {active_users}, всего уведомлений: {total_alerts}")

            completed_alerts = []

            for user_id in alerts_storage.get_all_users():
                alerts = alerts_storage.get_user_alerts(user_id)

                for alert in alerts:
                    symbol = alert['symbol']

                    ticker = await bybit_client.get_ticker(symbol)
                    if ticker:
                        current_price = float(ticker['lastPrice'])
                        alert['current_price'] = current_price

                        target_reached = False
                        if alert['direction'] == "ВВЕРХ" and current_price >= alert['target_price']:
                            target_reached = True
                            logger.info(f"🎯 Цель достигнута! {symbol}: {current_price:.4f} >= {alert['target_price']:.4f}")
                        elif alert['direction'] == "ВНИЗ" and current_price <= alert['target_price']:
                            target_reached = True
                            logger.info(f"🎯 Цель достигнута! {symbol}: {current_price:.4f} <= {alert['target_price']:.4f}")

                        if target_reached:
                            short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
                            display_name = short_name[0] if short_name else symbol
                            direction_icon = "📈" if alert['direction'] == "ВВЕРХ" else "📉"

                            try:
                                await bot.send_message(
                                    user_id,
                                    f"🚨 <b>УВЕДОМЛЕНИЕ #{alert['id']}</b>\n\n"
                                    f"{display_name} достиг цели!\n"
                                    f"{direction_icon} <b>{alert['direction']}</b> до ${alert['target_price']:.4f}\n"
                                    f"Текущая цена: <b>${current_price:.4f}</b>\n\n"
                                    f"<i>Уведомление выполнено ✅</i>"
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


# ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ =====

def register_handlers(dp, bot_instance):
    """
    Регистрирует все обработчики в диспетчере и запускает фоновые задачи.
    """
    dp.include_router(router)

    global bot
    bot = bot_instance

    asyncio.create_task(check_alerts_task())
    logger.info("🚀 Фоновая задача проверки уведомлений запущена")