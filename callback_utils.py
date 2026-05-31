from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from typing import Optional, Any
from logger import get_logger
from config import Config
import asyncio
from functools import wraps
from aiogram.fsm.context import FSMContext

logger = get_logger('callback_utils')


async def cleanup_and_answer(message: Message, state: FSMContext, text: str, reply_markup=None):
    """
    Удаляет предыдущее сообщение бота (с кнопками) и сообщение пользователя,
    затем отправляет новое сообщение и сохраняет его ID.
    """
    data = await state.get_data()
    last_msg_id = data.get("last_bot_msg_id")

    if last_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_msg_id)
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass

    new_msg = await message.answer(text, reply_markup=reply_markup)

    await state.update_data(last_bot_msg_id=new_msg.message_id)

    return new_msg


def auto_delete_message(delay: int = 3):
    """
    Декоратор для автоматического удаления сообщения пользователя после обработки команды
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(message: Message, *args, **kwargs):
            try:
                result = await func(message, *args, **kwargs)
                try:
                    await message.delete()
                    logger.debug(f"🗑️ Сообщение пользователя {message.from_user.id} удалено")
                except Exception as e:
                    logger.debug(f"⚠️ Не удалось удалить сообщение: {e}")

                return result
            except Exception as e:
                logger.error(f"Ошибка в {func.__name__}: {e}")
                raise

        return wrapper

    return decorator


async def safe_callback_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False,
                               max_retries: int = Config.TELEGRAM_MAX_RETRIES) -> bool:
    """
    Безопасный ответ на callback с обработкой устаревших запросов и сетевых ошибок
    """
    for attempt in range(max_retries):
        try:
            await callback.answer(text=text, show_alert=show_alert)
            return True
        except TelegramBadRequest as e:
            if "query is too old" in str(e) or "query ID is invalid" in str(e):
                logger.debug(f"⚠️ Пропуск устаревшего callback: {e}")
                return False
            logger.error(f"❌ Ошибка при answer callback: {e}")
            raise
        except (TelegramNetworkError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(
                    f"🌐 Сетевая ошибка при answer callback (попытка {attempt + 1}/{max_retries}): {e}. Ждем {wait_time}с")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Не удалось выполнить answer callback после {max_retries} попыток: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при answer callback: {e}")
            return False

    return False


async def safe_edit_message(
        callback: CallbackQuery,
        text: str,
        reply_markup: Optional[Any] = None,
        max_retries: int = Config.TELEGRAM_MAX_RETRIES,
        **kwargs
) -> bool:
    """
    Безопасное редактирование сообщения с обработкой ошибок и сетевых проблем
    """
    for attempt in range(max_retries):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup, **kwargs)
            return True
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                return True
            elif "message can't be edited" in str(e):
                try:
                    await callback.message.answer(text, reply_markup=reply_markup, **kwargs)
                    return True
                except Exception as send_error:
                    logger.error(f"❌ Ошибка при отправке нового сообщения: {send_error}")
                    return False
            else:
                logger.error(f"❌ Ошибка при редактировании сообщения: {e}")
                return False
        except (TelegramNetworkError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(
                    f"🌐 Сетевая ошибка при edit message (попытка {attempt + 1}/{max_retries}): {e}. Ждем {wait_time}с")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Не удалось отредактировать сообщение после {max_retries} попыток: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при редактировании: {e}")
            return False

    return False


async def safe_delete_message(message: Message, max_retries: int = Config.TELEGRAM_MAX_RETRIES) -> bool:
    """
    Безопасное удаление сообщения
    """
    for attempt in range(max_retries):
        try:
            await message.delete()
            return True
        except TelegramBadRequest as e:
            if "message can't be deleted" in str(e):
                logger.debug(f"⚠️ Сообщение нельзя удалить: {e}")
                return False
            else:
                logger.error(f"❌ Ошибка при удалении сообщения: {e}")
                return False
        except (TelegramNetworkError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(
                    f"🌐 Сетевая ошибка при delete message (попытка {attempt + 1}/{max_retries}): {e}. Ждем {wait_time}с")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Не удалось удалить сообщение после {max_retries} попыток: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при удалении: {e}")
            return False

    return False


async def safe_send_message(
        callback: CallbackQuery,
        text: str,
        reply_markup: Optional[Any] = None,
        max_retries: int = Config.TELEGRAM_MAX_RETRIES,
        **kwargs
) -> Optional[Message]:
    """
    Безопасная отправка нового сообщения
    """
    for attempt in range(max_retries):
        try:
            return await callback.message.answer(text, reply_markup=reply_markup, **kwargs)
        except (TelegramNetworkError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(
                    f"🌐 Сетевая ошибка при send message (попытка {attempt + 1}/{max_retries}): {e}. Ждем {wait_time}с")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"❌ Не удалось отправить сообщение после {max_retries} попыток: {e}")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения: {e}")
            return None

    return None