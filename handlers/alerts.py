from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from decimal import Decimal

from database.repositories import AlertRepository, PortfolioRepository, AssetRepository
from keyboards import Keyboards
from logger import get_logger, log_function_call
from services.price_service import price_service
from services.portfolio_service import portfolio_service
from utils import parse_decimal, validate_positive_decimal, format_money, format_percent

router = Router()
logger = get_logger('alerts')


class AlertState(StatesGroup):
    """Состояния для создания уведомления"""
    waiting_for_target_value = State()
    waiting_for_portfolio_selection = State()
    waiting_for_asset_selection = State()


@router.message(F.text == "🔔 Мои уведомления")
@log_function_call()
async def show_alerts(message: Message):
    """Показывает список уведомлений"""
    user_id = message.from_user.id

    alerts = await AlertRepository.get_user_alerts(user_id, active_only=False)

    if not alerts:
        await message.answer(
            "📭 <b>У вас нет уведомлений</b>\n\n"
            "Создайте уведомление для портфеля или актива!",
            reply_markup=Keyboards.get_alerts_empty()
        )
        return

    # Разделяем на активные и сработавшие
    active_alerts = [a for a in alerts if a['is_active'] and not a['is_triggered']]
    triggered_alerts = [a for a in alerts if a['is_triggered']]

    text = "🔔 <b>Ваши уведомления</b>\n\n"

    if active_alerts:
        text += f"⏳ Активные: {len(active_alerts)}\n"
    if triggered_alerts:
        text += f"✅ Сработавшие: {len(triggered_alerts)}\n"

    await message.answer(
        text,
        reply_markup=Keyboards.get_alerts_list(alerts)
    )


@router.callback_query(F.data == "new_alert")
@log_function_call()
async def new_alert_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания нового уведомления"""
    await callback.answer()

    user_id = callback.from_user.id
    portfolios = await PortfolioRepository.get_user_portfolios(user_id)

    if not portfolios:
        await callback.message.edit_text(
            "📭 <b>У вас нет портфелей</b>\n\n"
            "Сначала создайте портфель!",
            reply_markup=Keyboards.get_back_button("back_to_alerts")
        )
        return

    # Показываем выбор портфеля
    buttons = []
    for p in portfolios:
        buttons.append([
            InlineKeyboardButton(
                text=f"📁 {p['name']} ({p['assets_count']} активов)",
                callback_data=f"alert_portfolio_{p['id']}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_alerts")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "🔔 <b>Создание уведомления</b>\n\n"
        "Выберите портфель:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("alert_portfolio_"))
@log_function_call()
async def create_portfolio_alert(callback: CallbackQuery, state: FSMContext):
    """Создание уведомления для портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("alert_portfolio_", ""))
    portfolio = await PortfolioRepository.get(portfolio_id)

    if not portfolio:
        await callback.message.edit_text("❌ Портфель не найден")
        return

    await state.update_data(
        alert_type='portfolio',
        portfolio_id=portfolio_id
    )

    # Проверяем, есть ли активы в портфеле
    assets = await AssetRepository.get_portfolio_assets(portfolio_id)
    if assets:
        # Если есть активы, показываем выбор: портфель или конкретный актив
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Весь портфель", callback_data=f"alert_target_portfolio_{portfolio_id}"),
                InlineKeyboardButton(text="💎 Конкретный актив", callback_data=f"alert_choose_asset_{portfolio_id}")
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="new_alert")]
        ])

        await callback.message.edit_text(
            f"🔔 <b>Уведомление для портфеля '{portfolio['name']}'</b>\n\n"
            f"Что будем отслеживать?",
            reply_markup=keyboard
        )
    else:
        # Если активов нет, только портфель
        await show_alert_type_selection(callback, state, 'portfolio', portfolio_id)


