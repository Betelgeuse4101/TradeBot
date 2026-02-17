# handlers.py
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from datetime import datetime
from aiogram.exceptions import TelegramBadRequest

from config import Config
from bybit_client import BybitClient
from keyboards import Keyboards
from alerts_storage import AlertsStorage


class AlertState(StatesGroup):
    """
    Состояния FSM (Finite State Machine) для процесса создания уведомлений.

    Используется для отслеживания этапов диалога с пользователем при
    настройке пользовательских уведомлений о ценах.

    States:
        waiting_for_custom_price: Ожидание ввода пользовательской цены
    """
    waiting_for_custom_price = State()


# Создаем роутер для регистрации обработчиков
router = Router()

# Инициализация хранилища уведомлений
alerts_storage = AlertsStorage("alerts.json")

# Глобальные переменные
bot = None  # Будет установлено при регистрации

# Инициализация клиента Bybit
bybit_client = BybitClient()


# Вспомогательная функция для безопасного редактирования сообщений
async def safe_edit_message(message, text, reply_markup=None):
    """
    Безопасно редактирует сообщение, игнорируя ошибку "message is not modified".

    Args:
        message: Объект сообщения для редактирования
        text: Новый текст сообщения
        reply_markup: Новая клавиатура (опционально)

    Returns:
        bool: True если сообщение было изменено, False если нет
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            # Сообщение не изменилось - это не ошибка, просто игнорируем
            print("Сообщение не изменилось, пропускаем")
            return False
        else:
            # Другая ошибка - пробрасываем дальше
            print(f"Ошибка при редактировании сообщения: {e}")
            raise e


# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ =====

@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обработчик команды /start.

    Отправляет приветственное сообщение с описанием функций бота
    и показывает главное меню с reply-клавиатурой.

    Args:
        message (Message): Объект сообщения от пользователя
    """
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
async def show_quotes(message: Message):
    """
    Показывает меню выбора криптовалют для просмотра котировок.

    Args:
        message (Message): Объект сообщения от пользователя
    """
    await message.answer(
        "📊 <b>Выберите криптовалюту:</b>\n"
        "Или используйте /price [символ] для любой пары",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "🚀 Популярные")
