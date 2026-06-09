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
from utils import parse_decimal, format_money, validate_positive_decimal, format_percent, format_quantity
from callback_utils import safe_callback_answer, safe_edit_message, auto_delete_message, cleanup_and_answer
from constants import SYSTEM_COMMANDS

router = Router()
logger = get_logger('assets')


class AssetState(StatesGroup):
    """Состояния для добавления актива"""
    waiting_for_symbol = State()
    waiting_for_quantity = State()
    waiting_for_price_choice = State()
    waiting_for_manual_price = State()
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

    await state.update_data(
        portfolio_id=portfolio_id,
        last_bot_msg_id=callback.message.message_id
    )
    await state.set_state(AssetState.waiting_for_symbol)

    await safe_edit_message(
        callback,
        f"➕ <b>Добавление актива в портфель '{portfolio['name']}'</b>\n\n"
        f"Введите ТИКЕР актива (например, SBER, GAZP, YDEX):\n\n"
        f"<i>Только латинские буквы, без поиска по названию</i>",
        reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}")
    )


@router.message(AssetState.waiting_for_symbol)
@log_function_call()
async def process_asset_symbol(message: Message, state: FSMContext):
    """Обработка символа актива"""
    symbol = message.text.strip().upper()
    data = await state.get_data()
    portfolio_id = data.get('portfolio_id')

    if not symbol or len(symbol) < 1 or len(symbol) > 20:
        await cleanup_and_answer(message, state, "❌ Некорректный тикер. Введите правильный тикер (например, SBER):",
                                 reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}"))
        return

    if not all(c.isalnum() or c in ['.', '-', '_'] for c in symbol):
        await cleanup_and_answer(message, state, "❌ Тикер должен содержать только буквы, цифры и символы . - _",
                                 reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}"))
        return

    status_msg = await cleanup_and_answer(message, state, f"⏳ Проверяем тикер {symbol} на MOEX...")

    is_valid, info = await price_service.validate_symbol_with_info(symbol)

    if not is_valid or not info:
        await status_msg.edit_text(
            f"❌ Тикер {symbol} не найден на MOEX.\n\n"
            f"Проверьте правильность тикера и попробуйте снова:\n"
            f"• SBER - Сбербанк\n"
            f"• GAZP - Газпром\n"
            f"• YDEX - Яндекс\n",
            reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}")
        )
        return

    current_price = await price_service.get_price(symbol, use_cache=False)

    await state.update_data(
        symbol=symbol,
        name=info.get('name', symbol),
        asset_type=info.get('asset_type', 'stock'),
        currency=info.get('currency', 'RUB'),
        current_price=current_price,
        info=info
    )

    await state.set_state(AssetState.waiting_for_quantity)

    market_status = "🟢 Биржа открыта" if price_service._is_market_open() else "🔴 Биржа закрыта"
    price_text = format_money(current_price, info.get('currency', 'RUB')) if current_price else "не удалось получить"

    await status_msg.edit_text(
        f"✅ Найден актив: <b>{info.get('name', symbol)}</b> ({symbol})\n\n"
        f"Тип: {info.get('asset_type_display', 'Акция')}\n"
        f"Валюта: {info.get('currency', 'RUB')}\n"
        f"{market_status}\n\n"
        f"💰 Текущая цена: <b>{price_text}</b>\n\n"
        f"🔢 Введите количество актива (например, 10 или 0.5):",
        reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}")
    )


@router.message(AssetState.waiting_for_quantity)
@log_function_call()
async def process_asset_quantity(message: Message, state: FSMContext):
    """Обработка количества актива"""
    quantity = parse_decimal(message.text)
    data = await state.get_data()
    portfolio_id = data.get('portfolio_id')

    if not validate_positive_decimal(quantity):
        await cleanup_and_answer(
            message,
            state,
            "❌ Вы ввели отрицательное или слишком большое число (более 12 цифр).\nВведите корректное число:",
            reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}")
        )
        return

    await state.update_data(quantity=quantity)
    current_price = data.get('current_price')

    await state.set_state(AssetState.waiting_for_price_choice)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💰 Использовать текущую цену MOEX",
                callback_data="use_moex_price"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Ввести свою цену",
                callback_data="use_manual_price"
            )
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"portfolio_{portfolio_id}")
        ]
    ])

    currency = data.get('currency', 'RUB')

    if current_price and current_price > 0:
        price_text = format_money(current_price, currency)
        await cleanup_and_answer(
            message,
            state,
            f"📝 <b>Выберите цену покупки для {data['symbol']}</b>\n\n"
            f"💰 Текущая рыночная цена: <b>{price_text}</b>\n\n"
            f"Выберите, какую цену использовать:",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Ввести свою цену",
                    callback_data="use_manual_price"
                )
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"portfolio_{portfolio_id}")
            ]
        ])
        await cleanup_and_answer(
            message,
            state,
            f"⚠️ <b>Текущая цена для {data['symbol']} недоступна</b>\n\n"
            f"Пожалуйста, введите цену покупки вручную:",
            reply_markup=keyboard
        )


@router.callback_query(AssetState.waiting_for_price_choice, F.data == "use_moex_price")
@log_function_call()
async def use_moex_price(callback: CallbackQuery, state: FSMContext):
    """Использовать текущую цену с MOEX"""
    await safe_callback_answer(callback)

    data = await state.get_data()
    current_price = data.get('current_price')

    if not current_price or current_price <= 0:
        await callback.message.edit_text(
            "❌ Текущая цена недоступна. Пожалуйста, введите цену вручную.",
            reply_markup=Keyboards.get_back_button("add_asset")
        )
        await state.set_state(AssetState.waiting_for_manual_price)
        return

    await state.update_data(purchase_price=current_price, price_choice='moex')
    await show_confirmation(callback.message, state, callback)


@router.callback_query(AssetState.waiting_for_price_choice, F.data == "use_manual_price")
@log_function_call()
async def use_manual_price(callback: CallbackQuery, state: FSMContext):
    """Ввести свою цену"""
    await safe_callback_answer(callback)
    await state.set_state(AssetState.waiting_for_manual_price)

    # Обновляем last_bot_msg_id для следующего шага
    await state.update_data(price_choice='manual', last_bot_msg_id=callback.message.message_id)

    data = await state.get_data()
    currency = data.get('currency', 'RUB')
    current_price = data.get('current_price')
    portfolio_id = data.get('portfolio_id')

    text = "✏️ <b>Введите цену покупки</b>\n\n"
    text += f"Валюта: {currency}\n\n"

    if current_price and current_price > 0:
        text += f"💰 Текущая рыночная цена: {format_money(current_price, currency)}\n"
        text += f"💡 Вы можете ввести другую цену, отличную от рыночной\n\n"

    text += f"Введите цену (например, 150.50 или 2500):"

    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}")
    )


@router.message(AssetState.waiting_for_manual_price)
@log_function_call()
async def process_manual_price(message: Message, state: FSMContext):
    """Обработка ручного ввода цены"""
    purchase_price = parse_decimal(message.text)
    data = await state.get_data()
    portfolio_id = data.get('portfolio_id')

    if not validate_positive_decimal(purchase_price):
        await cleanup_and_answer(
            message,
            state,
            "❌ Введите положительное число (например, 150.50 или 2500):\n\n"
            "Цена должна быть больше 0",
            reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}")
        )
        return

    if purchase_price > Decimal('999999999999'):
        await cleanup_and_answer(
            message,
            state,
            "❌ Слишком большая цена (максимум 999 999 999 999)",
            reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"portfolio_{portfolio_id}")
        )
        return

    await state.update_data(purchase_price=purchase_price)
    await show_confirmation(message, state)


