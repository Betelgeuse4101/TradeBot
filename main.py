import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import Config
from handlers import register_handlers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CryptoBot:
    def __init__(self):
        # Инициализация бота с FSM хранилищем
        self.storage = MemoryStorage()
        self.bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher(storage=self.storage)

        # Регистрация обработчиков
        register_handlers(self.dp, self.bot)

    async def start(self):
        """Запуск бота"""
        logger.info("🚀 Запуск крипто-бота с кнопочным интерфейсом...")

        # Удаляем вебхук
        await self.bot.delete_webhook(drop_pending_updates=True)

        # Запускаем поллинг
        await self.dp.start_polling(self.bot)


async def main():
    bot = CryptoBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")


if __name__ == "__main__":
    asyncio.run(main())