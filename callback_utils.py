from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from typing import Optional, Any
from logger import get_logger
from config import Config
import asyncio

logger = get_logger('callback_utils')


async def safe_callback_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False,
                               max_retries: int = Config.TELEGRAM_MAX_RETRIES) -> bool:
    """
    Безопасный ответ на callback с обработкой устаревших запросов и сетевых ошибок

    Args:
        callback: CallbackQuery объект
        text: Текст уведомления
        show_alert: Показывать как alert
        max_retries: Максимальное количество попыток

    Returns:
        bool: True если успешно, False если callback устарел
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

    Args:
        callback: CallbackQuery объект
        text: Новый текст
        reply_markup: Новая клавиатура
        max_retries: Максимальное количество попыток
        **kwargs: Дополнительные параметры

    Returns:
        bool: True если успешно, False если не удалось
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

    Args:
        message: Сообщение для удаления
        max_retries: Максимальное количество попыток

    Returns:
        bool: True если успешно, False если не удалось
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

    Args:
        callback: CallbackQuery объект
        text: Текст сообщения
        reply_markup: Клавиатура
        max_retries: Максимальное количество попыток
        **kwargs: Дополнительные параметры

    Returns:
        Optional[Message]: Отправленное сообщение или None
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