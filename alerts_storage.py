import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AlertsStorage:
    """
    Класс для хранения и управления уведомлениями пользователей в JSON файле.

    Обеспечивает:
    - Сохранение уведомлений между перезапусками бота
    - Загрузку уведомлений при старте
    - Автоматическое сохранение при изменениях
    - Безопасную работу с файловой системой

    Attributes:
        storage_path (Path): Путь к файлу с уведомлениями
        user_alerts (Dict): Словарь с уведомлениями пользователей
        auto_save (bool): Флаг автоматического сохранения при изменениях
    """

    def __init__(self, storage_path: str = "alerts.json", auto_save: bool = True):
        """
        Инициализирует хранилище уведомлений.

        Args:
            storage_path (str): Путь к файлу для хранения уведомлений
            auto_save (bool): Автоматически сохранять изменения в файл
        """
        self.storage_path = Path(storage_path)
        self.auto_save = auto_save
        self.user_alerts: Dict[int, List[Dict[str, Any]]] = {}

        # Загружаем существующие уведомления
        self.load()

    def load(self) -> bool:
        """
        Загружает уведомления из JSON файла.

        Returns:
            bool: True если загрузка успешна, False в противном случае
        """
        try:
            if not self.storage_path.exists():
                logger.info(f"Файл {self.storage_path} не найден, создаю новое хранилище")
                self.user_alerts = {}
                self.save()
                return True

            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Конвертируем строковые ключи обратно в int
            self.user_alerts = {int(user_id): alerts for user_id, alerts in data.items()}

            # Восстанавливаем числовые значения для price
            for user_id, alerts in self.user_alerts.items():
                for alert in alerts:
                    if 'target_price' in alert and isinstance(alert['target_price'], str):
                        alert['target_price'] = float(alert['target_price'])
                    if 'current_price' in alert and isinstance(alert['current_price'], str):
                        alert['current_price'] = float(alert['current_price'])

            logger.info(
                f"Загружено {self.get_total_alerts_count()} уведомлений для {len(self.user_alerts)} пользователей")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON файла {self.storage_path}: {e}")
            # Создаем резервную копию поврежденного файла
            self._backup_corrupted_file()
            self.user_alerts = {}
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки уведомлений: {e}")
            self.user_alerts = {}
            return False

    def save(self) -> bool:
        """
        Сохраняет уведомления в JSON файл.

        Returns:
            bool: True если сохранение успешно, False в противном случае
        """
        try:
            # Создаем временный файл для безопасной записи
            temp_path = self.storage_path.with_suffix('.tmp')

            # Подготавливаем данные для сериализации
            data_to_save = {}
            for user_id, alerts in self.user_alerts.items():
                # Конвертируем datetime в строку если нужно
                serialized_alerts = []
                for alert in alerts:
                    alert_copy = alert.copy()
                    if 'created_at' in alert_copy and isinstance(alert_copy['created_at'], datetime):
                        alert_copy['created_at'] = alert_copy['created_at'].isoformat()
                    serialized_alerts.append(alert_copy)
                data_to_save[str(user_id)] = serialized_alerts

            # Записываем во временный файл
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)

            # Заменяем основной файл временным
            temp_path.replace(self.storage_path)

            logger.debug(f"💾 Сохранено {self.get_total_alerts_count()} уведомлений")
            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения уведомлений: {e}")
            return False

    def _backup_corrupted_file(self):
        """
        Создает резервную копию поврежденного файла.
        """
        if self.storage_path.exists():
            backup_path = self.storage_path.with_suffix('.json.bak')
            try:
                # Добавляем временную метку к имени резервной копии
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.storage_path.parent / f"alerts_{timestamp}.json.bak"
                self.storage_path.rename(backup_path)
                logger.info(f"📦 Поврежденный файл сохранен как {backup_path}")
            except Exception as e:
                logger.error(f"Не удалось создать резервную копию: {e}")

    def add_alert(self, user_id: int, alert_data: Dict[str, Any]) -> int:
        """
        Добавляет новое уведомление для пользователя.

        Args:
            user_id (int): ID пользователя Telegram
            alert_data (Dict): Данные уведомления

        Returns:
            int: ID созданного уведомления
        """
        if user_id not in self.user_alerts:
            self.user_alerts[user_id] = []

        # Генерируем уникальный ID
        if self.user_alerts[user_id]:
            alert_id = max(alert['id'] for alert in self.user_alerts[user_id]) + 1
        else:
            alert_id = 1

        # Добавляем ID в данные уведомления
        alert_data['id'] = alert_id

        # Добавляем временную метку если её нет
        if 'created_at' not in alert_data:
            alert_data['created_at'] = datetime.now().isoformat()

        self.user_alerts[user_id].append(alert_data)

        if self.auto_save:
            self.save()

        logger.info(f"✅ Добавлено уведомление #{alert_id} для пользователя {user_id}")
        return alert_id

    def remove_alert(self, user_id: int, alert_id: int) -> bool:
        """
        Удаляет конкретное уведомление пользователя.

        Args:
            user_id (int): ID пользователя Telegram
            alert_id (int): ID уведомления

        Returns:
            bool: True если удаление успешно, False если уведомление не найдено
        """
        if user_id not in self.user_alerts:
            return False

        for i, alert in enumerate(self.user_alerts[user_id]):
            if alert['id'] == alert_id:
                removed_alert = self.user_alerts[user_id].pop(i)

                # Если у пользователя не осталось уведомлений, удаляем запись
                if not self.user_alerts[user_id]:
                    del self.user_alerts[user_id]

                if self.auto_save:
                    self.save()

                logger.info(f"🗑️ Удалено уведомление #{alert_id} для пользователя {user_id}")
                return True

        return False

    def remove_all_user_alerts(self, user_id: int) -> int:
        """
        Удаляет все уведомления пользователя.

        Args:
            user_id (int): ID пользователя Telegram

        Returns:
            int: Количество удаленных уведомлений
        """
        if user_id not in self.user_alerts:
            return 0

        count = len(self.user_alerts[user_id])
        del self.user_alerts[user_id]

        if self.auto_save:
            self.save()

        logger.info(f"🗑️ Удалено {count} уведомлений пользователя {user_id}")
        return count

    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Возвращает список уведомлений пользователя.

        Args:
            user_id (int): ID пользователя Telegram

        Returns:
            List[Dict]: Список уведомлений пользователя
        """
        return self.user_alerts.get(user_id, []).copy()

    def get_alert(self, user_id: int, alert_id: int) -> Optional[Dict[str, Any]]:
        """
        Возвращает конкретное уведомление пользователя.

        Args:
            user_id (int): ID пользователя Telegram
            alert_id (int): ID уведомления

        Returns:
            Optional[Dict]: Уведомление или None если не найдено
        """
        alerts = self.user_alerts.get(user_id, [])
        for alert in alerts:
            if alert['id'] == alert_id:
                return alert.copy()
        return None

    def update_alert(self, user_id: int, alert_id: int, updated_data: Dict[str, Any]) -> bool:
        """
        Обновляет существующее уведомление.

        Args:
            user_id (int): ID пользователя Telegram
            alert_id (int): ID уведомления
            updated_data (Dict): Новые данные для уведомления

        Returns:
            bool: True если обновление успешно, False если уведомление не найдено
        """
        if user_id not in self.user_alerts:
            return False

        for i, alert in enumerate(self.user_alerts[user_id]):
            if alert['id'] == alert_id:
                # Сохраняем ID
                updated_data['id'] = alert_id
                # Сохраняем дату создания если есть
                if 'created_at' in alert:
                    updated_data['created_at'] = alert['created_at']

                self.user_alerts[user_id][i] = updated_data

                if self.auto_save:
                    self.save()

                logger.info(f"✏️ Обновлено уведомление #{alert_id} для пользователя {user_id}")
                return True

        return False

    def has_user_alerts(self, user_id: int) -> bool:
        """
        Проверяет, есть ли у пользователя уведомления.

        Args:
            user_id (int): ID пользователя Telegram

        Returns:
            bool: True если есть уведомления
        """
        return user_id in self.user_alerts and len(self.user_alerts[user_id]) > 0

    def get_total_alerts_count(self) -> int:
        """
        Возвращает общее количество уведомлений в системе.

        Returns:
            int: Общее количество уведомлений
        """
        return sum(len(alerts) for alerts in self.user_alerts.values())

    def get_all_users(self) -> List[int]:
        """
        Возвращает список всех пользователей с уведомлениями.

        Returns:
            List[int]: Список ID пользователей
        """
        return list(self.user_alerts.keys())

    def get_alerts_by_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Возвращает все уведомления для конкретной криптовалюты.

        Args:
            symbol (str): Торговый символ

        Returns:
            List[Dict]: Список уведомлений для указанного символа
        """
        result = []
        for user_id, alerts in self.user_alerts.items():
            for alert in alerts:
                if alert.get('symbol') == symbol:
                    alert_copy = alert.copy()
                    alert_copy['user_id'] = user_id
                    result.append(alert_copy)
        return result

    def cleanup_completed_alerts(self, completed_alert_ids: List[tuple]) -> int:
        """
        Удаляет выполненные уведомления.

        Args:
            completed_alert_ids (List[tuple]): Список кортежей (user_id, alert_id)

        Returns:
            int: Количество удаленных уведомлений
        """
        removed_count = 0
        for user_id, alert_id in completed_alert_ids:
            if self.remove_alert(user_id, alert_id):
                removed_count += 1

        return removed_count

    def export_to_dict(self) -> Dict:
        """
        Экспортирует все уведомления в словарь.

        Returns:
            Dict: Словарь со всеми уведомлениями
        """
        return {
            str(user_id): alerts.copy()
            for user_id, alerts in self.user_alerts.items()
        }

    def import_from_dict(self, data: Dict) -> int:
        """
        Импортирует уведомления из словаря.

        Args:
            data (Dict): Словарь с уведомлениями

        Returns:
            int: Количество импортированных уведомлений
        """
        count = 0
        for user_id_str, alerts in data.items():
            user_id = int(user_id_str)
            if user_id not in self.user_alerts:
                self.user_alerts[user_id] = []

            for alert in alerts:
                # Проверяем наличие обязательных полей
                if 'id' in alert and 'symbol' in alert and 'target_price' in alert:
                    self.user_alerts[user_id].append(alert)
                    count += 1

        if self.auto_save:
            self.save()

        logger.info(f"📥 Импортировано {count} уведомлений")
        return count