@router.callback_query(F.data.startswith("alert_target_portfolio_"))
@log_function_call()
async def alert_target_portfolio(callback: CallbackQuery, state: FSMContext):
    """Выбор цели для портфеля"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("alert_target_portfolio_", ""))
    await show_alert_type_selection(callback, state, 'portfolio', portfolio_id)


@router.callback_query(F.data.startswith("alert_choose_asset_"))
@log_function_call()
async def alert_choose_asset(callback: CallbackQuery, state: FSMContext):
    """Выбор актива для уведомления"""
    await callback.answer()

    portfolio_id = int(callback.data.replace("alert_choose_asset_", ""))
    assets = await AssetRepository.get_portfolio_assets(portfolio_id)

    if not assets:
        await callback.message.edit_text(
            "📭 В портфеле нет активов",
            reply_markup=Keyboards.get_back_button(f"alert_portfolio_{portfolio_id}")
        )
        return

    buttons = []
    for asset in assets[:10]:
        buttons.append([
            InlineKeyboardButton(
                text=f"{asset['symbol']} - {asset['name'][:30]}",
                callback_data=f"alert_asset_{asset['id']}"
            )
        ])

    if len(assets) > 10:
        buttons.append([InlineKeyboardButton(text="📄 Показать еще", callback_data=f"more_assets_alert_{portfolio_id}_10")])

    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"alert_portfolio_{portfolio_id}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "🔔 <b>Выберите актив для уведомления:</b>",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("alert_asset_"))
@log_function_call()
async def create_asset_alert(callback: CallbackQuery, state: FSMContext):
    """Создание уведомления для актива"""
    await callback.answer()

    asset_id = int(callback.data.replace("alert_asset_", ""))
    asset = await AssetRepository.get(asset_id)

    if not asset:
        await callback.message.edit_text("❌ Актив не найден")
        return

    await state.update_data(
        alert_type='asset',
        asset_id=asset_id
    )

    await show_alert_type_selection(callback, state, 'asset', asset_id)


async def show_alert_type_selection(callback: CallbackQuery, state: FSMContext,
                                    target_type: str, target_id: int):
    """Показывает выбор типа уведомления"""
    if target_type == 'portfolio':
        portfolio = await PortfolioRepository.get(target_id)
        name = portfolio['name'] if portfolio else f"ID:{target_id}"
        text = f"📊 Портфель: <b>{name}</b>"
    else:
        asset = await AssetRepository.get(target_id)
        name = asset['name'] if asset else f"ID:{target_id}"
        symbol = asset['symbol'] if asset else ""
        text = f"💎 Актив: <b>{name}</b> ({symbol})"

    await callback.message.edit_text(
        f"🔔 <b>Тип уведомления</b>\n\n"
        f"{text}\n\n"
        f"Выберите условие:",
        reply_markup=Keyboards.get_alert_type_selection(target_type, target_id)
    )


@router.callback_query(F.data.startswith("alert_type_"))
@log_function_call()
async def select_alert_type(callback: CallbackQuery, state: FSMContext):
    """Выбор типа уведомления"""
    await callback.answer()

    parts = callback.data.replace("alert_type_", "").split("_")
    condition_type = parts[0]  # price или percent
    direction = parts[1]  # up или down
    target_id = int(parts[2])

    await state.update_data(
        condition_type=condition_type,
        direction=direction
    )
    await state.set_state(AlertState.waiting_for_target_value)

    # Получаем текущее значение для подсказки
    user_id = callback.from_user.id
    current_value = None

    data = await state.get_data()

    if data['alert_type'] == 'portfolio':
        # Для портфеля
        portfolio_id = target_id
        assets = await AssetRepository.get_portfolio_assets(portfolio_id)

        if assets:
            # Обновляем цены
            await price_service.update_portfolio_prices(portfolio_id)
            portfolio_value = await price_service.calculate_portfolio_value(portfolio_id, assets)
            current_value = portfolio_value['total_value']
        else:
            current_value = Decimal('0')

        if condition_type == 'percent':
            hint = "Введите желаемый процент изменения (например, +10 или -5):"
        else:
            hint = f"Введите желаемую стоимость портфеля (текущая: {format_money(current_value)}):"
    else:
        # Для актива
        asset_id = target_id
        asset = await AssetRepository.get(asset_id)

        if asset:
            if not asset['current_price']:
                await price_service.get_price(asset['symbol'])
                asset = await AssetRepository.get(asset_id)

            current_value = asset['current_price'] or asset['purchase_price']

            if condition_type == 'percent':
                hint = "Введите желаемый процент изменения (например, +10 или -5):"
            else:
                hint = f"Введите желаемую цену (текущая: {format_money(current_value, asset['currency'])}):"

    await callback.message.edit_text(
        f"🎯 <b>Установка цели</b>\n\n"
        f"{hint}",
        reply_markup=Keyboards.get_cancel_keyboard()
    )


@router.message(AlertState.waiting_for_target_value)
@log_function_call()
async def process_alert_target(message: Message, state: FSMContext):
    """Обработка целевого значения"""
    target_text = message.text.strip()

    data = await state.get_data()
    condition_type = data['condition_type']
    user_id = message.from_user.id

    if condition_type == 'percent':
        # Парсим процент
        try:
            if target_text.startswith('+'):
                target_value = Decimal(target_text[1:])
            elif target_text.startswith('-'):
                target_value = Decimal(target_text)
            else:
                target_value = Decimal(target_text)

            # Для процентов допускаются отрицательные значения
            if abs(target_value) > 1000:
                await message.answer("❌ Слишком большой процент (макс. 1000%)")
                return
        except:
            await message.answer("❌ Введите число (например, +10 или -5):")
            return
    else:
        # Парсим цену
        target_value = parse_decimal(target_text)
        if not validate_positive_decimal(target_value):
            await message.answer("❌ Введите положительное число:")
            return

    # Создаем уведомление
    alert_id = None

    if data['alert_type'] == 'portfolio':
        alert_id = await AlertRepository.create_portfolio_alert(
            user_id=user_id,
            portfolio_id=data['portfolio_id'],
            condition_type=condition_type,
            direction=data['direction'],
            target_value=target_value
        )
    else:
        alert_id = await AlertRepository.create_asset_alert(
            user_id=user_id,
            asset_id=data['asset_id'],
            condition_type=condition_type,
            direction=data['direction'],
            target_value=target_value
        )

    await state.clear()

    if alert_id:
        direction_text = "выше" if data['direction'] == 'up' else "ниже"

        if condition_type == 'percent':
            target_display = f"{target_value:+.1f}%"
        else:
            target_display = format_money(target_value)

        await message.answer(
            f"✅ <b>Уведомление #{alert_id} создано!</b>\n\n"
            f"Цель: {direction_text} {target_display}\n\n"
            f"Я уведомлю вас при достижении цели!",
            reply_markup=Keyboards.get_main_menu()
        )
    else:
        await message.answer(
            "❌ Ошибка создания уведомления",
            reply_markup=Keyboards.get_main_menu()
        )


@router.callback_query(F.data.startswith("view_alert_"))
@log_function_call()
async def view_alert(callback: CallbackQuery):
    """Просмотр уведомления"""
    await callback.answer()

    alert_id = int(callback.data.replace("view_alert_", ""))
    alert = await AlertRepository.get(alert_id)

    if not alert:
        await callback.message.edit_text("❌ Уведомление не найдено")
        return

    # Формируем детальную информацию
    direction_icon = "📈" if alert['direction'] == 'up' else "📉"
    direction_text = "выше" if alert['direction'] == 'up' else "ниже"

    if alert['condition_type'] == 'price':
        target_display = format_money(alert['target_value'])
        current_display = format_money(alert['current_value']) if alert['current_value'] else "нет данных"
    else:
        target_display = f"{float(alert['target_value']):+.1f}%"
        current_display = f"{float(alert['current_value']):+.1f}%" if alert['current_value'] else "нет данных"

    status = "✅ Сработало" if alert['is_triggered'] else "⏳ Активно" if alert['is_active'] else "⏸️ Неактивно"
    created = alert['created_at'].strftime('%d.%m.%Y %H:%M') if alert['created_at'] else "неизвестно"

    if alert['alert_type'] == 'portfolio':
        target_name = alert.get('portfolio_name', f"Портфель ID:{alert['portfolio_id']}")
        text = f"""