async def show_confirmation(message: Message, state: FSMContext, callback: CallbackQuery = None):
    """Показывает подтверждение добавления актива"""
    data = await state.get_data()

    quantity = data['quantity']
    purchase_price = data['purchase_price']
    current_price = data.get('current_price')
    currency = data.get('currency', 'RUB')
    total = quantity * purchase_price

    price_choice = data.get('price_choice', 'manual')
    portfolio_id = data.get('portfolio_id')

    profit_info = ""
    if price_choice == 'moex' and current_price and current_price > 0:
        current_total = quantity * current_price
        potential_profit = current_total - total

        if abs(potential_profit) > Decimal('0.01'):
            potential_profit_percent = (potential_profit / total * 100) if total > 0 else Decimal('0')
            profit_icon = "🟢" if potential_profit >= 0 else "🔴"
            profit_info = f"\n📈 Потенциальная прибыль: {profit_icon} {format_money(potential_profit, currency)} ({format_percent(potential_profit_percent)})"

    price_source = "текущей рыночной MOEX" if price_choice == 'moex' else "введена вручную"

    await state.set_state(AssetState.waiting_for_confirmation)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_add_asset")],
        [InlineKeyboardButton(text="↩️ Назад к выбору цены", callback_data="back_to_price_choice")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"portfolio_{portfolio_id}")]
    ])

    response = f"""
📝 <b>Подтверждение добавления актива</b>

Актив: <b>{data['name']}</b> ({data['symbol']})
Количество: <b>{quantity}</b>
Цена покупки: <b>{format_money(purchase_price, currency)}</b> ({price_source})
Общая стоимость: <b>{format_money(total, currency)}</b>{profit_info}

Всё верно?
    """

    if callback:
        await callback.message.edit_text(response, reply_markup=keyboard)
    else:
        await cleanup_and_answer(message, state, response, reply_markup=keyboard)


@router.callback_query(F.data == "back_to_price_choice")
@log_function_call()
async def back_to_price_choice(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору цены"""
    await safe_callback_answer(callback)
    await state.set_state(AssetState.waiting_for_price_choice)

    data = await state.get_data()
    current_price = data.get('current_price')
    currency = data.get('currency', 'RUB')
    portfolio_id = data.get('portfolio_id')

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💰 Использовать текущую цену MOEX",
                callback_data="use_moex_price"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Ввести свою цену",
                callback_data="use_manual_price"
            )
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"portfolio_{portfolio_id}")
        ]
    ])

    if current_price and current_price > 0:
        price_text = format_money(current_price, currency)
        await callback.message.edit_text(
            f"📝 <b>Выберите цену покупки для {data['symbol']}</b>\n\n"
            f"💰 Текущая рыночная цена: <b>{price_text}</b>\n\n"
            f"Выберите, какую цену использовать:",
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Ввести свою цену",
                    callback_data="use_manual_price"
                )
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"portfolio_{portfolio_id}")
            ]
        ])
        await callback.message.edit_text(
            f"⚠️ <b>Текущая цена для {data['symbol']} недоступна</b>\n\n"
            f"Пожалуйста, введите цену покупки вручную:",
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
            purchase_price=data['purchase_price'],
            currency=data.get('currency', 'RUB'),
            sector=data.get('info', {}).get('sector'),
            notes=None
        )

        await state.clear()

        if asset_id:
            currency = data.get('currency', 'RUB')
            total = data['quantity'] * data['purchase_price']
            price_source = "текущей рыночной" if data['purchase_price'] == data.get(
                'current_price') else "введенной вручную"

            await safe_edit_message(
                callback,
                f"✅ <b>Актив успешно добавлен!</b>\n\n"
                f"Актив: {data['name']} ({data['symbol']})\n"
                f"Количество: {data['quantity']}\n"
                f"Цена покупки: {format_money(data['purchase_price'], currency)} ({price_source})\n"
                f"Общая стоимость: {format_money(total, currency)}",
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
        current_price = await price_service.get_price(asset['symbol'])

        if not current_price:
            current_price = asset['current_price'] or purchase_price

        cost = quantity * purchase_price
        current_value = quantity * current_price
        profit = current_value - cost
        profit_percent = (profit / cost * 100) if cost > 0 else Decimal('0')
        asset['profit'] = profit
        asset['profit_percent'] = profit_percent
        asset['current_price_display'] = current_price

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
📦 Количество: {format_quantity(details['quantity'])}
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
    """Обновление цены актива"""
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

    new_callback = callback.model_copy(update={"data": f"view_asset_{asset_id}"})
    await view_asset(new_callback)


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
        [InlineKeyboardButton(text="💰 Обновить цену", callback_data=f"refresh_asset_{asset_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_asset_{asset_id}")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"view_asset_{asset_id}")]
    ])

    await safe_edit_message(
        callback,
        f"✏️ <b>Редактирование актива</b>\n\n"
        f"Актив: {asset['name']} ({asset['symbol']})\n"
        f"Текущее количество: {asset['quantity']}\n"
        f"Цена покупки: {format_money(asset['purchase_price'], asset['currency'])}\n"
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

    await state.update_data(asset_id=asset_id, last_bot_msg_id=callback.message.message_id)
    await state.set_state(AssetState.waiting_for_edit_quantity)

    await safe_edit_message(
        callback,
        f"✏️ <b>Изменение количества</b>\n\n"
        f"Актив: {asset['name']} ({asset['symbol']})\n"
        f"Текущее количество: {asset['quantity']}\n\n"
        f"Введите новое количество (положительное число):",
        reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"view_asset_{asset_id}")
    )


@router.message(AssetState.waiting_for_edit_quantity)
@log_function_call()
async def process_edit_quantity(message: Message, state: FSMContext):
    """Обработка нового количества"""
    new_quantity = parse_decimal(message.text)
    data = await state.get_data()
    asset_id = data['asset_id']

    if not validate_positive_decimal(new_quantity):
        await cleanup_and_answer(
            message,
            state,
            "❌ Введите положительное число:",
            reply_markup=Keyboards.get_cancel_keyboard(callback_data=f"view_asset_{asset_id}")
        )
        return

    await AssetRepository.update_quantity(asset_id, new_quantity)

    await cleanup_and_answer(
        message,
        state,
        f"✅ Количество обновлено до {new_quantity}",
        reply_markup=Keyboards.get_back_button(f"view_asset_{asset_id}")
    )
    await state.clear()


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


@router.callback_query(F.data.startswith("more_assets_"))
@log_function_call()
async def paginate_assets(callback: CallbackQuery):
    """Пагинация списка активов"""
    await safe_callback_answer(callback)

    parts = callback.data.split("_")
    if len(parts) < 4:
        return

    portfolio_id = int(parts[2])
    offset = int(parts[3])

    assets = await AssetRepository.get_portfolio_assets(portfolio_id)
    if not assets:
        return

    for asset in assets:
        quantity = asset['quantity']
        purchase_price = asset['purchase_price']
        current_price = asset['current_price'] or purchase_price
        cost = quantity * purchase_price
        current_value = quantity * current_price
        profit = current_value - cost
        asset['profit'] = profit
        asset['profit_percent'] = (profit / cost * 100) if cost > 0 else Decimal('0')

    next_offset = offset + 10
    current_page_assets = assets[offset:next_offset]

    buttons = []
    for asset in current_page_assets:
        profit_icon = "🟢" if asset.get('profit', 0) >= 0 else "🔴"
        profit_str = f"{profit_icon} {float(asset.get('profit_percent', 0)):+.2f}%"
        buttons.append([
            InlineKeyboardButton(
                text=f"{asset['symbol']} - {asset['name'][:20]} {profit_str}",
                callback_data=f"view_asset_{asset['id']}"
            )
        ])

    if len(assets) > next_offset:
        buttons.append(
            [InlineKeyboardButton(text="📄 Показать еще", callback_data=f"more_assets_{portfolio_id}_{next_offset}")])

    buttons.append([InlineKeyboardButton(text="↩️ Назад к портфелю", callback_data=f"portfolio_{portfolio_id}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await safe_edit_message(
        callback,
        f"📋 <b>Активы портфеля (Стр. {offset // 10 + 1}):</b>",
        reply_markup=keyboard
    )