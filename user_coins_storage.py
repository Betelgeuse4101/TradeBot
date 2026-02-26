import json
from typing import Dict, List
from pathlib import Path
from datetime import datetime
from logger import get_logger, log_function_call
from config import Config


class UserCoinsStorage:
    """
    Класс для хранения и управления пользовательскими списками монет.

    Каждый пользователь может иметь свой персональный список отслеживаемых монет.
    """

    def __init__(self, storage_path: str = "user_coins.json"):
        """
        Инициализирует хранилище пользовательских монет.

        Args:
            storage_path: Путь к файлу с данными
        """
        self.storage_path = Path(storage_path)
        self.logger = get_logger('user_coins')
        self._data: Dict[str, Dict] = self._load()

        # Базовая структура для пользователя
        self.default_structure = {
            'coins': [],  # Список монет пользователя
            'updated_at': None,  # Время последнего обновления
            'created_at': None  # Время создания
        }

    def _load(self) -> Dict:
        """
        Загружает данные из файла.

        Returns:
            Dict: Загруженные данные
        """
        try:
            if not self.storage_path.exists():
                self.logger.info(f"📄 Файл {self.storage_path} не найден, создаю новое хранилище")
                return {}

            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.logger.info(f"✅ Данные пользовательских монет загружены из {self.storage_path}")
            return data

        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки пользовательских монет: {e}")
            return {}

    def _save(self):
        """Сохраняет данные в файл."""
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            self.logger.debug("💾 Данные пользовательских монет сохранены")
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения пользовательских монет: {e}")

    def _ensure_user(self, user_id: int):
        """
        Убеждается, что для пользователя есть запись.

        Args:
            user_id: ID пользователя
        """
        user_id_str = str(user_id)
        if user_id_str not in self._data:
            self._data[user_id_str] = {
                'coins': [],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

    @log_function_call()
    def add_user_coin(self, user_id: int, symbol: str) -> bool:
        """
        Добавляет монету в список пользователя.

        Args:
            user_id: ID пользователя
            symbol: Торговый символ (например, "BTCUSDT")

        Returns:
            bool: True если добавлено успешно
        """
        symbol = symbol.upper()
        self._ensure_user(user_id)

        user_id_str = str(user_id)
        user_coins = self._data[user_id_str]['coins']

        if symbol not in user_coins:
            user_coins.append(symbol)
            self._data[user_id_str]['updated_at'] = datetime.now().isoformat()
            self._save()

            self.logger.info(f"➕ Пользователь {user_id} добавил монету {symbol}")
            return True

        self.logger.debug(f"ℹ️ Монета {symbol} уже есть у пользователя {user_id}")
        return False

    @log_function_call()
    def remove_user_coin(self, user_id: int, symbol: str) -> bool:
        """
        Удаляет монету из списка пользователя.

        Args:
            user_id: ID пользователя
            symbol: Торговый символ

        Returns:
            bool: True если удалено успешно
        """
        symbol = symbol.upper()
        user_id_str = str(user_id)

        if user_id_str not in self._data:
            return False

        user_coins = self._data[user_id_str]['coins']

        if symbol in user_coins:
            user_coins.remove(symbol)
            self._data[user_id_str]['updated_at'] = datetime.now().isoformat()
            self._save()

            self.logger.info(f"➖ Пользователь {user_id} удалил монету {symbol}")
            return True

        return False

    def get_user_coins(self, user_id: int) -> List[str]:
        """
        Возвращает список монет пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            List[str]: Список торговых символов
        """
        user_id_str = str(user_id)
        if user_id_str in self._data:
            return self._data[user_id_str]['coins'].copy()
        return []

    def get_all_user_coins(self, user_id: int) -> List[str]:
        """
        Возвращает ВСЕ монеты пользователя (популярные + пользовательские).

        Args:
            user_id: ID пользователя

        Returns:
            List[str]: Полный список монет
        """
        # Популярные монеты
        popular_coins = list(Config.POPULAR_CRYPTO.values())

        # Пользовательские монеты
        user_coins = self.get_user_coins(user_id)

        # Объединяем и удаляем дубликаты
        all_coins = list(set(popular_coins + user_coins))

        return sorted(all_coins)

    def get_available_coins(self, user_id: int) -> List[str]:
        """
        Возвращает монеты, которые пользователь еще не добавил.

        Args:
            user_id: ID пользователя

        Returns:
            List[str]: Список доступных для добавления монет
        """
        # Здесь можно добавить логику получения всех доступных монет с биржи
        popular_coins = list(Config.POPULAR_CRYPTO.values())
        user_coins = self.get_user_coins(user_id)

        available = [coin for coin in popular_coins if coin not in user_coins]
        return available

    def has_user_coin(self, user_id: int, symbol: str) -> bool:
        """
        Проверяет, есть ли монета в списке пользователя.

        Args:
            user_id: ID пользователя
            symbol: Торговый символ

        Returns:
            bool: True если монета есть в списке
        """
        user_coins = self.get_user_coins(user_id)
        return symbol.upper() in user_coins

    def get_user_coins_count(self, user_id: int) -> int:
        """
        Возвращает количество монет пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            int: Количество монет
        """
        return len(self.get_user_coins(user_id))

    @log_function_call()
    def clear_user_coins(self, user_id: int) -> int:
        """
        Очищает список монет пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            int: Количество удаленных монет
        """
        user_id_str = str(user_id)
        if user_id_str not in self._data:
            return 0

        count = len(self._data[user_id_str]['coins'])
        self._data[user_id_str]['coins'] = []
        self._data[user_id_str]['updated_at'] = datetime.now().isoformat()
        self._save()

        self.logger.info(f"🧹 Пользователь {user_id} очистил список монет (удалено {count})")
        return count

    def get_stats(self) -> Dict:
        """
        Возвращает статистику по пользовательским монетам.

        Returns:
            Dict: Статистика
        """
        total_users = len(self._data)
        total_coins = sum(len(data['coins']) for data in self._data.values())

        # Самые популярные монеты среди пользователей
        coin_stats = {}
        for user_data in self._data.values():
            for coin in user_data['coins']:
                coin_stats[coin] = coin_stats.get(coin, 0) + 1

        top_coins = sorted(coin_stats.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            'total_users': total_users,
            'total_custom_coins': total_coins,
            'avg_coins_per_user': round(total_coins / total_users, 2) if total_users > 0 else 0,
            'top_custom_coins': dict(top_coins)
        }


# Создаем глобальный экземпляр
user_coins_storage = UserCoinsStorage()