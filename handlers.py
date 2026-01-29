from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from datetime import datetime

from config import Config
from bybit_client import BybitClient
from keyboards import Keyboards


# Состояния для FSM
class AlertState(StatesGroup):
    waiting_for_price = State()
    waiting_for_custom_price = State()
    waiting_for_symbol = State()


# Создаем роутер
router = Router()

# Глобальные переменные
user_alerts = {}  # user_id -> список алертов
bot = None  # Будет установлено при регистрации

# Инициализация клиента
bybit_client = BybitClient()


# ===== ОСНОВНЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ =====

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
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
    """Показать выбор криптовалют - ЭТОТ ОБРАБОТЧИК БЫЛ УДАЛЕН!"""
    await message.answer(
        "📊 <b>Выберите криптовалюту:</b>\n"
        "Или используйте /price [символ] для любой пары",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "🚀 Популярные")
async def show_popular(message: Message):
    """Показать популярные криптовалюты"""
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

        response += f"<b>{short_name}</b> (${price:,.2f}) {change_icon} {change:+.2f}%\n"

    await message.answer(
        response,
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.message(F.text == "🔔 Мои уведомления")
async def show_my_alerts(message: Message):
    """Показать уведомления пользователя"""
    user_id = message.from_user.id
    alerts = user_alerts.get(user_id, [])

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
                response += f"   📈 Вверх: {counts['up']}\n"
            if counts['down']:
                response += f"   📉 Вниз: {counts['down']}\n"

        response += "\n👇 <b>Используйте кнопки для управления:</b>"

        await message.answer(
            response,
            reply_markup=Keyboards.get_alerts_menu()
        )


@router.message(F.text == "📊 Статистика")
async def show_stats_menu(message: Message):
    """Меню статистики"""
    await message.answer(
        "📈 <b>Выберите криптовалюту для подробной статистики:</b>",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message):
    """Показать настройки"""
    user_id = message.from_user.id
    alert_count = len(user_alerts.get(user_id, []))

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
    """Показать справку"""
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
    """Обработчик команды /price [символ]"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажите символ: /price BTCUSDT")
        return

    symbol = args[1].upper()
    await show_crypto_price(message, symbol)


@router.message(Command("alerts"))
async def cmd_alerts(message: Message):
    """Команда /alerts"""
    await show_my_alerts(message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=Keyboards.get_main_menu()
    )


# ===== ОБРАБОТЧИКИ CALLBACK ДЛЯ КРИПТОВАЛЮТ =====

@router.callback_query(F.data.startswith("crypto_"))
async def handle_crypto_selection(callback: CallbackQuery):
    """Обработка выбора криптовалюты"""
    symbol = callback.data.replace("crypto_", "")

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    await callback.message.edit_text(
        f"⏳ Получаю данные для <b>{display_name}</b>...",
        reply_markup=Keyboards.get_back_button("back_to_crypto")
    )

    await show_crypto_price_callback(callback, symbol)


@router.callback_query(F.data == "all_prices")
async def handle_all_prices(callback: CallbackQuery):
    """Показать все котировки"""
    await callback.message.edit_text("⏳ Получаю все котировки...")

    tickers = await bybit_client.get_multiple_tickers(Config.DEFAULT_PAIRS)

    if not tickers:
        await callback.message.edit_text("❌ Не удалось получить данные")
        return

    response = "<b>💰 Все котировки:</b>\n\n"

    for symbol, ticker in tickers.items():
        price = float(ticker['lastPrice'])
        change = float(ticker['price24hPcnt']) * 100
        change_icon = "🟢" if change > 0 else "🔴"

        # Находим короткое имя
        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
        display_name = short_name[0] if short_name else symbol

        response += f"<b>{display_name}</b>: ${price:,.2f} {change_icon} {change:+.2f}%\n"

    await callback.message.edit_text(
        response,
        reply_markup=Keyboards.get_back_button("back_to_crypto")
    )


@router.callback_query(F.data.startswith("detail_"))
async def handle_detail(callback: CallbackQuery):
    """Подробная информация о крипте"""
    symbol = callback.data.replace("detail_", "")

    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await callback.answer("❌ Не удалось получить данные")
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

💰 <b>Цена:</b> ${price:,.2f}
📈 <b>Изменение 24ч:</b> {change:+.2f}%
⬆️ <b>Максимум 24ч:</b> ${high:,.2f}
⬇️ <b>Минимум 24ч:</b> ${low:,.2f}
💎 <b>Объем 24ч:</b> ${volume:,.0f}
📅 <b>Цена открытия:</b> ${float(ticker['prevPrice24h']):,.2f}
🔄 <b>Диапазон:</b> ${high - low:,.2f}

<i>Данные с биржи Bybit</i>
    """

    await callback.message.edit_text(
        response,
        reply_markup=Keyboards.get_price_actions(symbol)
    )


@router.callback_query(F.data.startswith("chart_"))
async def handle_chart(callback: CallbackQuery):
    """График (текстовый)"""
    symbol = callback.data.replace("chart_", "")

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    await callback.message.edit_text(
        f"📈 <b>График {display_name}</b>\n\n"
        f"🚧 <i>Функция графиков в разработке...</i>\n\n"
        f"Скоро здесь будут:\n"
        f"• Свечные графики\n"
        f"• Трендовые линии\n"
        f"• Индикаторы RSI, MACD\n"
        f"• Уровни поддержки/сопротивления",
        reply_markup=Keyboards.get_back_button(f"back_to_price_{symbol}")
    )


@router.callback_query(F.data.startswith("fav_"))
async def handle_favorite(callback: CallbackQuery):
    """Добавить в избранное"""
    symbol = callback.data.replace("fav_", "")

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    await callback.answer(f"✅ {display_name} добавлен в избранное!")


# ===== ОБРАБОТЧИКИ ДЛЯ УВЕДОМЛЕНИЙ =====

@router.callback_query(F.data.startswith("alert_"))
async def handle_alert_setup(callback: CallbackQuery):
    """Настройка уведомления"""
    symbol = callback.data.replace("alert_", "")

    # Находим короткое имя
    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol]
    display_name = short_name[0] if short_name else symbol

    # Получаем текущую цену
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await callback.answer("❌ Не удалось получить данные")
        return

    current_price = float(ticker['lastPrice'])

    response = f"""
🔔 <b>Настройка уведомления для {display_name}</b>

💰 Текущая цена: <b>${current_price:,.2f}</b>

👇 <b>Выберите тип уведомления:</b>
• 📈 Выше на 5% - когда вырастет на 5%
• 📉 Ниже на 5% - когда упадет на 5%
• 📈 Выше на 10% - когда вырастет на 10%
• 📉 Ниже на 10% - когда упадет на 10%
• ⚙️ Своя цена - введите свою цену
    """

    await callback.message.edit_text(
        response,
        reply_markup=Keyboards.get_alert_setup(symbol)
    )


