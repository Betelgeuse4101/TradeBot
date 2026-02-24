import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime
import os

# Создаем директорию для логов если её нет
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Форматы логов
DETAILED_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
SIMPLE_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class CustomLogger:
    """
    Класс для централизованного управления логированием.

    Позволяет:
    - Настраивать форматирование логов
    - Управлять выводом в файл и консоль
    - Ежедневная ротация лог-файлов
    - Хранение логов за последние 30 дней
    - Разные уровни логирования для разных модулей
    """

    def __init__(self, name: str = None):
        """
        Инициализация логгера.

        Args:
            name (str): Имя логгера (обычно __name__)
        """
        self.logger = logging.getLogger(name)
        self._configure()

    def _configure(self):
        """Базовая настройка логгера"""
        # Предотвращаем добавление нескольких обработчиков
        if self.logger.handlers:
            return

        self.logger.setLevel(logging.DEBUG)

        # Создаем обработчики
        self._add_file_handler()
        self._add_console_handler()

    def _add_file_handler(self):
        """Добавляет файловый обработчик с ежедневной ротацией"""
        # Создаем обработчик с ротацией раз в день
        file_handler = TimedRotatingFileHandler(
            LOG_DIR / "bot.log",
            when="midnight",  # Ротация в полночь
            interval=1,  # Каждый день
            backupCount=30,  # Хранить логи за последние 30 дней
            encoding='utf-8',
            utc=False  # Использовать локальное время
        )

        # Настройка формата имени для ротированных файлов
        # bot.log -> bot.log.2026-02-24
        file_handler.suffix = "%Y-%m-%d"

        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            DETAILED_FORMAT,
            datefmt=DATE_FORMAT
        ))

        # Добавляем фильтр для записи даты ротации
        file_handler.addFilter(self._add_rotation_marker)

        self.logger.addHandler(file_handler)

    def _add_console_handler(self):
        """Добавляет консольный обработчик"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            SIMPLE_FORMAT,
            datefmt=DATE_FORMAT
        ))
        self.logger.addHandler(console_handler)

    @staticmethod
    def _add_rotation_marker(record):
        """Добавляет маркер при ротации логов"""
        # Проверяем, есть ли уже атрибут rotation_marker
        if not hasattr(record, 'rotation_marker'):
            # Если файл только что создан (размер 0), добавляем маркер
            log_file = LOG_DIR / "bot.log"
            if log_file.exists() and log_file.stat().st_size == 0:
                record.rotation_marker = True
            else:
                record.rotation_marker = False
        return True

    def get_logger(self):
        """Возвращает настроенный логгер"""
        return self.logger


# Словарь для хранения созданных логгеров
_loggers = {}


def get_logger(name: str = None) -> logging.Logger:
    """
    Фабричная функция для получения настроенного логгера.

    Args:
        name (str): Имя модуля (обычно __name__)

    Returns:
        logging.Logger: Настроенный логгер
    """
    if name not in _loggers:
        _loggers[name] = CustomLogger(name).get_logger()
    return _loggers[name]


def log_rotation_info():
    """
    Записывает информацию о ротации логов при запуске бота.
    Вызывается при каждом запуске для отметки в лог-файле.
    """
    logger = get_logger('system')
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Красивое разделение между сессиями
    separator = "=" * 80

    logger.info(separator)
    logger.info(f"🚀 ЗАПУСК БОТА - {current_time}")
    logger.info(f"📁 Лог-файл: bot.log (ежедневная ротация в полночь)")
    logger.info(f"📊 Хранение логов: 30 дней")
    logger.info(separator)


def setup_module_loggers():
    """Настройка логгеров для основных модулей с разными уровнями"""

    # Логгер для bybit_client - больше деталей
    bybit_logger = get_logger('bybit_client')
    bybit_logger.setLevel(logging.DEBUG)

    # Логгер для handlers - важные события
    handlers_logger = get_logger('handlers')
    handlers_logger.setLevel(logging.INFO)

    # Логгер для alerts_storage - ошибки и предупреждения
    alerts_logger = get_logger('alerts_storage')
    alerts_logger.setLevel(logging.WARNING)

    # Логгер для main - только критическое
    main_logger = get_logger('main')
    main_logger.setLevel(logging.ERROR)

    # Логгер для системы
    system_logger = get_logger('system')
    system_logger.setLevel(logging.INFO)

    # Записываем информацию о запуске
    log_rotation_info()


def cleanup_old_logs(days: int = 30):
    """
    Дополнительная очистка старых логов.
    Может быть вызвана при необходимости.

    Args:
        days (int): Удалять логи старше указанного количества дней
    """
    import time

    logger = get_logger('system')
    current_time = time.time()
    deleted_count = 0

    for log_file in LOG_DIR.glob("bot.log.*"):
        # Получаем время модификации файла
        file_time = log_file.stat().st_mtime
        # Если файл старше days дней
        if current_time - file_time > days * 24 * 3600:
            try:
                log_file.unlink()
                deleted_count += 1
                logger.info(f"🧹 Удален старый лог-файл: {log_file.name}")
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении {log_file.name}: {e}")

    if deleted_count > 0:
        logger.info(f"✅ Удалено {deleted_count} старых лог-файлов")


# Декоратор для логирования функций
def log_function_call(logger=None):
    """
    Декоратор для автоматического логирования вызовов функций.

    Args:
        logger: Логгер для использования

    Returns:
        function: Декорированная функция
    """
    import asyncio
    from functools import wraps

    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.debug(f"▶️ Вызов {func.__name__}")
            try:
                result = await func(*args, **kwargs)
                logger.debug(f"✅ {func.__name__} завершена")
                return result
            except Exception as e:
                logger.error(f"❌ Ошибка в {func.__name__}: {e}", exc_info=True)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger.debug(f"▶️ Вызов {func.__name__}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"✅ {func.__name__} завершена")
                return result
            except Exception as e:
                logger.error(f"❌ Ошибка в {func.__name__}: {e}", exc_info=True)
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# Контекстный менеджер для временного изменения уровня логирования
class LogLevelContext:
    """Контекстный менеджер для временного изменения уровня логирования"""

    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self.old_level = None

    def __enter__(self):
        self.old_level = self.logger.level
        self.logger.setLevel(self.level)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.old_level)


# Функция для получения статистики по логам
def get_log_stats():
    """
    Возвращает статистику по лог-файлам.

    Returns:
        dict: Статистика по логам
    """
    stats = {
        'total_size': 0,
        'files': [],
        'current_log_size': 0
    }

    current_log = LOG_DIR / "bot.log"
    if current_log.exists():
        stats['current_log_size'] = current_log.stat().st_size
        stats['files'].append({
            'name': 'bot.log',
            'size': current_log.stat().st_size,
            'modified': datetime.fromtimestamp(current_log.stat().st_mtime).strftime(DATE_FORMAT)
        })

    for log_file in sorted(LOG_DIR.glob("bot.log.*")):
        file_size = log_file.stat().st_size
        stats['total_size'] += file_size
        stats['files'].append({
            'name': log_file.name,
            'size': file_size,
            'modified': datetime.fromtimestamp(log_file.stat().st_mtime).strftime(DATE_FORMAT)
        })

    stats['total_size_mb'] = stats['total_size'] / (1024 * 1024)

    return stats