async def show_popular(message: Message):
    """
    Показывает текущие цены на популярные криптовалюты.

    Получает данные для первых 6 популярных пар из конфига
    и отображает их с изменением за 24 часа.

    Args:
        message (Message): Объект сообщения от пользователя
    """
    await message.answer("⏳ Получаю актуальные цены...")

    symbols = list(Config.POPULAR_CRYPTO.values())[:6]
    tickers = await bybit_client.get_multiple_tickers(symbols)

    if not tickers:
        await message.answer("❌ Не удалось получить данные")
        return

    response = "<b>🚀 Популярные криптовалюты:</b>\n\n"

    for symbol, ticker in tickers.items():
        price = float(ticker['lastPrice'])
        change = float(ticker['price24hPcnt']) * 100
        change_icon = "🟢" if change > 0 else "🔴"

        # Находим короткое имя
        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

        response += f"<b>{short_name}</b> (${price:,.4f}) {change_icon} {change:+.4f}%\n"

    await message.answer(
        response,
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.message(F.text == "🔔 Мои уведомления")
async def show_my_alerts(message: Message):
    """
    Показывает информацию об уведомлениях пользователя.

    Если у пользователя нет уведомлений - показывает соответствующее сообщение.
    Если есть - показывает сводку по криптовалютам с количеством уведомлений.

    Args:
        message (Message): Объект сообщения от пользователя
    """
    user_id = message.from_user.id
    alerts = alerts_storage.get_user_alerts(user_id)

    if not alerts:
        response = "📭 <b>У вас нет активных уведомлений</b>\n\n"
        response += "Нажмите '➕ Новое уведомление' чтобы создать"

        await message.answer(
            response,
            reply_markup=Keyboards.get_alerts_menu()
        )
    else:
        # Показываем краткую информацию
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
async def show_stats_menu(message: Message):
    """
    Показывает меню выбора криптовалюты для просмотра статистики.

    Args:
        message (Message): Объект сообщения от пользователя
    """
    await message.answer(
        "📈 <b>Выберите криптовалюту для подробной статистики:</b>",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message):
    """
    Показывает меню настроек бота.

    Отображает текущую статистику пользователя и доступные настройки.

    Args:
        message (Message): Объект сообщения от пользователя
    """
    user_id = message.from_user.id
    alert_count = len(alerts_storage.get_user_alerts(user_id))

    settings_text = f"""
⚙️ <b>Настройки бота</b>

📊 <b>Статистика:</b>
• Активных уведомлений: {alert_count}
• Отслеживаемых пар: {len(Config.POPULAR_CRYPTO)}

🔧 <b>Настройки:</b>
• Интервал проверки: {Config.ALERT_INTERVAL} сек

👇 <b>Выберите настройку для изменения:</b>
    """

    await message.answer(
        settings_text,
        reply_markup=Keyboards.get_settings_menu()
    )


@router.message(F.text == "📋 Помощь")
async def show_help(message: Message):
    """
    Показывает справочную информацию по использованию бота.

    Содержит описание всех разделов, работу с уведомлениями
    и список доступных команд.

    Args:
        message (Message): Объект сообщения от пользователя
    """
    help_text = """
📚 <b>Помощь по боту</b>

🎯 <b>Основные разделы:</b>
• <b>💰 Котировки</b> - выбор криптовалюты для просмотра цены
• <b>🚀 Популярные</b> - быстрый просмотр топ-криптовалют
• <b>🔔 Мои уведомления</b> - управление уведомлениями о ценах
• <b>📊 Статистика</b> - детальная статистика по парам
• <b>⚙️ Настройки</b> - настройки бота

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
async def cmd_price(message: Message):
    """
    Обработчик команды /price для получения цены по символу.

    Формат: /price BTCUSDT

    Args:
        message (Message): Объект сообщения от пользователя
    """
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажите символ: /price BTCUSDT")
        return

    symbol = args[1].upper()
    await show_crypto_price(message, symbol)


@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    """
    Обработчик команды /alerts для показа уведомлений.

    Args:
        message (Message): Объект сообщения от пользователя
    """
    await show_my_alerts(message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """
    Обработчик команды /cancel для отмены текущего действия.

    Очищает состояние FSM и возвращает пользователя в главное меню.

    Args:
        message (Message): Объект сообщения от пользователя
        state (FSMContext): Контекст состояния FSM
    """
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=Keyboards.get_main_menu()
    )


# ===== ОБРАБОТЧИКИ CALLBACK ДЛЯ КРИПТОВАЛЮТ =====

@router.callback_query(F.data.startswith("crypto_"))
async def handle_crypto_selection(callback: CallbackQuery):
    """
    Обрабатывает выбор криптовалюты из списка.

    Извлекает символ из callback_data и показывает текущую цену.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()  # Отвечаем на callback, чтобы убрать "часики"

    symbol = callback.data.replace("crypto_", "")

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    await safe_edit_message(
        callback.message,
        f"⏳ Получаю данные для <b>{display_name}</b>...",
        Keyboards.get_back_button("back_to_crypto")
    )

    await show_crypto_price_callback(callback, symbol)


@router.callback_query(F.data == "all_prices")
async def handle_all_prices(callback: CallbackQuery):
    """
    Показывает цены для всех доступных криптовалют.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    await safe_edit_message(
        callback.message,
        "⏳ Получаю все котировки..."
    )

    tickers = await bybit_client.get_multiple_tickers(Config.DEFAULT_PAIRS)

    if not tickers:
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    response = "<b>💰 Все котировки:</b>\n\n"

    for symbol, ticker in tickers.items():
        price = float(ticker['lastPrice'])
        change = float(ticker['price24hPcnt']) * 100
        change_icon = "🟢" if change > 0 else "🔴"

        # Находим короткое имя
        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
        display_name = short_name[0] if short_name else symbol

        response += f"<b>{display_name}</b>: ${price:,.4f} {change_icon} {change:+.4f}%\n"

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_back_button("back_to_crypto")
    )


@router.callback_query(F.data.startswith("detail_"))
async def handle_detail(callback: CallbackQuery):
    """
    Показывает подробную информацию о выбранной криптовалюте.

    Включает: цену, изменение за 24ч, максимум, минимум, объем,
    цену открытия и диапазон.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    symbol = callback.data.replace("detail_", "")

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    price = float(ticker['lastPrice'])
    change = float(ticker['price24hPcnt']) * 100
    high = float(ticker['highPrice24h'])
    low = float(ticker['lowPrice24h'])
    volume = float(ticker['volume24h'])

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    response = f"""
📊 <b>Подробная информация {display_name}</b>

💰 <b>Цена:</b> ${price:,.4f}
📈 <b>Изменение 24ч:</b> {change:+.4f}%
⬆️ <b>Максимум 24ч:</b> ${high:,.4f}
⬇️ <b>Минимум 24ч:</b> ${low:,.4f}
💎 <b>Объем 24ч:</b> ${volume:,.0f}
📅 <b>Цена открытия:</b> ${float(ticker['prevPrice24h']):,.4f}
🔄 <b>Диапазон:</b> ${high - low:,.4f}

<i>Данные с биржи Bybit</i>
    """

    await safe_edit_message(
        callback.message,
        response,
        Keyboards.get_price_actions(symbol)
    )


@router.callback_query(F.data.startswith("chart_"))
async def handle_chart(callback: CallbackQuery):
    """
    Показывает информацию о функции графиков (в разработке).

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    symbol = callback.data.replace("chart_", "")

    # Находим короткое имя
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
async def handle_favorite(callback: CallbackQuery):
    """
    Добавляет криптовалюту в избранное пользователя.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    symbol = callback.data.replace("fav_", "")

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    await callback.answer(f"✅ {display_name} добавлен в избранное!")


# ===== ОБРАБОТЧИКИ ДЛЯ УВЕДОМЛЕНИЙ =====
# ВАЖНО: Специфичные обработчики должны идти ДО общего обработчика alert_

@router.callback_query(F.data.startswith("alert_up_percent_"))
async def handle_alert_up_percent(callback: CallbackQuery):
    """
    Устанавливает уведомление на рост цены на заданный процент.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    # Формат: alert_up_percent_BTCUSDT_5
    data_parts = callback.data.replace("alert_up_percent_", "").split("_")
    symbol = data_parts[0]
    percent = float(data_parts[1])

    print(f"📈 Установка уведомления на рост: {symbol} +{percent}%")

    # Получаем текущую цену
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    current_price = float(ticker['lastPrice'])
    target_price = current_price * (1 + percent / 100)

    # Сохраняем уведомление
    alert_id = await save_alert(
        user_id=callback.from_user.id,
        symbol=symbol,
        target_price=target_price,
        current_price=current_price,
        direction="ВВЕРХ"
    )

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

    await safe_edit_message(
        callback.message,
        f"✅ <b>Уведомление #{alert_id} установлено!</b>\n\n"
        f"Криптовалюта: <b>{short_name}</b>\n"
        f"Тип: 📈 <b>Выше на {percent}%</b>\n"
        f"Текущая цена: <b>${current_price:,.4f}</b>\n"
        f"Целевая цена: <b>${target_price:,.4f}</b>\n\n"
        f"Я уведомлю вас, когда цена достигнет цели!",
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data.startswith("alert_down_percent_"))
async def handle_alert_down_percent(callback: CallbackQuery):
    """
    Устанавливает уведомление на падение цены на заданный процент.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    # Формат: alert_down_percent_BTCUSDT_5
    data_parts = callback.data.replace("alert_down_percent_", "").split("_")
    symbol = data_parts[0]
    percent = float(data_parts[1])

    print(f"📉 Установка уведомления на падение: {symbol} -{percent}%")

    # Получаем текущую цену
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить данные"
        )
        return

    current_price = float(ticker['lastPrice'])
    target_price = current_price * (1 - percent / 100)

    # Сохраняем уведомление
    alert_id = await save_alert(
        user_id=callback.from_user.id,
        symbol=symbol,
        target_price=target_price,
        current_price=current_price,
        direction="ВНИЗ"
    )

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

    await safe_edit_message(
        callback.message,
        f"✅ <b>Уведомление #{alert_id} установлено!</b>\n\n"
        f"Криптовалюта: <b>{short_name}</b>\n"
        f"Тип: 📉 <b>Ниже на {percent}%</b>\n"
        f"Текущая цена: <b>${current_price:,.4f}</b>\n"
        f"Целевая цена: <b>${target_price:,.4f}</b>\n\n"
        f"Я уведомлю вас, когда цена достигнет цели!",
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data.startswith("alert_custom_"))
async def handle_alert_custom(callback: CallbackQuery, state: FSMContext):
    """
    Запрашивает у пользователя ввод своей цены для уведомления.

    Переводит бота в состояние ожидания ввода цены.

    Args:
        callback (CallbackQuery): Объект callback запроса
        state (FSMContext): Контекст состояния FSM
    """
    await callback.answer()

    symbol = callback.data.replace("alert_custom_", "")

    # Сохраняем данные в состоянии
    await state.update_data(symbol=symbol)
    await state.set_state(AlertState.waiting_for_custom_price)

    # Получаем текущую цену для справки
    ticker = await bybit_client.get_ticker(symbol)
    if ticker:
        current_price = float(ticker['lastPrice'])

        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

        await safe_edit_message(
            callback.message,
            f"💰 <b>Установка своей цены для {short_name}</b>\n\n"
            f"Текущая цена: <b>${current_price:,.4f}</b>\n\n"
            f"<b>Введите желаемую цену:</b>\n"
            f"• Для уведомления о росте - цена ВЫШЕ текущей\n"
            f"• Для уведомления о падении - цена НИЖЕ текущей\n\n"
            f"Пример: <code>50000</code> или <code>2500.50</code>\n\n"
            f"Для отмены нажмите /cancel",
            Keyboards.get_cancel_keyboard(f"cancel_custom_{symbol}")
        )
    else:
        await safe_edit_message(
            callback.message,
            "❌ Не удалось получить текущую цену"
        )
        await state.clear()