@router.callback_query(F.data == "new_alert")
async def handle_new_alert(callback: CallbackQuery):
    """Создание нового уведомления из меню уведомлений"""
    await callback.message.edit_text(
        "🔔 <b>Создание нового уведомления</b>\n\n"
        "👇 <b>Выберите криптовалюту:</b>",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.callback_query(F.data == "new_alert_from_select")
async def handle_new_alert_from_select(callback: CallbackQuery):
    """Создание уведомления из выбора крипты"""
    await callback.message.edit_text(
        "🔔 <b>Создание нового уведомления</b>\n\n"
        "👇 <b>Выберите криптовалюту:</b>",
        reply_markup=Keyboards.get_crypto_selection()
    )


@router.callback_query(F.data == "list_alerts")
async def handle_list_alerts(callback: CallbackQuery):
    """Показать список уведомлений с управлением"""
    user_id = callback.from_user.id
    alerts = user_alerts.get(user_id, [])

    if not alerts:
        await callback.message.edit_text(
            "📭 <b>У вас нет активных уведомлений</b>\n\n"
            "Нажмите '➕ Новое уведомление' чтобы создать",
            reply_markup=Keyboards.get_alerts_menu()
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

    await callback.message.edit_text(
        response,
        reply_markup=Keyboards.get_alerts_menu()
    )


@router.callback_query(F.data.startswith("alert_up_percent_"))
async def handle_alert_up_percent(callback: CallbackQuery):
    """Установить уведомление на рост в процентах"""
    data_parts = callback.data.replace("alert_up_percent_", "").split("_")
    symbol = data_parts[0]
    percent = float(data_parts[1])

    # Получаем текущую цену
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await callback.answer("❌ Не удалось получить данные")
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

    await callback.message.edit_text(
        f"✅ <b>Уведомление #{alert_id} установлено!</b>\n\n"
        f"Криптовалюта: <b>{short_name}</b>\n"
        f"Тип: 📈 <b>Выше на {percent}%</b>\n"
        f"Текущая цена: <b>${current_price:,.2f}</b>\n"
        f"Целевая цена: <b>${target_price:,.2f}</b>\n\n"
        f"Я уведомлю вас, когда цена достигнет цели!",
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data.startswith("alert_down_percent_"))
async def handle_alert_down_percent(callback: CallbackQuery):
    """Установить уведомление на падение в процентах"""
    data_parts = callback.data.replace("alert_down_percent_", "").split("_")
    symbol = data_parts[0]
    percent = float(data_parts[1])

    # Получаем текущую цену
    ticker = await bybit_client.get_ticker(symbol)
    if not ticker:
        await callback.answer("❌ Не удалось получить данные")
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

    await callback.message.edit_text(
        f"✅ <b>Уведомление #{alert_id} установлено!</b>\n\n"
        f"Криптовалюта: <b>{short_name}</b>\n"
        f"Тип: 📉 <b>Ниже на {percent}%</b>\n"
        f"Текущая цена: <b>${current_price:,.2f}</b>\n"
        f"Целевая цена: <b>${target_price:,.2f}</b>\n\n"
        f"Я уведомлю вас, когда цена достигнет цели!",
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data.startswith("alert_custom_"))
async def handle_alert_custom(callback: CallbackQuery, state: FSMContext):
    """Запрос своей цены для уведомления"""
    symbol = callback.data.replace("alert_custom_", "")

    # Сохраняем данные в состоянии
    await state.update_data(symbol=symbol)
    await state.set_state(AlertState.waiting_for_custom_price)

    # Получаем текущую цену для справки
    ticker = await bybit_client.get_ticker(symbol)
    if ticker:
        current_price = float(ticker['lastPrice'])

        short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

        await callback.message.edit_text(
            f"💰 <b>Установка своей цены для {short_name}</b>\n\n"
            f"Текущая цена: <b>${current_price:,.2f}</b>\n\n"
            f"<b>Введите желаемую цену:</b>\n"
            f"• Для уведомления о росте - цена ВЫШЕ текущей\n"
            f"• Для уведомления о падении - цена НИЖЕ текущей\n\n"
            f"Пример: <code>50000</code> или <code>2500.50</code>\n\n"
            f"Для отмены нажмите /cancel",
            reply_markup=Keyboards.get_cancel_keyboard(f"cancel_custom_{symbol}")
        )
    else:
        await callback.answer("❌ Не удалось получить текущую цену")


@router.callback_query(F.data.startswith("cancel_custom_"))
async def handle_cancel_custom(callback: CallbackQuery, state: FSMContext):
    """Отмена установки своей цены"""
    symbol = callback.data.replace("cancel_custom_", "")
    await state.clear()

    short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == symbol][0]

    await callback.message.edit_text(
        f"❌ Установка уведомления для {short_name} отменена",
        reply_markup=Keyboards.get_back_button(f"back_to_price_{symbol}")
    )


@router.message(AlertState.waiting_for_custom_price)
async def process_custom_price(message: Message, state: FSMContext):
    """Обработка введенной своей цены"""
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
Текущая цена: <b>${current_price:,.2f}</b>
Целевая цена: <b>${target_price:,.2f}</b>

Я уведомлю вас, когда цена достигнет цели!
        """

        await message.answer(
            response,
            reply_markup=Keyboards.get_main_menu()
        )

        await state.clear()

    except ValueError:
        await message.answer("❌ Неверный формат цены. Введите число, например: 50000 или 2500.50")


@router.callback_query(F.data.startswith("delete_alert_"))
async def handle_delete_alert(callback: CallbackQuery):
    """Удалить конкретное уведомление"""
    try:
        alert_id = int(callback.data.replace("delete_alert_", ""))
        user_id = callback.from_user.id

        if user_id in user_alerts:
            # Ищем уведомление с таким ID
            alert_to_delete = None
            for alert in user_alerts[user_id]:
                if alert['id'] == alert_id:
                    alert_to_delete = alert
                    break

            if alert_to_delete:
                # Находим короткое имя
                short_name = [k for k, v in Config.POPULAR_CRYPTO.items() if v == alert_to_delete['symbol']]
                display_name = short_name[0] if short_name else alert_to_delete['symbol']

                # Удаляем уведомление
                user_alerts[user_id].remove(alert_to_delete)

                # Если уведомлений не осталось, удаляем пользователя
                if not user_alerts[user_id]:
                    del user_alerts[user_id]

                await callback.message.edit_text(
                    f"🗑️ <b>Уведомление #{alert_id} удалено</b>\n\n"
                    f"Криптовалюта: {display_name}\n"
                    f"Цель: ${alert_to_delete['target_price']:,.2f}",
                    reply_markup=Keyboards.get_back_button("back_to_alerts_list")
                )
            else:
                await callback.answer("❌ Уведомление не найдено")
        else:
            await callback.answer("❌ У вас нет уведомлений")

    except ValueError:
        await callback.answer("❌ Неверный ID уведомления")


@router.callback_query(F.data == "clear_alerts")
async def handle_clear_alerts(callback: CallbackQuery):
    """Очистить все уведомления"""
    user_id = callback.from_user.id

    if user_id in user_alerts:
        alert_count = len(user_alerts[user_id])
        del user_alerts[user_id]

        await callback.message.edit_text(
            f"🗑️ <b>Удалено {alert_count} уведомлений</b>\n\n"
            f"Все ваши уведомления были очищены.",
            reply_markup=Keyboards.get_back_button("back_to_main")
        )
    else:
        await callback.answer("✅ У вас нет уведомлений")


@router.callback_query(F.data == "back_to_alerts_list")
async def handle_back_to_alerts_list(callback: CallbackQuery):
    """Вернуться к списку уведомлений"""
    await handle_list_alerts(callback)


# ===== ОБРАБОТЧИКИ КНОПОК НАЗАД =====

@router.callback_query(F.data.startswith("back_to_"))
async def handle_back_button(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки Назад"""
    back_to = callback.data

    if back_to == "back_to_main":
        await state.clear()
        await callback.message.edit_text(
            "↩️ Возвращаемся в главное меню...",
            reply_markup=None
        )
        await callback.message.answer(
            "🏠 <b>Главное меню</b>",
            reply_markup=Keyboards.get_main_menu()
        )

    elif back_to == "back_to_crypto":
        await callback.message.edit_text(
            "📊 <b>Выберите криптовалюту:</b>",
            reply_markup=Keyboards.get_crypto_selection()
        )

    elif back_to.startswith("back_to_price_"):
        symbol = back_to.replace("back_to_price_", "")
        await show_crypto_price_callback(callback, symbol)

    elif back_to == "alert_settings":
        await callback.message.edit_text(
            "⚙️ <b>Настройки уведомлений</b>\n\n"
            "🚧 <i>Функция в разработке...</i>",
            reply_markup=Keyboards.get_back_button("back_to_main")
        )


# ===== ОБРАБОТЧИКИ НАСТРОЕК =====

@router.callback_query(F.data == "interval_setting")
async def handle_interval_setting(callback: CallbackQuery):
    """Настройка интервала"""
    await callback.message.edit_text(
        f"⏰ <b>Текущий интервал проверки: {Config.ALERT_INTERVAL} сек</b>\n\n"
        f"🚧 <i>Изменение интервала в разработке...</i>\n\n"
        f"Сейчас бот проверяет уведомления каждые {Config.ALERT_INTERVAL} секунд",
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data == "theme_setting")
async def handle_theme_setting(callback: CallbackQuery):
    """Настройка темы"""
    await callback.message.edit_text(
        "🎨 <b>Настройки темы</b>\n\n"
        "🚧 <i>Функция в разработке...</i>\n\n"
        "Скоро здесь можно будет выбрать:\n"
        "• Светлая/темная тема\n"
        "• Цветовые схемы\n"
        "• Шрифты",
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data == "notify_setting")
async def handle_notify_setting(callback: CallbackQuery):
    """Настройка уведомлений"""
    await callback.message.edit_text(
        "🔕 <b>Настройки уведомлений</b>\n\n"
        "🚧 <i>Функция в разработке...</i>\n\n"
        "Скоро здесь можно будет настроить:\n"
        "• Типы уведомлений (звук, вибрация)\n"
        "• Время тишины\n"
        "• Приоритеты",
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


@router.callback_query(F.data == "export_data")
async def handle_export_data(callback: CallbackQuery):
    """Экспорт данных"""
    await callback.message.edit_text(
        "💾 <b>Экспорт данных</b>\n\n"
        "🚧 <i>Функция в разработке...</i>\n\n"
        "Скоро здесь можно будет:\n"
        "• Экспортировать историю уведомлений\n"
        "• Скачать данные в CSV/Excel\n"
        "• Сохранить настройки",
        reply_markup=Keyboards.get_back_button("back_to_main")
    )


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def save_alert(user_id: int, symbol: str, target_price: float, current_price: float, direction: str) -> int:
    """Сохранить уведомление в хранилище"""
    if user_id not in user_alerts:
        user_alerts[user_id] = []

    # Генерируем ID (максимальный существующий + 1)
    if user_alerts[user_id]:
        alert_id = max(alert['id'] for alert in user_alerts[user_id]) + 1
    else:
        alert_id = 1

    alert = {
        'id': alert_id,
        'symbol': symbol,
        'target_price': target_price,
        'current_price': current_price,
        'direction': direction,
        'user_id': user_id,
        'created_at': datetime.now().isoformat()
    }

    user_alerts[user_id].append(alert)
    return alert_id


async def show_crypto_price(message, symbol: str):
    """Показать цену криптовалюты (для сообщений)"""
    ticker = await bybit_client.get_ticker(symbol)

    if not ticker:
        await message.answer(f"❌ Не удалось получить данные для {symbol}")
        return

    await format_and_send_price(message, symbol, ticker, is_callback=False)


async def show_crypto_price_callback(callback: CallbackQuery, symbol: str):
    """Показать цену криптовалюты (для callback)"""
    ticker = await bybit_client.get_ticker(symbol)

    if not ticker:
        await callback.message.edit_text(f"❌ Не удалось получить данные для {symbol}")
        return

    await format_and_send_price(callback.message, symbol, ticker, is_callback=True)


async def format_and_send_price(message_obj, symbol: str, ticker: dict, is_callback: bool = False):
    """Форматировать и отправить цену"""
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

💰 <b>Цена:</b> ${price:,.2f}
{change_icon} <b>Изменение 24ч:</b> {change_color} {change:+.2f}%
⬆️ <b>Макс 24ч:</b> ${high:,.2f}
⬇️ <b>Мин 24ч:</b> ${low:,.2f}
📊 <b>Объем 24ч:</b> ${float(ticker['volume24h']):,.0f}

<i>Данные с биржи Bybit</i>
    """

    if is_callback:
        await message_obj.edit_text(
            response,
            reply_markup=Keyboards.get_price_actions(symbol)
        )
    else:
        await message_obj.answer(
            response,
            reply_markup=Keyboards.get_price_actions(symbol)
        )


# ===== ФУНКЦИЯ ДЛЯ ПРОВЕРКИ УВЕДОМЛЕНИЙ =====

async def check_alerts_task():
    """Фоновая задача проверки уведомлений"""
    while True:
        try:
            for user_id, alerts in list(user_alerts.items()):
                alerts_to_remove = []

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
                        elif alert['direction'] == "ВНИЗ" and current_price <= alert['target_price']:
                            target_reached = True

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
                                    f"Текущая цена: <b>${current_price:,.2f}</b>\n\n"
                                    f"<i>Уведомление выполнено ✅</i>"
                                )

                                # Помечаем для удаления
                                alerts_to_remove.append(alert)

                            except Exception as e:
                                print(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

                # Удаляем выполненные уведомления
                for alert in alerts_to_remove:
                    if alert in alerts:
                        alerts.remove(alert)

                # Если уведомлений не осталось, удаляем пользователя
                if not alerts:
                    del user_alerts[user_id]

            # Ждем перед следующей проверкой
            await asyncio.sleep(Config.ALERT_INTERVAL)

        except Exception as e:
            print(f"Ошибка в задаче проверки уведомлений: {e}")
            await asyncio.sleep(60)


# ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ =====

def register_handlers(dp, bot_instance):
    """Регистрация всех обработчиков"""
    dp.include_router(router)

    # Сохраняем ссылку на бота для фоновой задачи
    global bot
    bot = bot_instance

    # Запускаем фоновую задачу проверки уведомлений
    asyncio.create_task(check_alerts_task())