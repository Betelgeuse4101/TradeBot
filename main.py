import asyncio
import signal
import sys
from config import Config
from database.db import db
from handlers import common, portfolio, assets, alerts
from logger import get_logger, setup_module_loggers
from services.alert_service import AlertService
from services.price_service import price_service
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import ClientTimeout, TCPConnector
import aiohttp

logger = get_logger('main')


class CryptoBot:
    """Главный класс бота"""

    def __init__(self):
        self.storage = MemoryStorage()
        self.bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher(storage=self.storage)
        self.alert_service = AlertService(self.bot)
        self._polling_task = None
        self._alert_task = None

        # Регистрация роутеров
        self.dp.include_router(common.router)
        self.dp.include_router(portfolio.router)
        self.dp.include_router(assets.router)
        self.dp.include_router(alerts.router)

    async def start(self):
        """Запуск бота"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК ИНВЕСТИЦИОННОГО БОТА С MOEX")
        logger.info("=" * 60)

        # Подключение к БД
        await db.connect()

        # Удаление вебхука
        await self.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Вебхук удален")

        # Запуск сервиса уведомлений
        self._alert_task = asyncio.create_task(self.alert_service.start())
        logger.info("✅ Сервис уведомлений запущен")

        # Запуск поллинга
        logger.info("📡 Запуск поллинга...")
        self._polling_task = asyncio.create_task(self.dp.start_polling(self.bot))

        # Ждем завершения задач
        try:
            await self._polling_task
        except asyncio.CancelledError:
            logger.info("🔄 Поллинг остановлен")
        finally:
            await self.stop()

    async def stop(self):
        """Остановка бота"""
        logger.info("🛑 Остановка бота...")

        # Отменяем задачи
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        # Остановка сервиса уведомлений
        if self._alert_task and not self._alert_task.done():
            self._alert_task.cancel()
            try:
                await self._alert_task
            except asyncio.CancelledError:
                pass

        await self.alert_service.stop()

        # Закрытие соединений
        await db.disconnect()
        await price_service.close()

        # Закрываем сессию бота
        if self.bot.session:
            await self.bot.session.close()

        logger.info("👋 Бот завершил работу")


async def main():
    """Главная функция"""
    # Настройка логгеров
    setup_module_loggers()

    bot = CryptoBot()

    # Настройка обработки сигналов
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("🛑 Получен сигнал завершения")
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()

    # Регистрируем обработчики сигналов (только для Unix-like систем)
    if sys.platform != 'win32':
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)

    try:
        await bot.start()
    except asyncio.CancelledError:
        logger.info("🔄 Главная задача отменена")
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Программа завершена")