@router.callback_query(F.data.startswith("cancel_custom_"))
async def handle_cancel_custom(callback: CallbackQuery, state: FSMContext):
    """
    Отменяет процесс установки своей цены для уведомления.

    Args:
        callback (CallbackQuery): Объект callback запроса
        state (FSMContext): Контекст состояния FSM
    """
    await callback.answer()

    symbol = callback.data.replace("cancel_custom_", "")
    await state.clear()

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

    await safe_edit_message(
        callback.message,
        f"❌ Установка уведомления для {short_name} отменена",
        Keyboards.get_back_button(f"back_to_price_{symbol}")
    )


@router.callback_query(F.data == "new_alert")
async def handle_new_alert(callback: CallbackQuery):
    """
    Начинает процесс создания нового уведомления из меню уведомлений.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    await safe_edit_message(
        callback.message,
        "🔔 <b>Создание нового уведомления</b>\n\n"
        "👇 <b>Выберите криптовалюту:</b>",
        Keyboards.get_crypto_selection()
    )


@router.callback_query(F.data == "new_alert_from_select")
async def handle_new_alert_from_select(callback: CallbackQuery):
    """
    Начинает процесс создания нового уведомления из меню выбора криптовалют.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    await safe_edit_message(
        callback.message,
        "🔔 <b>Создание нового уведомления</b>\n\n"
        "👇 <b>Выберите криптовалюту:</b>",
        Keyboards.get_crypto_selection()
    )


@router.callback_query(F.data == "list_alerts")
async def handle_list_alerts(callback: CallbackQuery):
    """
    Показывает список всех уведомлений пользователя с подробной информацией.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    user_id = callback.from_user.id
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

    for i, alert in enumerate(alerts[:10], 1):  # Показываем первые 10
        direction_icon = "📈" if alert['direction'] == 'ВВЕРХ' else "📉"

        # Находим короткое имя
        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == alert['symbol']]
        display_name = short_name[0] if short_name else alert['symbol']

        response += f"<b>#{i}. {display_name}</b>\n"
        response += f"   {direction_icon} {alert['direction']} до ${alert['target_price']:,.2f}\n"
        response += f"   Текущая: ${alert['current_price']:,.2f}\n"

        # Рассчитываем разницу в процентах
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
async def handle_delete_alert(callback: CallbackQuery):
    """
    Удаляет конкретное уведомление пользователя по его ID.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    try:
        alert_id = int(callback.data.replace("delete_alert_", ""))
        user_id = callback.from_user.id

        alert = alerts_storage.get_alert(user_id, alert_id)

        if alert:
            # Находим короткое имя
            short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == alert['symbol']]
            display_name = short_name[0] if short_name else alert['symbol']

            if alerts_storage.remove_alert(user_id, alert_id):
                await safe_edit_message(
                    callback.message,
                    f"🗑️ <b>Уведомление #{alert_id} удалено</b>\n\n"
                    f"Криптовалюта: {display_name}\n"
                    f"Цель: ${alert['target_price']:,.2f}",
                    Keyboards.get_back_button("back_to_alerts_list")
                )
            else:
                await callback.answer("❌ Не удалось удалить уведомление")
        else:
            await callback.answer("❌ Уведомление не найдено")

    except ValueError:
        await callback.answer("❌ Неверный ID уведомления")


