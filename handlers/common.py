from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.repositories import UserRepository
from keyboards import Keyboards
from logger import get_logger, log_function_call
from constants import WELCOME_MESSAGE, HELP_MESSAGE

router = Router()
logger = get_logger('handlers')


@router.message(Command("start"))
@log_function_call()
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user = message.from_user

    # Сохраняем пользователя
    await UserRepository.create_or_update(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    logger.info(f"👤 Новый пользователь: {user.id} (@{user.username})")

    await message.answer(
        WELCOME_MESSAGE,
        reply_markup=Keyboards.get_main_menu()
    )


@router.message(Command("help"))
@log_function_call()
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(HELP_MESSAGE, reply_markup=Keyboards.get_back_button("back_to_main"))


@router.message(Command("cancel"))
@log_function_call()
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено",
        reply_markup=Keyboards.get_main_menu()
    )


@router.message(F.text == "📋 Помощь")
@log_function_call()
async def show_help(message: Message):
    """Показывает помощь"""
    await message.answer(HELP_MESSAGE, reply_markup=Keyboards.get_back_button("back_to_main"))


@router.callback_query(F.data == "back_to_main")
@log_function_call()
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await callback.answer()
    await state.clear()

    # Исправление: удаляем предыдущее сообщение и отправляем новое с обычной клавиатурой
    await callback.message.delete()
    await callback.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=Keyboards.get_main_menu()
    )


@router.callback_query(F.data == "cancel")
@log_function_call()
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена действия"""
    await callback.answer()
    await state.clear()

    # Исправление: удаляем предыдущее сообщение и отправляем новое с обычной клавиатурой
    await callback.message.delete()
    await callback.message.answer(
        "❌ Действие отменено",
        reply_markup=Keyboards.get_main_menu()
    )


@router.callback_query(F.data == "skip")
@log_function_call()
async def skip_action(callback: CallbackQuery, state: FSMContext):
    """Пропуск шага"""
    await callback.answer()
    await state.update_data(skipped=True)

    # Здесь нужно будет добавить логику перехода к следующему шагу
    # Пока просто удаляем сообщение
    await callback.message.delete()
    await callback.message.answer(
        "⏭️ Шаг пропущен",
        reply_markup=Keyboards.get_main_menu()
    )