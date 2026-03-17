from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal

from database.repositories import AssetRepository, PortfolioRepository
from keyboards import Keyboards
from logger import get_logger, log_function_call
from services.price_service import price_service
from services.portfolio_service import portfolio_service
from utils import parse_decimal, format_money, format_percent, validate_positive_decimal

router = Router()
logger = get_logger('assets')


class AssetState(StatesGroup):
    """Состояния для добавления актива"""
    waiting_for_symbol = State()
    waiting_for_name = State()
    waiting_for_type = State()
    waiting_for_quantity = State()
    waiting_for_price = State()
    waiting_for_currency = State()
    waiting_for_notes = State()
    waiting_for_search_query = State()


@router.callback_query(F.data.startswith("add_asset_"))
@log_function_call()
async def add_asset_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления актива"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("add_asset_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await callback.message.edit_text("❌ Портфель не найден")
        return

    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(AssetState.waiting_for_symbol)

    await callback.message.edit_text(
        f"➕ <b>Добавление актива в портфель '{portfolio['name']}'</b>\n\n"
        f"Введите тикер актива (например, SBER, GAZP, YNDX):\n\n"
        f"<i>Можно использовать поиск по названию 🔍</i>",
        reply_markup=Keyboards.get_asset_search(portfolio_id)
    )


