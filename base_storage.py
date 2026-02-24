import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
from abc import ABC, abstractmethod
from logger import get_logger
from decimal import Decimal
from utils import to_decimal


class DecimalEncoder(json.JSONEncoder):
    """JSON энкодер для Decimal объектов."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class BaseStorage(ABC):
    """
    Абстрактный базовый класс для всех хранилищ данных.

    Предоставляет общие методы для работы с JSON файлами:
    - Загрузка и сохранение данных
    - Создание резервных копий
    - Безопасная запись через временный файл
    """

    def __init__(self, storage_path: str, auto_save: bool = True):
        """
        Инициализация базового хранилища.

        Args:
            storage_path: Путь к файлу хранилища
            auto_save: Автоматически сохранять изменения
        """
        self.storage_path = Path(storage_path)
        self.auto_save = auto_save
        self.modified = False
        self.logger = get_logger(self.__class__.__name__)

        self.logger.info(f"📁 Инициализация хранилища: {storage_path}")
        self._data: Dict = {}
        self.load()

    @abstractmethod
    def _deserialize(self, data: Dict) -> Dict:
        """
        Десериализация данных после загрузки.
        Должен быть переопределен в дочерних классах.

        Args:
            data: Сырые данные из JSON

        Returns:
            Dict: Обработанные данные
        """
        pass

    @abstractmethod
    def _serialize(self, data: Dict) -> Dict:
        """
        Сериализация данных перед сохранением.
        Должен быть переопределен в дочерних классах.

        Args:
            data: Данные для сохранения

        Returns:
            Dict: Данные готовые для JSON
        """
        pass

    def load(self) -> bool:
        """
        Загружает данные из JSON файла.

        Returns:
            bool: True если загрузка успешна
        """
        try:
            if not self.storage_path.exists():
                self.logger.info(f"📄 Файл {self.storage_path} не найден, создаю новое хранилище")
                self._data = {}
                self.save()
                return True

            with open(self.storage_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            self._data = self._deserialize(raw_data)
            self.logger.info(f"✅ Данные загружены из {self.storage_path}")
            return True

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Ошибка парсинга JSON: {e}")
            self._backup_corrupted_file()
            self._data = {}
            return False
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки: {e}")
            self._data = {}
            return False

    def save(self) -> bool:
        """
        Сохраняет данные в JSON файл.

        Returns:
            bool: True если сохранение успешно
        """
        try:
            temp_path = self.storage_path.with_suffix('.tmp')

            data_to_save = self._serialize(self._data)

            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False, cls=DecimalEncoder)

            temp_path.replace(self.storage_path)

            self.modified = False
            self.logger.debug(f"💾 Данные сохранены в {self.storage_path}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения: {e}")
            return False

    def _backup_corrupted_file(self):
        """
        Создает резервную копию поврежденного файла.
        """
        if self.storage_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.storage_path.parent / f"{self.storage_path.stem}_{timestamp}.json.bak"

            try:
                self.storage_path.rename(backup_path)
                self.logger.info(f"📦 Поврежденный файл сохранен как {backup_path}")
            except Exception as e:
                self.logger.error(f"❌ Не удалось создать резервную копию: {e}")

    def _auto_save_if_needed(self):
        """
        Автоматически сохраняет данные если включен auto_save.
        """
        if self.auto_save and self.modified:
            self.save()

    def get_all(self) -> Dict:
        """
        Возвращает все данные.

        Returns:
            Dict: Все данные хранилища
        """
        return self._data.copy()

    def clear(self):
        """
        Очищает все данные.
        """
        self._data.clear()
        self.modified = True
        self._auto_save_if_needed()
        self.logger.info("🧹 Все данные очищены")

    @property
    def is_empty(self) -> bool:
        """
        Проверяет, пусто ли хранилище.

        Returns:
            bool: True если хранилище пусто
        """
        return len(self._data) == 0

    @property
    def size(self) -> int:
        """
        Возвращает размер данных.

        Returns:
            int: Количество элементов
        """
        return len(self._data)