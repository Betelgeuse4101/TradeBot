from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.repositories import UserRepository
from keyboards import Keyboards
from logger import get_logger, log_function_call
from constants import WELCOME_MESSAGE, HELP_MESSAGE, POPULAR_TICKERS
from callback_utils import safe_callback_answer, safe_edit_message, safe_delete_message, auto_delete_message

router = Router()
logger = get_logger('handlers.common')


@router.message(Command("start"))
@auto_delete_message(delay=1)
@log_function_call()
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user = message.from_user

    await UserRepository.create_or_update(user_id=user.id)

    logger.info(f"👤 Новый пользователь: {user.id}")

    await message.answer(
        WELCOME_MESSAGE,
        reply_markup=Keyboards.get_main_menu()
    )


@router.message(Command("help"))
@auto_delete_message(delay=1)
@log_function_call()
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(HELP_MESSAGE, reply_markup=Keyboards.get_back_button("back_to_main"))


@router.message(Command("cancel"))
@auto_delete_message(delay=1)
@log_function_call()
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=Keyboards.get_main_menu()
    )


@router.message(F.text == "📋 Помощь")
@auto_delete_message(delay=1)
@log_function_call()
async def show_help(message: Message):
    """Показывает помощь"""
    await message.answer(HELP_MESSAGE, reply_markup=Keyboards.get_back_button("back_to_main"))


@router.callback_query(F.data == "back_to_main")
@log_function_call()
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await safe_callback_answer(callback)
    await state.clear()

    await safe_delete_message(callback.message)

    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=Keyboards.get_main_menu()
    )


@router.callback_query(F.data == "cancel")
@log_function_call()
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена действия"""
    await safe_callback_answer(callback, "❌ Действие отменено")
    await state.clear()

    await safe_delete_message(callback.message)

    await callback.message.answer(
        "❌ Действие отменено",
        reply_markup=Keyboards.get_main_menu()
    )


@router.message(F.text == "📈 Популярные активы")
@auto_delete_message(delay=1)
@log_function_call()
async def show_popular_tickers(message: Message):
    """Показывает список популярных тикеров"""
    items_per_page = 10
    total_pages = (len(POPULAR_TICKERS) + items_per_page - 1) // items_per_page

    text = "📈 <b>Популярные тикеры MOEX</b>\n\n"

    for i, ticker in enumerate(POPULAR_TICKERS[:items_per_page]):
        text += f"{i + 1}. <b>{ticker['symbol']}</b> - {ticker['name']} ({ticker['type']})\n"

    text += f"\n📄 Страница 1 из {total_pages}"

    await message.answer(
        text,
        reply_markup=Keyboards.get_popular_tickers_page(page=0, total_pages=total_pages)
    )


@router.callback_query(F.data.startswith("pop_page_"))
@log_function_call()
async def change_popular_page(callback: CallbackQuery):
    """Смена страницы популярных тикеров"""
    await callback.answer()

    page = int(callback.data.replace("pop_page_", ""))
    items_per_page = 10
    total_pages = (len(POPULAR_TICKERS) + items_per_page - 1) // items_per_page

    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(POPULAR_TICKERS))

    text = "📈 <b>Популярные тикеры MOEX</b>\n\n"

    for i, ticker in enumerate(POPULAR_TICKERS[start_idx:end_idx], start=start_idx + 1):
        text += f"{i}. <b>{ticker['symbol']}</b> - {ticker['name']} ({ticker['type']})\n"

    text += f"\n📄 Страница {page + 1} из {total_pages}"

    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.get_popular_tickers_page(page=page, total_pages=total_pages)
    )


@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    """Игнорирует нажатие на информационную кнопку"""
    await callback.answer()