@router.callback_query(F.data == "clear_alerts")
async def handle_clear_alerts(callback: CallbackQuery):
    """
    Удаляет все уведомления пользователя.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    user_id = callback.from_user.id

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
async def handle_back_to_alerts_list(callback: CallbackQuery):
    """
    Возвращает пользователя к списку уведомлений.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()
    await handle_list_alerts(callback)


@router.callback_query(F.data == "alert_help")
async def handle_alert_help(callback: CallbackQuery):
    """
    Показывает справку по уведомлениям.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

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


# Этот обработчик должен быть ПОСЛЕ всех специфичных alert_ обработчиков
@router.callback_query(F.data.startswith("alert_"))
async def handle_alert_setup(callback: CallbackQuery):
    """
    Показывает меню настройки уведомления для выбранной криптовалюты.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    # Проверяем, что это не другие типы alert_ (они уже обработаны выше)
    if callback.data in ["alert_settings", "alert_help", "new_alert", "new_alert_from_select",
                         "list_alerts", "clear_alerts", "back_to_alerts_list"]:
        return

    # Убеждаемся, что это не процентные уведомления
    if "_percent_" in callback.data:
        return

    symbol = callback.data.replace("alert_", "")

    print(f"🔔 Настройка уведомления для {symbol}")

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    # Получаем текущую цену
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
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
async def handle_back_button(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает различные кнопки "Назад" в приложении.

    В зависимости от callback_data возвращает пользователя
    в соответствующее меню.

    Args:
        callback (CallbackQuery): Объект callback запроса
        state (FSMContext): Контекст состояния FSM
    """
    await callback.answer()

    back_to = callback.data

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

    elif back_to == "alert_settings":
        await safe_edit_message(
            callback.message,
            "⚙️ <b>Настройки уведомлений</b>\n\n"
            "🚧 <i>Функция в разработке...</i>",
            Keyboards.get_back_button("back_to_main")
        )


# ===== ОБРАБОТЧИКИ НАСТРОЕК =====

@router.callback_query(F.data == "interval_setting")
async def handle_interval_setting(callback: CallbackQuery):
    """
    Показывает информацию о настройке интервала проверки уведомлений.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    await safe_edit_message(
        callback.message,
        f"⏰ <b>Текущий интервал проверки: {Config.ALERT_INTERVAL} сек</b>\n\n"
        f"🚧 <i>Изменение интервала в разработке...</i>\n\n"
        f"Сейчас бот проверяет уведомления каждые {Config.ALERT_INTERVAL} секунд",
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data == "theme_setting")
async def handle_theme_setting(callback: CallbackQuery):
    """
    Показывает информацию о настройке темы оформления.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    await safe_edit_message(
        callback.message,
        "🎨 <b>Настройки темы</b>\n\n"
        "🚧 <i>Функция в разработке...</i>\n\n"
        "Скоро здесь можно будет выбрать:\n"
        "• Светлая/темная тема\n"
        "• Цветовые схемы\n"
        "• Шрифты",
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data == "notify_setting")
async def handle_notify_setting(callback: CallbackQuery):
    """
    Показывает информацию о настройках уведомлений.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    await safe_edit_message(
        callback.message,
        "🔕 <b>Настройки уведомлений</b>\n\n"
        "🚧 <i>Функция в разработке...</i>\n\n"
        "Скоро здесь можно будет настроить:\n"
        "• Типы уведомлений (звук, вибрация)\n"
        "• Время тишины\n"
        "• Приоритеты",
        Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data == "export_data")
async def handle_export_data(callback: CallbackQuery):
    """
    Показывает информацию об экспорте данных.

    Args:
        callback (CallbackQuery): Объект callback запроса
    """
    await callback.answer()

    await safe_edit_message(
        callback.message,
        "💾 <b>Экспорт данных</b>\n\n"
        "🚧 <i>Функция в разработке...</i>\n\n"
        "Скоро здесь можно будет:\n"
        "• Экспортировать историю уведомлений\n"
        "• Скачать данные в CSV/Excel\n"
        "• Сохранить настройки",
        Keyboards.get_back_button("back_to_main")
    )


# ===== ОБРАБОТЧИКИ СООБЩЕНИЙ ДЛЯ FSM =====

@router.message(AlertState.waiting_for_custom_price)
async def process_custom_price(message: Message, state: FSMContext):
    """
    Обрабатывает введенную пользователем цену для уведомления.

    Проверяет корректность ввода, определяет направление (вверх/вниз)
    и сохраняет уведомление.

    Args:
        message (Message): Объект сообщения от пользователя
        state (FSMContext): Контекст состояния FSM
    """
    try:
        target_price = float(message.text.replace(",", "."))

        # Получаем данные из состояния
        data = await state.get_data()
        symbol = data.get("symbol")

        if not symbol:
            await message.answer("❌ Ошибка данных")
            await state.clear()
            return

        # Получаем текущую цену
        ticker = await bybit_client.get_ticker(symbol)
        if not ticker:
            await message.answer("❌ Не удалось получить текущую цену")
            await state.clear()
            return

        current_price = float(ticker['lastPrice'])

        # Определяем направление
        direction = "ВВЕРХ" if target_price > current_price else "ВНИЗ"

        # Сохраняем уведомление
        alert_id = await save_alert(
            user_id=message.from_user.id,
            symbol=symbol,
            target_price=target_price,
            current_price=current_price,
            direction=direction
        )

        # Находим короткое имя
        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]
        direction_icon = "📈" if direction == "ВВЕРХ" else "📉"

        response = f"""
✅ <b>Уведомление #{alert_id} установлено!</b>

Криптовалюта: <b>{short_name}</b>
Тип: {direction_icon} <b>{direction}</b>
Текущая цена: <b>${current_price:,.4f}</b>
Целевая цена: <b>${target_price:,.4f}</b>

Я уведомлю вас, когда цена достигнет цели!
        """

        await message.answer(
            response,
            reply_markup=Keyboards.get_main_menu()
        )

        await state.clear()

    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите число, например: 50000 или 2500.50")


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def save_alert(user_id: int, symbol: str, target_price: float, current_price: float, direction: str) -> int:
    """
    Сохраняет новое уведомление в хранилище.

    Генерирует уникальный ID для уведомления и добавляет его
    в список уведомлений пользователя.

    Args:
        user_id (int): ID пользователя Telegram
        symbol (str): Торговый символ (например, "BTCUSDT")
        target_price (float): Целевая цена для уведомления
        current_price (float): Текущая цена при создании уведомления
        direction (str): Направление ("ВВЕРХ" или "ВНИЗ")

    Returns:
        int: ID созданного уведомления
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
    print(f"✅ Уведомление #{alert_id} сохранено для пользователя {user_id}: {symbol} {direction} до {target_price}")
    return alert_id


async def show_crypto_price(message, symbol: str):
    """
    Показывает цену криптовалюты в ответ на текстовое сообщение.

    Args:
        message (Message): Объект сообщения от пользователя
        symbol (str): Торговый символ (например, "BTCUSDT")
    """
    ticker = await bybit_client.get_ticker(symbol)

    if not ticker:
        await message.answer(f"❌ Не удалось получить данные для {symbol}")
        return

    await format_and_send_price(message, symbol, ticker, is_callback=False)


async def show_crypto_price_callback(callback: CallbackQuery, symbol: str):
    """
    Показывает цену криптовалюты в ответ на callback запрос.

    Args:
        callback (CallbackQuery): Объект callback запроса
        symbol (str): Торговый символ (например, "BTCUSDT")
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

    Args:
        message_obj (Message): Объект сообщения для ответа
        symbol (str): Торговый символ (например, "BTCUSDT")
        ticker (dict): Данные тикера от Bybit API
        is_callback (bool): Флаг, указывающий, что это ответ на callback
    """
    price = float(ticker['lastPrice'])
    change = float(ticker['price24hPcnt']) * 100
    high = float(ticker['highPrice24h'])
    low = float(ticker['lowPrice24h'])

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    change_icon = "📈" if change > 0 else "📉"
    change_color = "🟢" if change > 0 else "🔴"

    response = f"""
