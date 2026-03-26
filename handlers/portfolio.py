from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal

from database.repositories import PortfolioRepository, AssetRepository
from keyboards import Keyboards
from logger import get_logger, log_function_call
from services.price_service import price_service
from services.portfolio_service import portfolio_service
from utils import format_money, format_percent
from callback_utils import safe_callback_answer, safe_edit_message  # Добавили импорт безопасных функций

router = Router()
logger = get_logger('portfolio')


class PortfolioState(StatesGroup):
    """Состояния для создания портфеля"""
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_edit_name = State()
    waiting_for_edit_description = State()


@router.message(F.text == "📊 Мои портфели")
@log_function_call()
async def show_portfolios(message: Message):
    """Показывает список портфелей"""
    user_id = message.from_user.id

    portfolios = await PortfolioRepository.get_user_portfolios(user_id)

    if not portfolios:
        await message.answer(
            "📭 <b>У вас нет портфелей</b>\n\n"
            "Создайте первый портфель!",
            reply_markup=Keyboards.get_portfolio_empty()
        )
        return

    # Получаем актуальные данные (мгновенно из БД)
    for portfolio in portfolios:
        if portfolio['assets_count'] > 0:
            summary = await portfolio_service.calculate_portfolio_summary(portfolio['id'])
            portfolio['total_value'] = summary.get('total_value', Decimal('0'))

    await message.answer(
        "📊 <b>Ваши портфели:</b>",
        reply_markup=Keyboards.get_portfolio_list(portfolios)
    )


@router.message(F.text == "➕ Создать портфель")
@log_function_call()
async def create_portfolio_start(message: Message, state: FSMContext):
    """Начало создания портфеля"""
    await state.set_state(PortfolioState.waiting_for_name)

    await message.answer(
        "📝 <b>Создание нового портфеля</b>\n\n"
        "Введите название портфеля:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.callback_query(F.data == "create_portfolio")
@log_function_call()
async def create_portfolio_callback(callback: CallbackQuery, state: FSMContext):
    """Начало создания портфеля (из callback)"""
    await safe_callback_answer(callback)
    await state.set_state(PortfolioState.waiting_for_name)

    await safe_edit_message(
        callback,
        "📝 <b>Создание нового портфеля</b>\n\n"
        "Введите название портфеля:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(PortfolioState.waiting_for_name)
@log_function_call()
async def process_portfolio_name(message: Message, state: FSMContext):
    """Обработка названия портфеля"""
    name = message.text.strip()

    if len(name) < 3 or len(name) > 50:
        await message.answer("❌ Название должно быть от 3 до 50 символов. Попробуйте еще раз:")
        return

    if await PortfolioRepository.check_name_exists(message.from_user.id, name):
        await message.answer("❌ У вас уже есть портфель с таким названием. Придумайте другое:")
        return

    await state.update_data(name=name)
    await state.set_state(PortfolioState.waiting_for_description)

    await message.answer(
        f"📝 Название: <b>{name}</b>\n\n"
        f"Теперь введите описание портфеля (или отправьте /skip чтобы пропустить):",
        reply_markup=Keyboards.get_skip_keyboard()
    )


@router.message(PortfolioState.waiting_for_description)
@log_function_call()
async def process_portfolio_description(message: Message, state: FSMContext):
    """Обработка описания портфеля"""
    if message.text == "/skip":
        description = None
    else:
        description = message.text.strip()
        if len(description) > 500:
            await message.answer("❌ Описание слишком длинное (макс. 500 символов). Попробуйте еще раз:")
            return

    data = await state.get_data()
    name = data.get('name')
    user_id = message.from_user.id

    portfolio_id = await PortfolioRepository.create(
        user_id=user_id,
        name=name,
        description=description
    )

    await state.clear()

    if portfolio_id:
        await message.answer(
            f"✅ <b>Портфель '{name}' создан!</b>\n\n"
            f"Теперь вы можете добавлять в него активы.",
            reply_markup=Keyboards.get_portfolio_actions(portfolio_id)
        )
    else:
        await message.answer(
            "❌ Ошибка создания портфеля. Попробуйте позже.",
            reply_markup=Keyboards.get_main_menu()
        )


@router.callback_query(PortfolioState.waiting_for_description, F.data == "skip")
@log_function_call()
async def process_skip_portfolio_description(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Пропустить' при создании (сохраняем без описания)"""
    await callback.answer()

    data = await state.get_data()
    name = data.get('name')
    user_id = callback.from_user.id

    # Создаем портфель с пустым описанием (None)
    portfolio_id = await PortfolioRepository.create(
        user_id=user_id,
        name=name,
        description=None
    )

    await state.clear()

    # Убираем старое сообщение с клавиатурой
    try:
        await callback.message.delete()
    except:
        pass

    if portfolio_id:
        await callback.message.answer(
            f"✅ <b>Портфель '{name}' создан!</b>\n\n"
            f"Теперь вы можете добавлять в него активы.",
            reply_markup=Keyboards.get_portfolio_actions(portfolio_id)
        )
    else:
        await callback.message.answer(
            "❌ Ошибка создания портфеля. Попробуйте позже.",
            reply_markup=Keyboards.get_main_menu()
        )


@router.callback_query(PortfolioState.waiting_for_edit_description, F.data == "skip")
@log_function_call()
async def process_skip_edit_portfolio_description(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Пропустить' при редактировании (очищаем описание)"""
    await callback.answer()

    data = await state.get_data()
    portfolio_id = data['portfolio_id']

    # Обновляем описание на None (очищаем)
    success = await PortfolioRepository.update_description(portfolio_id, None)

    await state.clear()

    try:
        await callback.message.delete()
    except:
        pass

    if success:
        await callback.message.answer(
            f"✅ Описание портфеля очищено",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
    else:
        await callback.message.answer(
            "❌ Ошибка при обновлении описания",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )

@router.callback_query(F.data.startswith("portfolio_"))
@log_function_call()
async def show_portfolio_detail(callback: CallbackQuery):
    """Показывает детали портфеля"""
    await safe_callback_answer(callback)

    portfolio_id = int(callback.data.replace("portfolio_", ""))
    summary = await portfolio_service.calculate_portfolio_summary(portfolio_id)

    if not summary:
        await safe_edit_message(callback, "❌ Портфель не найден")
        return

    portfolio = summary['portfolio']
    total_value = summary['total_value']
    total_cost = summary['total_cost']
    total_profit = summary['total_profit']
    total_profit_percent = summary['total_profit_percent']
    assets_count = summary['assets_count']

    profit_icon = "🟢" if total_profit >= 0 else "🔴"
    profit_text = f"{profit_icon} {format_money(total_profit)} ({format_percent(total_profit_percent)})"

    market_status = "🟢 Рынок открыт" if price_service._is_market_open() else "🔴 Рынок закрыт"

    response = f"""
📊 <b>{portfolio['name']}</b>
{market_status}

💰 Общая стоимость: <b>{format_money(total_value)}</b>
💵 Вложено: <b>{format_money(total_cost)}</b>
📈 Прибыль: <b>{profit_text}</b>
📦 Активов: <b>{assets_count}</b>
    """

    if portfolio.get('description'):
        response += f"\n📝 {portfolio['description']}"

    if summary['type_allocation']:
        response += "\n\n📊 <b>Распределение по типам:</b>\n"
        type_names = {
            'stock': 'Акции', 'bond': 'Облигации', 'etf': 'ETF',
            'currency': 'Валюта', 'futures': 'Фьючерсы'
        }
        for asset_type, pct in list(summary['type_allocation'].items())[:3]:
            type_name = type_names.get(asset_type, asset_type)
            response += f"• {type_name}: {pct:.1f}%\n"

    if summary['assets']:
        response += "\n🔝 <b>Топ активов:</b>\n"
        for asset in summary['assets'][:3]:
            profit_icon = "🟢" if asset['profit'] >= 0 else "🔴"
            response += f"• {asset['symbol']}: {format_money(asset['current_value'])} ({profit_icon} {format_percent(asset['profit_percent'])})\n"

    await safe_edit_message(
        callback,
        response,
        reply_markup=Keyboards.get_portfolio_actions(portfolio_id)
    )


@router.callback_query(F.data.startswith("stats_"))
@log_function_call()
async def show_portfolio_stats(callback: CallbackQuery):
    """Показывает расширенную статистику портфеля"""
    await safe_callback_answer(callback)

    portfolio_id = int(callback.data.split("_")[1])
    summary = await portfolio_service.calculate_portfolio_summary(portfolio_id)

    if not summary or summary['assets_count'] == 0:
        await safe_edit_message(
            callback,
            "📭 <b>Нет данных для статистики</b>\n\n"
            "Добавьте активы в портфель.",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
        return

    response = f"""
📊 <b>Статистика портфеля</b>

💰 <b>Основные показатели:</b>
• Общая стоимость: {format_money(summary['total_value'])}
• Вложено: {format_money(summary['total_cost'])}
• Прибыль: {format_money(summary['total_profit'])} ({format_percent(summary['total_profit_percent'])})
    """

    if summary['type_allocation']:
        response += "\n\n⚖️ <b>Распределение:</b>\n"
        response += "\n📊 По типам:\n"
        type_names = {
            'stock': 'Акции', 'bond': 'Облигации', 'etf': 'ETF',
            'currency': 'Валюта', 'futures': 'Фьючерсы'
        }
        for asset_type, pct in summary['type_allocation'].items():
            type_name = type_names.get(asset_type, asset_type)
            response += f"  • {type_name}: {pct:.1f}%\n"

    if summary['currency_allocation']:
        response += "\n💵 По валютам:\n"
        for currency, pct in summary['currency_allocation'].items():
            response += f"  • {currency}: {pct:.1f}%\n"

    await safe_edit_message(
        callback,
        response,
        reply_markup=Keyboards.get_refresh_keyboard(portfolio_id)
    )


@router.callback_query(F.data.startswith("refresh_portfolio_"))
@log_function_call()
async def refresh_portfolio(callback: CallbackQuery):
    """Кнопка Обновить (перерисовывает статистику по актуальному кэшу)"""
    await safe_callback_answer(callback, "🔄 Актуализируем данные...")

    portfolio_id = int(callback.data.replace("refresh_portfolio_", ""))

    # Безопасное обновление данных коллбека (избегаем ошибки Instance is frozen)
    new_callback = callback.model_copy(update={"data": f"stats_{portfolio_id}"})
    await show_portfolio_stats(new_callback)


@router.callback_query(F.data.startswith("edit_portfolio_"))
@log_function_call()
async def edit_portfolio(callback: CallbackQuery, state: FSMContext):
    """Редактирование портфеля"""
    await safe_callback_answer(callback)

    portfolio_id = int(callback.data.replace("edit_portfolio_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await safe_edit_message(callback, "❌ Портфель не найден")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        # ИЗМЕНЕНО: Новые уникальные префиксы edit_name_ и edit_desc_
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"edit_name_{portfolio_id}")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"edit_desc_{portfolio_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить портфель", callback_data=f"delete_portfolio_{portfolio_id}")],
        [InlineKeyboardButton(text="↩️ Назад", callback_data=f"portfolio_{portfolio_id}")]
    ])

    await safe_edit_message(
        callback,
        f"✏️ <b>Редактирование портфеля</b>\n\n"
        f"Название: {portfolio['name']}\n"
        f"Описание: {portfolio.get('description', 'нет')}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("edit_name_"))
@log_function_call()
async def edit_portfolio_name(callback: CallbackQuery, state: FSMContext):
    """Редактирование названия портфеля"""
    await safe_callback_answer(callback)

    # ИЗМЕНЕНО: Отрезаем правильный префикс
    portfolio_id = int(callback.data.replace("edit_name_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await safe_edit_message(callback, "❌ Портфель не найден")
        return

    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(PortfolioState.waiting_for_edit_name)

    await safe_edit_message(
        callback,
        f"✏️ <b>Изменение названия портфеля</b>\n\n"
        f"Текущее название: {portfolio['name']}\n\n"
        f"Введите новое название:",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(PortfolioState.waiting_for_edit_name)
@log_function_call()
async def process_edit_portfolio_name(message: Message, state: FSMContext):
    """Обработка нового названия портфеля"""
    new_name = message.text.strip()

    if len(new_name) < 3 or len(new_name) > 50:
        await message.answer("❌ Название должно быть от 3 до 50 символов. Попробуйте еще раз:")
        return

    if await PortfolioRepository.check_name_exists(message.from_user.id, new_name):
        await message.answer("❌ У вас уже есть портфель с таким названием. Придумайте другое:")
        return

    data = await state.get_data()
    portfolio_id = data['portfolio_id']

    success = await PortfolioRepository.update_name(portfolio_id, new_name)

    await state.clear()

    if success:
        await message.answer(
            f"✅ Название портфеля изменено на '{new_name}'",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
    else:
        await message.answer(
            "❌ Ошибка при изменении названия",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )


@router.callback_query(F.data.startswith("edit_desc_"))
@log_function_call()
async def edit_portfolio_description(callback: CallbackQuery, state: FSMContext):
    """Редактирование описания портфеля"""
    await safe_callback_answer(callback)

    # ИЗМЕНЕНО: Отрезаем правильный префикс
    portfolio_id = int(callback.data.replace("edit_desc_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await safe_edit_message(callback, "❌ Портфель не найден")
        return

    await state.update_data(portfolio_id=portfolio_id)
    await state.set_state(PortfolioState.waiting_for_edit_description)

    await safe_edit_message(
        callback,
        f"✏️ <b>Изменение описания портфеля</b>\n\n"
        f"Текущее описание: {portfolio.get('description', 'нет')}\n\n"
        f"Введите новое описание (или /skip чтобы оставить пустым):",
        reply_markup=Keyboards.get_skip_keyboard()
    )


@router.message(PortfolioState.waiting_for_edit_description)
@log_function_call()
async def process_edit_portfolio_description(message: Message, state: FSMContext):
    """Обработка нового описания портфеля"""
    if message.text == "/skip":
        new_description = None
    else:
        new_description = message.text.strip()
        if len(new_description) > 500:
            await message.answer("❌ Описание слишком длинное (макс. 500 символов). Попробуйте еще раз:")
            return

    data = await state.get_data()
    portfolio_id = data['portfolio_id']

    success = await PortfolioRepository.update_description(portfolio_id, new_description)

    await state.clear()

    if success:
        await message.answer(
            f"✅ Описание портфеля обновлено",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
    else:
        await message.answer(
            "❌ Ошибка при обновлении описания",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )


@router.callback_query(F.data.startswith("delete_portfolio_"))
@log_function_call()
async def delete_portfolio(callback: CallbackQuery):
    """Удаление портфеля"""
    await safe_callback_answer(callback)

    portfolio_id = int(callback.data.replace("delete_portfolio_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await safe_edit_message(callback, "❌ Портфель не найден")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            # ИЗМЕНЕНО: теперь используем префикс confirm_delete_portfolio_
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_portfolio_{portfolio_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"portfolio_{portfolio_id}")
        ]
    ])

    await safe_edit_message(
        callback,
        f"🗑️ <b>Удаление портфеля</b>\n\n"
        f"Вы уверены, что хотите удалить портфель '{portfolio['name']}'?\n"
        f"Все активы в портфеле также будут удалены!",
        reply_markup=keyboard
    )


# ИЗМЕНЕНО: фильтр теперь ловит строго confirm_delete_portfolio_
@router.callback_query(F.data.startswith("confirm_delete_portfolio_"))
@log_function_call()
async def confirm_delete_portfolio(callback: CallbackQuery):
    """Подтверждение удаления портфеля"""
    await safe_callback_answer(callback)

    # ИЗМЕНЕНО: отрезаем правильный префикс
    portfolio_id = int(callback.data.replace("confirm_delete_portfolio_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await safe_edit_message(callback, "❌ Портфель не найден")
        return

    if await PortfolioRepository.delete(portfolio_id):
        await safe_edit_message(
            callback,
            f"✅ <b>Портфель '{portfolio['name']}' удален</b>",
            reply_markup=Keyboards.get_back_button("back_to_portfolios")
        )
    else:
        await safe_edit_message(
            callback,
            "❌ Ошибка удаления портфеля",
            reply_markup=Keyboards.get_back_button("back_to_portfolios")
        )


@router.callback_query(F.data == "back_to_portfolios")
@log_function_call()
async def back_to_portfolios(callback: CallbackQuery):
    """Возврат к списку портфелей"""
    await safe_callback_answer(callback)

    user_id = callback.from_user.id
    portfolios = await PortfolioRepository.get_user_portfolios(user_id)

    await safe_edit_message(
        callback,
        "📊 <b>Ваши портфели:</b>",
        reply_markup=Keyboards.get_portfolio_list(portfolios)
    )