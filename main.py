import asyncio
import signal
import sys
from config import Config
from database.db import db
from handlers import common, portfolio, assets, alerts
from logger import get_logger, setup_module_loggers
from services.alert_service import AlertService
from services.price_service import price_service
from database.fsm_storage import AsyncpgStorage
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiohttp import ClientError
import aiohttp
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
import socket

logger = get_logger('main')


class CryptoBot:
    """Главный класс бота"""

    def __init__(self):
        self.storage = AsyncpgStorage()

        self.storage.key_builder = DefaultKeyBuilder(with_bot_id=True, with_destiny=True)

        session = AiohttpSession()

        self.bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            session=session
        )
        self.dp = Dispatcher(storage=self.storage)
        self.alert_service = AlertService(self.bot)
        self._polling_task = None
        self._alert_task = None
        self._price_updater_task = None
        self._cleanup_task = None
        self._retry_count = 0
        self._max_retries = 10
        self._polling_timeout = Config.TELEGRAM_POLLING_TIMEOUT
        self._is_shutting_down = False

        self.dp.include_router(common.router)
        self.dp.include_router(portfolio.router)
        self.dp.include_router(assets.router)
        self.dp.include_router(alerts.router)

    async def start(self):
        """Запуск бота"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК ИНВЕСТИЦИОННОГО БОТА С MOEX")
        logger.info("=" * 60)

        await db.connect()

        # Запуск периодической очистки старых FSM состояний
        self._cleanup_task = asyncio.create_task(self._cleanup_old_fsm_states_periodically())

        await self._safe_delete_webhook()

        # Запуск сервиса уведомлений
        self._alert_task = asyncio.create_task(self.alert_service.start())
        logger.info("✅ Сервис уведомлений запущен")

        # Запуск фонового обновления цен
        self._price_updater_task = asyncio.create_task(price_service.start_updater())
        logger.info("✅ Фоновое обновление цен запущено")

        logger.info("📡 Запуск поллинга...")
        self._polling_task = asyncio.create_task(self._safe_polling())

        try:
            await self._polling_task
        except asyncio.CancelledError:
            logger.info("🔄 Поллинг остановлен")
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в поллинге: {e}", exc_info=True)
        finally:
            await self.stop()

    async def _cleanup_old_fsm_states_periodically(self):
        """Периодическая очистка старых FSM состояний"""
        while not self._is_shutting_down:
            try:
                # Очищаем состояния старше 24 часов раз в 6 часов
                await self.storage.cleanup_old_states(max_age_hours=24)
                await asyncio.sleep(6 * 3600)  # 6 часов
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка при очистке FSM состояний: {e}")
                await asyncio.sleep(3600)  # При ошибке ждем час

    async def _safe_delete_webhook(self):
        """Безопасное удаление вебхука с повторными попытками"""
        for attempt in range(self._max_retries):
            try:
                await asyncio.wait_for(
                    self.bot.delete_webhook(drop_pending_updates=True),
                    timeout=self._polling_timeout
                )
                logger.info("✅ Вебхук удален")
                self._retry_count = 0
                return
            except asyncio.TimeoutError:
                self._retry_count += 1
                wait_time = min(2 ** self._retry_count, 30)
                logger.warning(f"⚠️ Таймаут удаления вебхука (попытка {attempt + 1}/{self._max_retries})")
            except TelegramNetworkError as e:
                self._retry_count += 1
                wait_time = min(2 ** self._retry_count, 30)
                logger.warning(f"⚠️ Сетевая ошибка удаления вебхука (попытка {attempt + 1}/{self._max_retries}): {e}")
            except Exception as e:
                self._retry_count += 1
                wait_time = min(2 ** self._retry_count, 30)
                logger.warning(f"⚠️ Ошибка удаления вебхука (попытка {attempt + 1}/{self._max_retries}): {e}")

            if attempt < self._max_retries - 1:
                logger.info(f"⏳ Ожидание {wait_time} секунд перед повторной попыткой...")
                await asyncio.sleep(wait_time)
            else:
                logger.error("❌ Не удалось удалить вебхук после всех попыток")

    async def _safe_polling(self):
        """Безопасный запуск поллинга с автоматическим восстановлением"""
        consecutive_errors = 0
        max_consecutive_errors = 5

        while not self._is_shutting_down:
            try:
                await self.dp.start_polling(
                    self.bot,
                    handle_signals=False,
                    close_bot_session=False,
                    polling_timeout=self._polling_timeout
                )
                consecutive_errors = 0
                break

            except (ClientError, asyncio.TimeoutError, aiohttp.ClientError, TelegramNetworkError, socket.gaierror) as e:
                consecutive_errors += 1
                self._retry_count += 1
                wait_time = min(2 ** min(self._retry_count, 6), 120)

                logger.error(f"🌐 Сетевая ошибка в поллинге ({consecutive_errors}/{max_consecutive_errors}): {e}")
                logger.info(f"⏳ Повторная попытка через {wait_time} секунд...")

                if not await self._check_internet_connection():
                    logger.warning("⚠️ Нет подключения к интернету, ждем...")
                    wait_time = 30

                await asyncio.sleep(wait_time)

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"❌ Слишком много последовательных ошибок ({consecutive_errors}), перезапускаем сессию...")
                    await self._recreate_session()
                    consecutive_errors = 0

            except TelegramRetryAfter as e:
                logger.warning(f"⏳ Telegram просит подождать {e.retry_after} секунд")
                await asyncio.sleep(e.retry_after)

            except Exception as e:
                logger.error(f"💥 Неожиданная ошибка в поллинге: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _recreate_session(self):
        """Пересоздание сессии при проблемах"""
        try:
            if self.bot.session and not self.bot.session.closed:
                await self.bot.session.close()

            session = AiohttpSession()
            self.bot.session = session
            logger.info("✅ Сессия Telegram пересоздана")
            self._retry_count = 0

        except Exception as e:
            logger.error(f"❌ Ошибка при пересоздании сессии: {e}")

    async def _check_internet_connection(self) -> bool:
        """Проверка подключения к интернету"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('8.8.8.8', 53),
                timeout=5
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False

    async def stop(self):
        """Остановка бота"""
        if self._is_shutting_down:
            return

        self._is_shutting_down = True
        logger.info("🛑 Остановка бота...")

        tasks_to_cancel = []
        if self._polling_task and not self._polling_task.done():
            tasks_to_cancel.append(self._polling_task)
        if self._alert_task and not self._alert_task.done():
            tasks_to_cancel.append(self._alert_task)
        if self._price_updater_task and not self._price_updater_task.done():
            tasks_to_cancel.append(self._price_updater_task)
        if self._cleanup_task and not self._cleanup_task.done():
            tasks_to_cancel.append(self._cleanup_task)

        for task in tasks_to_cancel:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self.alert_service.stop()
        await db.disconnect()
        await price_service.close()
        await self.storage.close()

        try:
            if self.bot.session:
                await asyncio.wait_for(self.bot.session.close(), timeout=10)
                logger.info("✅ Сессия бота закрыта")
        except asyncio.TimeoutError:
            logger.warning("⚠️ Таймаут при закрытии сессии бота")
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии сессии бота: {e}")

        logger.info("👋 Бот завершил работу")


async def main():
    """Главная функция"""
    setup_module_loggers()
    logger.info("🚀 Запуск приложения...")

    bot = CryptoBot()
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("🛑 Получен сигнал завершения")
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()

    if sys.platform != 'win32':
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            logger.warning("⚠️ Обработка сигналов не поддерживается на этой платформе")
    else:
        logger.info("🪟 Windows: используем альтернативную обработку сигналов")
        try:
            signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(shutdown(bot)))
            signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(shutdown(bot)))
        except:
            pass

    try:
        await bot.start()
    except asyncio.CancelledError:
        logger.info("🔄 Главная задача отменена")
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)
    finally:
        await bot.stop()
        logger.info("🏁 Приложение завершено")


async def shutdown(bot: CryptoBot):
    """Функция для graceful shutdown на Windows"""
    logger.info("🛑 Завершение работы...")
    await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот завершил работу")
    except Exception as e:
        logger.error(f"💥 Необработанная ошибка: {e}", exc_info=True)