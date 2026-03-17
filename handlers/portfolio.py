from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal

from database.repositories import PortfolioRepository, AssetRepository
from keyboards import Keyboards
from logger import get_logger, log_function_call
from services.price_service import price_service
from services.portfolio_service import portfolio_service
from utils import format_money, format_percent

router = Router()
logger = get_logger('portfolio')


class PortfolioState(StatesGroup):
    """Состояния для создания портфеля"""
    waiting_for_name = State()
    waiting_for_description = State()


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

    # Обновляем стоимости портфелей
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
    await callback.answer()
    await state.set_state(PortfolioState.waiting_for_name)

    await callback.message.edit_text(
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


@router.callback_query(F.data.startswith("portfolio_"))
@log_function_call()
async def show_portfolio_detail(callback: CallbackQuery):
    """Показывает детали портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("portfolio_", ""))

    # Полный расчет портфеля
    summary = await portfolio_service.calculate_portfolio_summary(portfolio_id, force_update=True)

    if not summary:
        await callback.message.edit_text("❌ Портфель не найден")
        return

    portfolio = summary['portfolio']
    total_value = summary['total_value']
    total_cost = summary['total_cost']
    total_profit = summary['total_profit']
    total_profit_percent = summary['total_profit_percent']
    assets_count = summary['assets_count']

    # Формируем ответ
    profit_icon = "🟢" if total_profit >= 0 else "🔴"
    profit_text = f"{profit_icon} {format_money(total_profit)} ({format_percent(total_profit_percent)})"

    response = f"""
📊 <b>{portfolio['name']}</b>

💰 Общая стоимость: <b>{format_money(total_value)}</b>
💵 Вложено: <b>{format_money(total_cost)}</b>
📈 Прибыль: <b>{profit_text}</b>
📦 Активов: <b>{assets_count}</b>
    """

    if portfolio.get('description'):
        response += f"\n📝 {portfolio['description']}"

    # Добавляем распределение по типам
    if summary['type_allocation']:
        response += "\n\n📊 <b>Распределение по типам:</b>\n"
        type_names = {
            'stock': 'Акции',
            'bond': 'Облигации',
            'etf': 'ETF',
            'currency': 'Валюта',
            'futures': 'Фьючерсы'
        }
        for asset_type, pct in list(summary['type_allocation'].items())[:3]:
            type_name = type_names.get(asset_type, asset_type)
            response += f"• {type_name}: {pct:.1f}%\n"

    # Добавляем топ-3 актива
    if summary['assets']:
        response += "\n🔝 <b>Топ активов:</b>\n"
        for asset in summary['assets'][:3]:
            profit_icon = "🟢" if asset['profit'] >= 0 else "🔴"
            response += f"• {asset['symbol']}: {format_money(asset['current_value'])} ({profit_icon} {format_percent(asset['profit_percent'])})\n"

    await callback.message.edit_text(
        response,
        reply_markup=Keyboards.get_portfolio_actions(portfolio_id)
    )


@router.callback_query(F.data.startswith("stats_"))
@log_function_call()
async def show_portfolio_stats(callback: CallbackQuery):
    """Показывает расширенную статистику портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("stats_", ""))
    summary = await portfolio_service.calculate_portfolio_summary(portfolio_id, force_update=True)

    if not summary or summary['assets_count'] == 0:
        await callback.message.edit_text(
            "📭 <b>Нет данных для статистики</b>\n\n"
            "Добавьте активы в портфель.",
            reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
        )
        return

    # Риск-метрики
    risk_metrics = await portfolio_service.calculate_portfolio_risk_metrics(portfolio_id)

    # Рекомендации
    recommendations = await portfolio_service.get_recommendations(portfolio_id)

    response = f"""
📊 <b>Статистика портфеля</b>

💰 <b>Основные показатели:</b>
• Общая стоимость: {format_money(summary['total_value'])}
• Вложено: {format_money(summary['total_cost'])}
• Прибыль: {format_money(summary['total_profit'])} ({format_percent(summary['total_profit_percent'])})

⚖️ <b>Распределение:</b>
    """

    # Распределение по типам
    if summary['type_allocation']:
        response += "\n📊 По типам:\n"
        type_names = {
            'stock': 'Акции',
            'bond': 'Облигации',
            'etf': 'ETF',
            'currency': 'Валюта',
            'futures': 'Фьючерсы'
        }
        for asset_type, pct in summary['type_allocation'].items():
            type_name = type_names.get(asset_type, asset_type)
            response += f"  • {type_name}: {pct:.1f}%\n"

    # Распределение по валютам
    if summary['currency_allocation']:
        response += "\n💵 По валютам:\n"
        for currency, pct in summary['currency_allocation'].items():
            response += f"  • {currency}: {pct:.1f}%\n"

    # Риск-метрики
    if risk_metrics:
        response += f"""
⚠️ <b>Риск-метрики:</b>
• Уровень риска: {risk_metrics.get('risk_level', 'Н/Д')}
• Макс. концентрация: {risk_metrics.get('max_concentration', 0):.1f}%
• Диверсификация: {risk_metrics.get('diversified_count', 0)} активов (>5%)
• Валютный риск: {risk_metrics.get('currency_risk_pct', 0):.1f}%
        """

    # Рекомендации
    if recommendations:
        response += "\n💡 <b>Рекомендации:</b>\n"
        for rec in recommendations[:3]:
            response += f"• {rec['text']}\n"

    await callback.message.edit_text(
        response,
        reply_markup=Keyboards.get_refresh_keyboard(portfolio_id)
    )


@router.callback_query(F.data.startswith("refresh_portfolio_"))
@log_function_call()
async def refresh_portfolio(callback: CallbackQuery):
    """Обновление цен портфеля"""
    await callback.answer("🔄 Обновляем цены...")

    portfolio_id = int(callback.data.replace("refresh_portfolio_", ""))
    updated = await price_service.update_portfolio_prices(portfolio_id)

    await callback.answer(f"✅ Обновлено {updated} активов")

    # Возвращаемся к статистике
    await show_portfolio_stats(callback)


@router.callback_query(F.data.startswith("edit_portfolio_"))
@log_function_call()
async def edit_portfolio(callback: CallbackQuery, state: FSMContext):
    """Редактирование портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("edit_portfolio_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await callback.message.edit_text("❌ Портфель не найден")
        return

    # Здесь можно реализовать редактирование
    await callback.message.edit_text(
        f"✏️ <b>Редактирование портфеля</b>\n\n"
        f"Пока в разработке. Вы можете удалить портфель и создать новый.",
        reply_markup=Keyboards.get_back_button(f"portfolio_{portfolio_id}")
    )


@router.callback_query(F.data.startswith("delete_portfolio_"))
@log_function_call()
async def delete_portfolio(callback: CallbackQuery):
    """Удаление портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("delete_portfolio_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await callback.message.edit_text("❌ Портфель не найден")
        return

    # Подтверждение удаления
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{portfolio_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"portfolio_{portfolio_id}")
        ]
    ])

    await callback.message.edit_text(
        f"🗑️ <b>Удаление портфеля</b>\n\n"
        f"Вы уверены, что хотите удалить портфель '{portfolio['name']}'?\n"
        f"Все активы в портфеле также будут удалены!",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("confirm_delete_"))
@log_function_call()
async def confirm_delete_portfolio(callback: CallbackQuery):
    """Подтверждение удаления портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("confirm_delete_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await callback.message.edit_text("❌ Портфель не найден")
        return

    if await PortfolioRepository.delete(portfolio_id):
        await callback.message.edit_text(
            f"✅ <b>Портфель '{portfolio['name']}' удален</b>",
            reply_markup=Keyboards.get_back_button("back_to_portfolios")
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка удаления портфеля",
            reply_markup=Keyboards.get_back_button("back_to_portfolios")
        )


@router.callback_query(F.data == "back_to_portfolios")
@log_function_call()
async def back_to_portfolios(callback: CallbackQuery):
    """Возврат к списку портфелей"""
    await callback.answer()

    user_id = callback.from_user.id
    portfolios = await PortfolioRepository.get_user_portfolios(user_id)

    await callback.message.edit_text(
        "📊 <b>Ваши портфели:</b>",
        reply_markup=Keyboards.get_portfolio_list(portfolios)
    )