<b>{display_name}</b>

💰 <b>Цена:</b> ${price:,.4f}
{change_icon} <b>Изменение 24ч:</b> {change_color} {change:+.4f}%
⬆️ <b>Макс 24ч:</b> ${high:,.4f}
⬇️ <b>Мин 24ч:</b> ${low:,.4f}
📊 <b>Объем 24ч:</b> ${float(ticker['volume24h']):,.0f}

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

    Запускается в бесконечном цикле и периодически проверяет,
    достигли ли цены целевых значений для активных уведомлений.
    При достижении цели отправляет уведомление пользователю
    и удаляет выполненное уведомление.

    Интервал проверки задается в Config.ALERT_INTERVAL.
    """
    while True:
        try:
            print(f"🔍 Проверка уведомлений... Активных пользователей: {len(alerts_storage.get_all_users())}")

            completed_alerts = []  # Список для сбора выполненных уведомлений

            for user_id in alerts_storage.get_all_users():
                alerts = alerts_storage.get_user_alerts(user_id)

                for alert in alerts:
                    symbol = alert['symbol']

                    # Получаем текущую цену
                    ticker = await bybit_client.get_ticker(symbol)
                    if ticker:
                        current_price = float(ticker['lastPrice'])

                        # Обновляем текущую цену в алерте
                        alert['current_price'] = current_price

                        # Проверяем достижение цели
                        target_reached = False
                        if alert['direction'] == "ВВЕРХ" and current_price >= alert['target_price']:
                            target_reached = True
                            print(f"🎯 Цель достигнута! {symbol}: {current_price} >= {alert['target_price']}")
                        elif alert['direction'] == "ВНИЗ" and current_price <= alert['target_price']:
                            target_reached = True
                            print(f"🎯 Цель достигнута! {symbol}: {current_price} <= {alert['target_price']}")

                        if target_reached:
                            # Находим короткое имя
                            short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
                            display_name = short_name[0] if short_name else symbol

                            direction_icon = "📈" if alert['direction'] == "ВВЕРХ" else "📉"

                            try:
                                await bot.send_message(
                                    user_id,
                                    f"🚨 <b>УВЕДОМЛЕНИЕ #{alert['id']}</b>\n\n"
                                    f"{display_name} достиг цели!\n"
                                    f"{direction_icon} <b>{alert['direction']}</b> до ${alert['target_price']:,.2f}\n"
                                    f"Текущая цена: <b>${current_price:,.4f}</b>\n\n"
                                    f"<i>Уведомление выполнено ✅</i>"
                                )

                                # Добавляем в список на удаление
                                completed_alerts.append((user_id, alert['id']))

                            except Exception as e:
                                print(f"❌ Ошибка отправки уведомления пользователю {user_id}: {e}")

            # Удаляем выполненные уведомления
            if completed_alerts:
                alerts_storage.cleanup_completed_alerts(completed_alerts)
                print(f"🗑️ Удалено {len(completed_alerts)} выполненных уведомлений")

            # Ждем перед следующей проверкой
            await asyncio.sleep(Config.ALERT_INTERVAL)

        except Exception as e:
            print(f"❌ Ошибка в задаче проверки уведомлений: {e}")
            await asyncio.sleep(60)


# ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ =====

def register_handlers(dp, bot_instance):
    """
    Регистрирует все обработчики в диспетчере и запускает фоновые задачи.

    Args:
        dp (Dispatcher): Диспетчер Aiogram
        bot_instance (Bot): Экземпляр бота
    """
    dp.include_router(router)

    # Сохраняем ссылку на бота для фоновой задачи
    global bot
    bot = bot_instance

    # Запускаем фоновую задачу проверки уведомлений
    asyncio.create_task(check_alerts_task())
    print("🚀 Фоновая задача проверки уведомлений запущена")