🔔 <b>Уведомление #{alert['id']}</b>

📊 Объект: <b>{target_name}</b>
{direction_icon} Условие: {direction_text} {target_display}
💰 Текущее: {current_display}

📊 Статус: {status}
📅 Создано: {created}
        """
    else:
        target_name = alert.get('asset_name', alert.get('asset_symbol', f"Актив ID:{alert['asset_id']}"))
        symbol = alert.get('asset_symbol', '')
        text = f"""
🔔 <b>Уведомление #{alert['id']}</b>

💎 Актив: <b>{target_name}</b> ({symbol})
{direction_icon} Условие: {direction_text} {target_display}
💰 Текущее: {current_display}

📊 Статус: {status}
📅 Создано: {created}
        """

    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.get_alert_actions(alert_id)
    )


@router.callback_query(F.data.startswith("delete_alert_"))
@log_function_call()
async def delete_alert(callback: CallbackQuery):
    """Удаление уведомления"""
    await callback.answer()

    alert_id = int(callback.data.replace("delete_alert_", ""))

    if await AlertRepository.delete(alert_id):
        await callback.message.edit_text(
            "🗑️ <b>Уведомление удалено</b>",
            reply_markup=Keyboards.get_back_button("back_to_alerts")
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка удаления уведомления",
            reply_markup=Keyboards.get_back_button("back_to_alerts")
        )


@router.callback_query(F.data.startswith("reactivate_alert_"))
@log_function_call()
async def reactivate_alert(callback: CallbackQuery):
    """Реактивация уведомления"""
    await callback.answer()

    alert_id = int(callback.data.replace("reactivate_alert_", ""))

    if await AlertRepository.reactivate(alert_id):
        await callback.message.edit_text(
            "🔄 <b>Уведомление активировано</b>",
            reply_markup=Keyboards.get_back_button("back_to_alerts")
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка активации уведомления",
            reply_markup=Keyboards.get_back_button("back_to_alerts")
        )


@router.callback_query(F.data == "back_to_alerts")
@log_function_call()
async def back_to_alerts(callback: CallbackQuery):
    """Возврат к списку уведомлений"""
    await callback.answer()

    user_id = callback.from_user.id
    alerts = await AlertRepository.get_user_alerts(user_id, active_only=False)

    await callback.message.edit_text(
        "🔔 <b>Ваши уведомления:</b>",
        reply_markup=Keyboards.get_alerts_list(alerts)
    )


# Импортируем InlineKeyboardMarkup для использования в этом файле
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton