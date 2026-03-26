from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from decimal import Decimal

from database.repositories import AssetRepository, PortfolioRepository
from keyboards import Keyboards
from logger import get_logger, log_function_call
from services.price_service import price_service
from services.portfolio_service import portfolio_service
from utils import parse_decimal, format_money, validate_positive_decimal, format_percent
from callback_utils import safe_callback_answer, safe_edit_message

router = Router()
logger = get_logger('assets')


class AssetState(StatesGroup):
    """Состояния для добавления актива"""
    waiting_for_symbol = State()
    waiting_for_quantity = State()
    waiting_for_confirmation = State()
    waiting_for_edit_quantity = State()


@router.callback_query(F.data.startswith("add_asset_"))
@log_function_call()
async def add_asset_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления актива"""
    await safe_callback_answer(callback)

    portfolio_id = int(callback.data.replace("add_asset_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await safe_edit_message(
            callback,
            "❌ Портфель не найден",
            reply_markup=Keyboards.get_back_button("back_to_portfolios")
        )
        return

    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(AssetState.waiting_for_symbol)

    await safe_edit_message(
        callback,
        f"➕ <b>Добавление актива в портфель '{portfolio['name']}'</b>\n\n"
        f"Введите ТИКЕР актива (например, SBER, GAZP, YDEX):\n\n"
        f"<i>Только латинские буквы, без поиска по названию</i>",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(AssetState.waiting_for_symbol)
@log_function_call()
async def process_asset_symbol(message: Message, state: FSMContext):
    """Обработка символа актива"""
    symbol = message.text.strip().upper()

    if not symbol or len(symbol) < 1 or len(symbol) > 20:
        await message.answer("❌ Некорректный тикер. Введите правильный тикер (например, SBER):")
        return

    if not all(c.isalnum() or c in ['.', '-', '_'] for c in symbol):
        await message.answer("❌ Тикер должен содержать только буквы, цифры и символы . - _")
        return

    status_msg = await message.answer(f"⏳ Проверяем тикер {symbol} на MOEX...")

    is_valid, info = await price_service.validate_symbol_with_info(symbol)

    if not is_valid or not info:
        await status_msg.edit_text(
            f"❌ Тикер {symbol} не найден на MOEX.\n\n"
            f"Проверьте правильность тикера и попробуйте снова:\n"
            f"• SBER - Сбербанк\n"
            f"• GAZP - Газпром\n"
            f"• YDEX - Яндекс\n",
            reply_markup=Keyboards.get_cancel_keyboard()
        )
        return

    # При добавлении нового актива запрашиваем актуальную цену без кэша
    current_price = await price_service.get_price(symbol, use_cache=False)

    await state.update_data(
        symbol=symbol,
        name=info.get('name', symbol),
        asset_type=info.get('asset_type', 'stock'),
        currency=info.get('currency', 'RUB'),
        current_price=current_price,
        info=info
    )

    if current_price and current_price > 0:
        await state.set_state(AssetState.waiting_for_quantity)

        market_status = "🟢 Биржа открыта" if price_service._is_market_open() else "🔴 Биржа закрыта"

        await status_msg.edit_text(
            f"✅ Найден актив: <b>{info.get('name', symbol)}</b> ({symbol})\n\n"
            f"Тип: {info.get('asset_type_display', 'Акция')}\n"
            f"Валюта: {info.get('currency', 'RUB')}\n"
            f"{market_status}\n\n"
            f"💰 Текущая цена: <b>{format_money(current_price, info.get('currency', 'RUB'))}</b>\n\n"
            f"🔢 Введите количество актива (например, 10 или 0.5):",
            reply_markup=Keyboards.get_cancel_keyboard()
        )
    else:
        await state.update_data(use_manual_price=False)
        await state.set_state(AssetState.waiting_for_quantity)

        await status_msg.edit_text(
            f"✅ Найден актив: <b>{info.get('name', symbol)}</b> ({symbol})\n\n"
            f"Тип: {info.get('asset_type_display', 'Акция')}\n"
            f"Валюта: {info.get('currency', 'RUB')}\n\n"
            f"⚠️ Не удалось получить текущую цену. "
            f"Цена будет определена при следующем обновлении.\n\n"
            f"🔢 Введите количество актива (например, 10 или 0.5):",
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
    data = await state.get_data()

    if data.get('current_price'):
        await show_confirmation(message, state)
    else:
        status_msg = await message.answer("⏳ Получаем актуальную цену...")
        current_price = await price_service.get_price(data['symbol'], use_cache=False)

        if current_price and current_price > 0:
            await state.update_data(current_price=current_price)
            await status_msg.delete()
            await show_confirmation(message, state)
        else:
            await status_msg.edit_text(
                f"❌ Не удалось получить цену для {data['symbol']}.\n\n"
                f"Попробуйте позже или добавьте другой актив.",
                reply_markup=Keyboards.get_cancel_keyboard()
            )


async def show_confirmation(message: Message, state: FSMContext):
    """Показывает подтверждение добавления актива"""
    data = await state.get_data()

    quantity = data['quantity']
    current_price = data['current_price']
    currency = data.get('currency', 'RUB')
    total = quantity * current_price

    await state.set_state(AssetState.waiting_for_confirmation)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_add_asset")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

    await message.answer(
        f"📝 <b>Подтверждение добавления актива</b>\n\n"
        f"Актив: <b>{data['name']}</b> ({data['symbol']})\n"
        f"Количество: <b>{quantity}</b>\n"
        f"Цена: <b>{format_money(current_price, currency)}</b>\n"
        f"Общая стоимость: <b>{format_money(total, currency)}</b>\n\n"
        f"Всё верно?",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_add_asset")
@log_function_call()
async def confirm_add_asset(callback: CallbackQuery, state: FSMContext):
    """Подтверждение добавления актива"""
    await safe_callback_answer(callback)

    data = await state.get_data()

    try:
        asset_id = await AssetRepository.add(
            portfolio_id=data['portfolio_id'],
            symbol=data['symbol'],
            name=data['name'],
            asset_type=data['asset_type'],
            quantity=data['quantity'],
            purchase_price=data['current_price'],
            currency=data.get('currency', 'RUB'),
            sector=data.get('info', {}).get('sector'),
            notes=None
        )

        await state.clear()

        if asset_id:
            await safe_edit_message(
                callback,
                f"✅ <b>Актив успешно добавлен!</b>\n\n"
                f"Актив: {data['name']} ({data['symbol']})\n"
                f"Количество: {data['quantity']}\n"
                f"Цена покупки: {format_money(data['current_price'], data.get('currency', 'RUB'))}",
                reply_markup=Keyboards.get_portfolio_actions(data['portfolio_id'])
            )
        else:
            await safe_edit_message(
                callback,
                "❌ Ошибка добавления актива",
                reply_markup=Keyboards.get_main_menu()
            )
    except Exception as e:
        logger.error(f"Ошибка сохранения актива: {e}")
        await safe_edit_message(
            callback,
            "❌ Ошибка добавления актива",
            reply_markup=Keyboards.get_main_menu()
        )


@router.callback_query(F.data.startswith("list_assets_"))
@log_function_call()
async def list_assets(callback: CallbackQuery):
    """Список активов портфеля"""
    await safe_callback_answer(callback)

    portfolio_id = int(callback.data.replace("list_assets_", ""))
    assets = await AssetRepository.get_portfolio_assets(portfolio_id)

    if not assets:
        await safe_edit_message(
            callback,
            "📭 <b>В портфеле нет активов</b>",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
        return

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

    await safe_edit_message(
        callback,
        f"📋 <b>Активы портфеля:</b>",
        reply_markup=Keyboards.get_assets_list(assets, portfolio_id)
    )


@router.callback_query(F.data.startswith("view_asset_"))
@log_function_call()
async def view_asset(callback: CallbackQuery):
    """Просмотр деталей актива"""
    await safe_callback_answer(callback)

    asset_id = int(callback.data.replace("view_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await safe_edit_message(callback, "❌ Актив не найден")
        return

    details = await portfolio_service.calculate_asset_details(asset_id)

    asset_types = {
        'stock': 'Акция', 'bond': 'Облигация', 'etf': 'ETF',
        'currency': 'Валюта', 'futures': 'Фьючерс', 'other': 'Другое'
    }

    asset_type_name = asset_types.get(asset['asset_type'], asset['asset_type'])
    market_status = "🟢" if price_service._is_market_open() else "🔴"

    response = f"""
💎 <b>{details['name']}</b> ({details['symbol']}) {market_status}

🏷️ Тип: {asset_type_name}
📦 Количество: {details['quantity']}
💵 Валюта: {details['currency']}

💰 Цена покупки: {format_money(details['purchase_price'], details['currency'])}
💎 Текущая цена: {format_money(details['current_price'] or details['purchase_price'], details['currency'])}
📊 Текущая стоимость: {format_money(details['current_value'], details['currency'])}
📈 Прибыль: {format_money(details['profit'], details['currency'])} ({format_percent(details['profit_percent'])})
    """

    if details.get('notes'):
        response += f"\n📝 Заметки: {details['notes']}"

    await safe_edit_message(
        callback,
        response,
        reply_markup=Keyboards.get_asset_actions(asset_id, asset['portfolio_id'])
    )


@router.callback_query(F.data.startswith("refresh_asset_"))
@log_function_call()
async def refresh_asset_price(callback: CallbackQuery):
    """Обновление цены актива (форсированно)"""
    await safe_callback_answer(callback, "🔄 Обновляем цену...")

    asset_id = int(callback.data.replace("refresh_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await safe_edit_message(callback, "❌ Актив не найден")
        return

    current_price = await price_service.get_price(asset['symbol'], use_cache=False)

    if current_price:
        await AssetRepository.update_price(asset_id, current_price)
        await safe_callback_answer(callback, f"✅ Цена обновлена: {format_money(current_price, asset['currency'])}")
    else:
        await safe_callback_answer(callback, "❌ Не удалось обновить цену")

    await view_asset(callback)


@router.callback_query(F.data.startswith("edit_asset_"))
@log_function_call()
async def edit_asset(callback: CallbackQuery):
    """Редактирование актива"""
    await safe_callback_answer(callback)

    asset_id = int(callback.data.replace("edit_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await safe_edit_message(callback, "❌ Актив не найден")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить количество", callback_data=f"edit_asset_quantity_{asset_id}")],
        [InlineKeyboardButton(text="💰 Обновить цену", callback_data=f"refresh_asset_{asset_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_asset_{asset_id}")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"view_asset_{asset_id}")]
    ])

    await safe_edit_message(
        callback,
        f"✏️ <b>Редактирование актива</b>\n\n"
        f"Актив: {asset['name']} ({asset['symbol']})\n"
        f"Текущее количество: {asset['quantity']}\n"
        f"Текущая цена: {format_money(asset['current_price'] or asset['purchase_price'], asset['currency'])}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("edit_asset_quantity_"))
@log_function_call()
async def edit_asset_quantity(callback: CallbackQuery, state: FSMContext):
    """Редактирование количества актива"""
    await safe_callback_answer(callback)

    asset_id = int(callback.data.replace("edit_asset_quantity_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await safe_edit_message(callback, "❌ Актив не найден")
        return

    await state.update_data(asset_id=asset_id)
    await state.set_state(AssetState.waiting_for_edit_quantity)

    await safe_edit_message(
        callback,
        f"✏️ <b>Изменение количества</b>\n\n"
        f"Актив: {asset['name']} ({asset['symbol']})\n"
        f"Текущее количество: {asset['quantity']}\n\n"
        f"Введите новое количество:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(AssetState.waiting_for_edit_quantity)
@log_function_call()
async def process_edit_quantity(message: Message, state: FSMContext):
    """Обработка нового количества"""
    new_quantity = parse_decimal(message.text)

    if not validate_positive_decimal(new_quantity):
        await message.answer("❌ Введите положительное число:")
        return

    data = await state.get_data()
    asset_id = data['asset_id']

    await AssetRepository.update_quantity(asset_id, new_quantity)
    await state.clear()

    await message.answer(
        f"✅ Количество обновлено до {new_quantity}",
        reply_markup=Keyboards.get_back_button(f"view_asset_{asset_id}")
    )


@router.callback_query(F.data.startswith("delete_asset_"))
@log_function_call()
async def delete_asset(callback: CallbackQuery):
    """Удаление актива"""
    await safe_callback_answer(callback)

    asset_id = int(callback.data.replace("delete_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await safe_edit_message(callback, "❌ Актив не найден")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_asset_{asset_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"view_asset_{asset_id}")
        ]
    ])

    await safe_edit_message(
        callback,
        f"🗑️ <b>Удаление актива</b>\n\n"
        f"Вы уверены, что хотите удалить актив {asset['symbol']}?",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("confirm_delete_asset_"))
@log_function_call()
async def confirm_delete_asset(callback: CallbackQuery):
    """Подтверждение удаления актива"""
    await safe_callback_answer(callback)

    asset_id = int(callback.data.replace("confirm_delete_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await safe_edit_message(callback, "❌ Актив не найден")
        return

    portfolio_id = asset['portfolio_id']

    if await AssetRepository.delete(asset_id):
        await safe_edit_message(
            callback,
            f"🗑️ <b>Актив {asset['symbol']} удален</b>",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
    else:
        await safe_edit_message(
            callback,
            "❌ Ошибка удаления актива",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )