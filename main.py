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
    """
    Главный класс крипто-бота для Telegram.

    Этот класс отвечает за инициализацию всех компонентов бота:
    - Создание экземпляра бота с токеном и настройками
    - Настройка диспетчера с FSM хранилищем
    - Регистрация обработчиков команд и сообщений
    - Запуск процесса поллинга

    Attributes:
        storage (MemoryStorage): Хранилище состояний FSM в оперативной памяти
        bot (Bot): Экземпляр бота Aiogram для взаимодействия с Telegram API
        dp (Dispatcher): Диспетчер для маршрутизации обновлений
    """

    def __init__(self):
        """
        Инициализирует компоненты бота.

        Создает хранилище, экземпляр бота с настройками по умолчанию,
        диспетчер и регистрирует все обработчики.
        """
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
        """
        Запускает процесс получения обновлений от Telegram.

        Выполняет следующие действия:
        1. Логирует информацию о запуске
        2. Удаляет вебхук (если был установлен)
        3. Запускает поллинг для получения обновлений

        Returns:
            None
        """
        logger.info("🚀 Запуск крипто-бота с кнопочным интерфейсом...")

        # Удаляем вебхук
        await self.bot.delete_webhook(drop_pending_updates=True)

        # Запускаем поллинг
        await self.dp.start_polling(self.bot)


async def main():
    """
    Главная асинхронная функция для запуска бота.

    Создает экземпляр бота и запускает его, обрабатывая возможное
    прерывание от пользователя (Ctrl+C).

    Returns:
        None
    """
    bot = CryptoBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")


if __name__ == "__main__":
    asyncio.run(main())