@router.callback_query(F.data.startswith("search_asset_"))
@log_function_call()
async def search_asset_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска актива"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("search_asset_", ""))
    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(AssetState.waiting_for_search_query)

    await callback.message.edit_text(
        "🔍 <b>Поиск актива на MOEX</b>\n\n"
        "Введите название или часть названия актива для поиска:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(AssetState.waiting_for_search_query)
@log_function_call()
async def process_search_query(message: Message, state: FSMContext):
    """Обработка поискового запроса"""
    query = message.text.strip()

    if len(query) < 2:
        await message.answer("❌ Слишком короткий запрос. Введите минимум 2 символа:")
        return

    await message.answer(f"🔍 Ищем активы по запросу '{query}'...")

    # Поиск на MOEX
    results = await price_service.search_assets(query, limit=15)

    if not results:
        await message.answer(
            f"❌ Ничего не найдено по запросу '{query}'\n\n"
            f"Попробуйте другой запрос или введите тикер вручную:",
            reply_markup=Keyboards.get_cancel_keyboard()
        )
        return

    # Формируем клавиатуру с результатами
    buttons = []
    for asset in results[:10]:
        # Безопасное получение имени с проверкой на None
        asset_name = asset.get('name', '')
        if asset_name is None:
            asset_name = ''

        # Обрезаем имя до 40 символов, если оно есть
        display_name = asset_name[:40] if asset_name else "Без названия"

        # Безопасное получение символа
        symbol = asset.get('symbol', '???')
        if symbol is None:
            symbol = '???'

        asset_type = {
            'stock': '📈',
            'bond': '📊',
            'etf': '📦',
            'currency': '💵',
            'futures': '📉',
            'other': '📄'
        }.get(asset.get('asset_type'), '📄')

        buttons.append([
            InlineKeyboardButton(
                text=f"{asset_type} {symbol} - {display_name}",
                callback_data=f"select_search_{symbol}|{display_name}|{asset.get('asset_type', 'other')}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="↩️ Ввести вручную", callback_data="back_to_symbol")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"🔍 <b>Найдено {len(results)} активов:</b>\n\n"
        f"Выберите подходящий:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("select_search_"))
@log_function_call()
async def select_search_result(callback: CallbackQuery, state: FSMContext):
    """Выбор результата поиска"""
    await callback.answer()

    data = callback.data.replace("select_search_", "").split("|")

    # Проверяем, что получили достаточно данных
    if len(data) < 3:
        await callback.message.edit_text("❌ Ошибка при выборе актива")
        return

    symbol = data[0] if data[0] != 'None' else 'UNKNOWN'
    name = data[1] if data[1] and data[1] != 'None' else symbol
    asset_type = data[2] if data[2] != 'None' else 'other'

    await state.update_data(
        symbol=symbol,
        name=name,
        asset_type=asset_type
    )
    await state.set_state(AssetState.waiting_for_quantity)

    await callback.message.edit_text(
        f"✅ Выбран актив: <b>{name}</b> ({symbol})\n\n"
        f"🔢 Введите количество актива:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.callback_query(F.data == "back_to_symbol")
@log_function_call()
async def back_to_symbol(callback: CallbackQuery, state: FSMContext):
    """Возврат к вводу символа"""
    await callback.answer()
    await state.set_state(AssetState.waiting_for_symbol)

    data = await state.get_data()
    portfolio_id = data.get('portfolio_id')

    await callback.message.edit_text(
        "➕ <b>Добавление актива</b>\n\n"
        "Введите тикер актива (например, SBER, GAZP, YNDX):",
        reply_markup=Keyboards.get_asset_search(portfolio_id)
    )


@router.message(AssetState.waiting_for_symbol)
@log_function_call()
async def process_asset_symbol(message: Message, state: FSMContext):
    """Обработка символа актива"""
    symbol = message.text.strip().upper()

    # Валидация
    if not symbol or len(symbol) < 2:
        await message.answer("❌ Слишком короткий символ. Попробуйте еще раз:")
        return

    # Проверяем существование на MOEX
    await message.answer(f"🔍 Проверяем символ {symbol} на MOEX...")

    is_valid = await price_service.validate_symbol(symbol)

    if not is_valid:
        await message.answer(
            f"❌ Символ {symbol} не найден на MOEX.\n\n"
            f"Попробуйте другой символ или воспользуйтесь поиском:",
            reply_markup=Keyboards.get_asset_search((await state.get_data()).get('portfolio_id'))
        )
        return

    # Получаем информацию об активе
    info = await price_service.get_asset_info(symbol)

    if info:
        name = info.get('name')
        if name is None:
            name = symbol
        asset_type = info.get('asset_type', 'stock')
    else:
        name = symbol
        asset_type = 'stock'

    await state.update_data(
        symbol=symbol,
        name=name,
        asset_type=asset_type
    )
    await state.set_state(AssetState.waiting_for_quantity)

    await message.answer(
        f"✅ Найден актив: <b>{name}</b> ({symbol})\n\n"
        f"🔢 Введите количество актива:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(AssetState.waiting_for_quantity)
@log_function_call()
async def process_asset_quantity(message: Message, state: FSMContext):
    """Обработка количества актива"""
    quantity = parse_decimal(message.text)

    if not validate_positive_decimal(quantity):
        await message.answer("❌ Введите положительное число (например, 10 или 0.5):")
        return

    await state.update_data(quantity=quantity)
    await state.set_state(AssetState.waiting_for_price)

    await message.answer(
        "💰 Введите цену покупки за единицу:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(AssetState.waiting_for_price)
@log_function_call()
async def process_asset_price(message: Message, state: FSMContext):
    """Обработка цены покупки"""
    price = parse_decimal(message.text)

    if not validate_positive_decimal(price):
        await message.answer("❌ Введите положительное число (например, 250 или 1500.50):")
        return

    await state.update_data(purchase_price=price)
    await state.set_state(AssetState.waiting_for_currency)

    await message.answer(
        "💵 Выберите валюту:",
        reply_markup=Keyboards.get_currencies()
    )


@router.callback_query(AssetState.waiting_for_currency, F.data.startswith("currency_"))
@log_function_call()
async def process_asset_currency(callback: CallbackQuery, state: FSMContext):
    """Обработка валюты"""
    await callback.answer()

    currency = callback.data.replace("currency_", "")
    await state.update_data(currency=currency)
    await state.set_state(AssetState.waiting_for_notes)

    await callback.message.edit_text(
        "📝 Введите заметки (необязательно) или отправьте /skip:",
        reply_markup=Keyboards.get_skip_keyboard()
    )


@router.message(AssetState.waiting_for_notes)
@log_function_call()
async def process_asset_notes(message: Message, state: FSMContext):
    """Обработка заметок и сохранение актива"""
    if message.text == "/skip":
        notes = None
    else:
        notes = message.text.strip()

    data = await state.get_data()

    # Сохраняем актив
    asset_id = await AssetRepository.add(
        portfolio_id=data['portfolio_id'],
        symbol=data['symbol'],
        name=data['name'],
        asset_type=data['asset_type'],
        quantity=data['quantity'],
        purchase_price=data['purchase_price'],
        currency=data.get('currency', 'RUB'),
        notes=notes
    )

    await state.clear()

    if asset_id:
        await message.answer(
            f"✅ <b>Актив успешно добавлен!</b>\n\n"
            f"Актив: {data['name']} ({data['symbol']})\n"
            f"Количество: {data['quantity']}\n"
            f"Цена покупки: {format_money(data['purchase_price'], data.get('currency', 'RUB'))}",
            reply_markup=Keyboards.get_portfolio_actions(data['portfolio_id'])
        )
    else:
        await message.answer(
            "❌ Ошибка добавления актива",
            reply_markup=Keyboards.get_main_menu()
        )


@router.callback_query(F.data.startswith("list_assets_"))
@log_function_call()
async def list_assets(callback: CallbackQuery):
    """Список активов портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("list_assets_", ""))
    assets = await AssetRepository.get_portfolio_assets(portfolio_id)

    if not assets:
        await callback.message.edit_text(
            "📭 <b>В портфеле нет активов</b>",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
        return

    # Обновляем цены
    await price_service.update_portfolio_prices(portfolio_id)
    assets = await AssetRepository.get_portfolio_assets(portfolio_id)

    # Рассчитываем прибыль для каждого актива
    for asset in assets:
        quantity = asset['quantity']
        purchase_price = asset['purchase_price']
        current_price = asset['current_price'] or purchase_price
        cost = quantity * purchase_price
        current_value = quantity * current_price
        profit = current_value - cost
        profit_percent = (profit / cost * 100) if cost > 0 else Decimal('0')
        asset['profit'] = profit
        asset['profit_percent'] = profit_percent

    await callback.message.edit_text(
        f"📋 <b>Активы портфеля:</b>",
        reply_markup=Keyboards.get_assets_list(assets, portfolio_id)
    )


@router.callback_query(F.data.startswith("view_asset_"))
@log_function_call()
async def view_asset(callback: CallbackQuery):
    """Просмотр деталей актива"""
    await callback.answer()

    asset_id = int(callback.data.replace("view_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await callback.message.edit_text("❌ Актив не найден")
        return

    # Детальный расчет
    details = await portfolio_service.calculate_asset_details(asset_id, update_price=True)

    asset_types = {
        'stock': 'Акция',
        'bond': 'Облигация',
        'etf': 'ETF',
        'currency': 'Валюта',
        'futures': 'Фьючерс',
        'other': 'Другое'
    }

    asset_type_name = asset_types.get(asset['asset_type'], asset['asset_type'])

    # Формируем сообщение
    response = f"""
💎 <b>{details['name']}</b> ({details['symbol']})

🏷️ Тип: {asset_type_name}
📦 Количество: {details['quantity']}
💵 Валюта: {details['currency']}

💰 Цена покупки: {format_money(details['purchase_price'], details['currency'])}
💎 Текущая цена: {format_money(details['current_price'] or details['purchase_price'], details['currency'])}
📊 Текущая стоимость: {format_money(details['current_value'], details['currency'])}
📈 Прибыль: {format_money(details['profit'], details['currency'])} ({format_percent(details['profit_percent'])})
    """

    # Добавляем изменения за периоды
    if details.get('price_change_1d') != 0:
        response += f"\n📅 Изменение за день: {format_percent(details['price_change_1d'])}"
    if details.get('price_change_1w') != 0:
        response += f"\n📅 Изменение за неделю: {format_percent(details['price_change_1w'])}"

    # Добавляем цели
    response += f"""

🎯 Цели:
• Безубыточность: {format_money(details['break_even'], details['currency'])}
• Удвоение: {format_money(details['required_for_double'], details['currency'])}
• Падение вдвое: {format_money(details['required_for_half'], details['currency'])}
    """

    if details.get('notes'):
        response += f"\n📝 Заметки: {details['notes']}"

    await callback.message.edit_text(
        response,
        reply_markup=Keyboards.get_asset_actions(asset_id, asset['portfolio_id'])
    )


@router.callback_query(F.data.startswith("refresh_asset_"))
@log_function_call()
async def refresh_asset_price(callback: CallbackQuery):
    """Обновление цены актива"""
    await callback.answer("🔄 Обновляем цену...")

    asset_id = int(callback.data.replace("refresh_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await callback.message.edit_text("❌ Актив не найден")
        return

    # Обновляем цену
    current_price = await price_service.get_price(asset['symbol'], use_cache=False)

    if current_price:
        await AssetRepository.update_price(asset_id, current_price)
        await callback.answer(f"✅ Цена обновлена: {format_money(current_price, asset['currency'])}")
    else:
        await callback.answer("❌ Не удалось обновить цену")

    # Возвращаемся к просмотру актива
    await view_asset(callback)


@router.callback_query(F.data.startswith("delete_asset_"))
@log_function_call()
async def delete_asset(callback: CallbackQuery):
    """Удаление актива"""
    await callback.answer()

    asset_id = int(callback.data.replace("delete_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await callback.message.edit_text("❌ Актив не найден")
        return

    portfolio_id = asset['portfolio_id']

    if await AssetRepository.delete(asset_id):
        await callback.message.edit_text(
            f"🗑️ <b>Актив {asset['symbol']} удален</b>",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка удаления актива",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )


@router.callback_query(F.data.startswith("more_assets_"))
@log_function_call()
async def more_assets(callback: CallbackQuery):
    """Показать еще активы"""
    await callback.answer()

    parts = callback.data.replace("more_assets_", "").split("_")
    portfolio_id = int(parts[0])
    offset = int(parts[1])

    assets = await AssetRepository.get_portfolio_assets(portfolio_id)

    # Рассчитываем прибыль
    for asset in assets[offset:offset + 10]:
        quantity = asset['quantity']
        purchase_price = asset['purchase_price']
        current_price = asset['current_price'] or purchase_price
        cost = quantity * purchase_price
        current_value = quantity * current_price
        profit = current_value - cost
        profit_percent = (profit / cost * 100) if cost > 0 else Decimal('0')
        asset['profit'] = profit
        asset['profit_percent'] = profit_percent

    # Здесь можно реализовать пагинацию
    await callback.message.edit_text(
        f"📋 <b>Активы портфеля (стр. {offset // 10 + 1}):</b>",
        reply_markup=Keyboards.get_assets_list(assets[offset:offset + 10], portfolio_id)
    )