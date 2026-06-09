import logging
import sys
import os
import time
import aiogram.exceptions
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from functools import wraps
import asyncio

from constants import LOG_DETAILED_FORMAT, LOG_SIMPLE_FORMAT, LOG_DATE_FORMAT, LOG_SEPARATOR

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


class WindowsSafeTimedRotatingFileHandler(TimedRotatingFileHandler):

    def __init__(self, filename, when='midnight', interval=1, backupCount=30,
                 encoding=None, delay=False, utc=False, atTime=None):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)

    def doRollover(self):
        """
        метод ротации
        """
        if self.stream:
            self.stream.close()
            self.stream = None

        dst_time = self.rolloverAt - self.interval

        if self.when == 'midnight' or self.when.startswith('D'):
            dfn = self.baseFilename + "." + time.strftime("%Y-%m-%d", time.localtime(dst_time))
        else:
            dfn = self.baseFilename + "." + time.strftime(self.suffix, time.localtime(dst_time))

        try:
            if os.path.exists(self.baseFilename):
                if os.path.exists(dfn):
                    try:
                        os.remove(dfn)
                    except OSError:
                        dfn = self.baseFilename + "." + time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(dst_time))

                try:
                    os.rename(self.baseFilename, dfn)
                except OSError as e:
                    self._safe_copy_log(self.baseFilename, dfn)

        except Exception as e:
            print(f"Ошибка при ротации логов: {e}", file=sys.stderr)

        if not self.delay:
            self.stream = self._open()

        self.rolloverAt = self.rolloverAt + self.interval

        if self.backupCount > 0:
            self._delete_old_logs()

    def _safe_copy_log(self, source, destination):
        """
        Безопасно копирует содержимое лог-файла при невозможности переименования.
        """
        try:
            with open(source, 'r', encoding='utf-8') as src:
                content = src.read()

            with open(destination, 'w', encoding='utf-8') as dst:
                dst.write(content)

            with open(source, 'w', encoding='utf-8') as src:
                src.truncate(0)

        except Exception as e:
            print(f"Ошибка при копировании лога: {e}", file=sys.stderr)

    def _delete_old_logs(self):
        """
        Удаляет старые лог-файлы, превышающие backupCount.
        """
        try:
            dir_name, base_name = os.path.split(self.baseFilename)
            pattern = base_name + ".*"

            files = []
            for file in Path(dir_name).glob(pattern):
                files.append((file.stat().st_mtime, file))

            files.sort()

            while len(files) > self.backupCount:
                _, oldest = files.pop(0)
                try:
                    oldest.unlink()
                except OSError:
                    pass

        except Exception:
            pass


class CustomLogger:
    """
    Класс для централизованного управления логированием.
    """

    def __init__(self, name: Optional[str] = None):
        """
        Инициализация логгера.
        """
        self.logger = logging.getLogger(name)
        self._configure()

    def _configure(self):
        """Базовая настройка логгера"""
        if self.logger.handlers:
            return

        self.logger.setLevel(logging.DEBUG)

        self._add_file_handler()
        self._add_console_handler()

    def _add_file_handler(self):
        """файловый обработчик"""
        try:
            file_handler = WindowsSafeTimedRotatingFileHandler(
                LOG_DIR / "bot.log",
                when="midnight",
                interval=1,
                backupCount=30,
                encoding='utf-8',
                delay=False
            )

            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                LOG_DETAILED_FORMAT,
                datefmt=LOG_DATE_FORMAT
            ))

            self.logger.addHandler(file_handler)

        except Exception as e:
            print(f"⚠️ Не удалось создать файловый обработчик логов: {e}", file=sys.stderr)

    def _add_console_handler(self):
        """консольный обработчик"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            LOG_SIMPLE_FORMAT,
            datefmt=LOG_DATE_FORMAT
        ))
        self.logger.addHandler(console_handler)

    def get_logger(self):
        """Возвращает настроенный логгер"""
        return self.logger


# Кэш для созданных логгеров
_loggers: Dict[str, logging.Logger] = {}


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    функция для получения настроенного логгера
    """
    if name not in _loggers:
        _loggers[name] = CustomLogger(name).get_logger()
    return _loggers[name]


def log_rotation_info():
    """Записывает информацию о ротации логов при запуске"""
    logger = get_logger('system')
    current_time = datetime.now().strftime(LOG_DATE_FORMAT)

    logger.info(LOG_SEPARATOR)
    logger.info(f"🚀 ЗАПУСК БОТА - {current_time}")
    logger.info(f"📁 Лог-файл: bot.log (ежедневная ротация в полночь)")
    logger.info(f"📊 Хранение логов: 30 дней")
    logger.info(f"💻 Платформа: {sys.platform}")
    logger.info(LOG_SEPARATOR)


def setup_module_loggers():
    """Настройка логгеров для основных модулей с разными уровнями"""

    # Логгер для bybit_client
    bybit_logger = get_logger('bybit_client')
    bybit_logger.setLevel(logging.DEBUG)

    # Логгер для handlers
    handlers_logger = get_logger('handlers')
    handlers_logger.setLevel(logging.INFO)

    # Логгер для alerts_storage
    alerts_logger = get_logger('alerts_storage')
    alerts_logger.setLevel(logging.WARNING)

    # Логгер для main
    main_logger = get_logger('main')
    main_logger.setLevel(logging.ERROR)

    # Логгер для системы
    system_logger = get_logger('system')
    system_logger.setLevel(logging.INFO)

    # Логгер для проверки уведомлений
    checker_logger = get_logger('alerts_checker')
    checker_logger.setLevel(logging.INFO)

    log_rotation_info()


def log_function_call(logger=None):
    """
    Декоратор для автоматического логирования вызовов функций.
    """

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
            except aiogram.exceptions.TelegramBadRequest as e:
                if "query is too old" in str(e) or "query ID is invalid" in str(e):
                    logger.debug(f"⚠️ Пропуск устаревшего callback в {func.__name__}: {e}")
                    return None
                logger.error(f"❌ Ошибка Telegram в {func.__name__}: {e}")
                raise
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