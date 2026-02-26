from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from base_storage import BaseStorage
from logger import log_function_call
from utils import safe_iso_format, to_decimal
from constants import ALERT_DIRECTION_UP, ALERT_DIRECTION_DOWN


class AlertsStorage(BaseStorage):
    """
    Класс для хранения и управления уведомлениями пользователей.
    """

    def __init__(self, storage_path: str = "alerts.json", auto_save: bool = True):
        """
        Инициализирует хранилище уведомлений.

        Args:
            storage_path: Путь к файлу с уведомлениями
            auto_save: Автоматически сохранять изменения
        """
        super().__init__(storage_path, auto_save)
        self.user_alerts: Dict[int, List[Dict[str, Any]]] = self._data

    def _deserialize(self, data: Dict) -> Dict:
        """
        Десериализует данные после загрузки.

        Args:
            data: Сырые данные из JSON

        Returns:
            Dict: Обработанные данные
        """
        result = {}
        for user_id_str, alerts in data.items():
            user_id = int(user_id_str)
            result[user_id] = []

            for alert in alerts:
                alert_copy = alert.copy()
                # Восстанавливаем Decimal значения
                if 'target_price' in alert_copy:
                    alert_copy['target_price'] = to_decimal(alert_copy['target_price'])
                if 'current_price' in alert_copy:
                    alert_copy['current_price'] = to_decimal(alert_copy['current_price'])
                result[user_id].append(alert_copy)

        return result

    def _serialize(self, data: Dict) -> Dict:
        """
        Сериализует данные перед сохранением.

        Args:
            data: Данные для сохранения

        Returns:
            Dict: Данные готовые для JSON
        """
        result = {}
        for user_id, alerts in data.items():
            serialized_alerts = []
            for alert in alerts:
                alert_copy = alert.copy()
                # Конвертируем datetime в строку
                if 'created_at' in alert_copy and isinstance(alert_copy['created_at'], datetime):
                    alert_copy['created_at'] = safe_iso_format(alert_copy['created_at'])
                # Decimal автоматически преобразуется в строку через DecimalEncoder
                serialized_alerts.append(alert_copy)
            result[str(user_id)] = serialized_alerts

        return result

    @log_function_call()
    def add_alert(self, user_id: int, alert_data: Dict[str, Any]) -> int:
        """
        Добавляет новое уведомление для пользователя.

        Args:
            user_id: ID пользователя
            alert_data: Данные уведомления

        Returns:
            int: ID созданного уведомления
        """
        if user_id not in self.user_alerts:
            self.user_alerts[user_id] = []
            self.logger.debug(f"👤 Создана запись для пользователя {user_id}")

        # Генерируем уникальный ID
        if self.user_alerts[user_id]:
            alert_id = max(a['id'] for a in self.user_alerts[user_id]) + 1
        else:
            alert_id = 1

        alert_data['id'] = alert_id

        if 'created_at' not in alert_data:
            alert_data['created_at'] = datetime.now()

        self.user_alerts[user_id].append(alert_data)
        self.modified = True

        self._auto_save_if_needed()

        self.logger.info(
            f"✅ Добавлено уведомление #{alert_id} для пользователя {user_id}: "
            f"{alert_data.get('symbol')} {alert_data.get('direction')} до {alert_data.get('target_price')}"
        )

        return alert_id

    @log_function_call()
    def remove_alert(self, user_id: int, alert_id: int) -> bool:
        """
        Удаляет конкретное уведомление пользователя.

        Args:
            user_id: ID пользователя
            alert_id: ID уведомления

        Returns:
            bool: True если удаление успешно
        """
        if user_id not in self.user_alerts:
            self.logger.warning(f"⚠️ Пользователь {user_id} не найден")
            return False

        for i, alert in enumerate(self.user_alerts[user_id]):
            if alert['id'] == alert_id:
                removed = self.user_alerts[user_id].pop(i)

                if not self.user_alerts[user_id]:
                    del self.user_alerts[user_id]

                self.modified = True
                self._auto_save_if_needed()

                self.logger.info(
                    f"🗑️ Удалено уведомление #{alert_id} для пользователя {user_id} "
                    f"({removed.get('symbol', 'unknown')})"
                )
                return True

        self.logger.warning(f"⚠️ Уведомление #{alert_id} для пользователя {user_id} не найдено")
        return False

    @log_function_call()
    def remove_all_user_alerts(self, user_id: int) -> int:
        """
        Удаляет все уведомления пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            int: Количество удаленных уведомлений
        """
        if user_id not in self.user_alerts:
            return 0

        count = len(self.user_alerts[user_id])
        del self.user_alerts[user_id]
        self.modified = True

        self._auto_save_if_needed()

        self.logger.info(f"🗑️ Удалено {count} уведомлений пользователя {user_id}")
        return count

    def get_user_alerts(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Возвращает список уведомлений пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            List[Dict]: Список уведомлений
        """
        return self.user_alerts.get(user_id, []).copy()

    def get_alert(self, user_id: int, alert_id: int) -> Optional[Dict[str, Any]]:
        """
        Возвращает конкретное уведомление пользователя.

        Args:
            user_id: ID пользователя
            alert_id: ID уведомления

        Returns:
            Optional[Dict]: Уведомление или None
        """
        alerts = self.user_alerts.get(user_id, [])
        for alert in alerts:
            if alert['id'] == alert_id:
                return alert.copy()
        return None

    @log_function_call()
    def update_alert(self, user_id: int, alert_id: int, updated_data: Dict[str, Any]) -> bool:
        """
        Обновляет существующее уведомление.

        Args:
            user_id: ID пользователя
            alert_id: ID уведомления
            updated_data: Новые данные

        Returns:
            bool: True если обновление успешно
        """
        if user_id not in self.user_alerts:
            return False

        for i, alert in enumerate(self.user_alerts[user_id]):
            if alert['id'] == alert_id:
                updated_data['id'] = alert_id
                if 'created_at' in alert:
                    updated_data['created_at'] = alert['created_at']

                self.user_alerts[user_id][i] = updated_data
                self.modified = True
                self._auto_save_if_needed()

                self.logger.info(f"✏️ Обновлено уведомление #{alert_id} для пользователя {user_id}")
                return True

        return False

    def has_user_alerts(self, user_id: int) -> bool:
        """
        Проверяет, есть ли у пользователя уведомления.

        Args:
            user_id: ID пользователя

        Returns:
            bool: True если есть уведомления
        """
        return user_id in self.user_alerts and len(self.user_alerts[user_id]) > 0

    def get_total_alerts_count(self) -> int:
        """
        Возвращает общее количество уведомлений.

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
            symbol: Торговый символ

        Returns:
            List[Dict]: Список уведомлений
        """
        result = []
        for user_id, alerts in self.user_alerts.items():
            for alert in alerts:
                if alert.get('symbol') == symbol:
                    alert_copy = alert.copy()
                    alert_copy['user_id'] = user_id
                    result.append(alert_copy)

        self.logger.debug(f"🔍 Найдено {len(result)} уведомлений для {symbol}")
        return result

    @log_function_call()
    def cleanup_completed_alerts(self, completed_alert_ids: List[Tuple[int, int]]) -> int:
        """
        Удаляет выполненные уведомления.

        Args:
            completed_alert_ids: Список кортежей (user_id, alert_id)

        Returns:
            int: Количество удаленных уведомлений
        """
        removed_count = 0
        for user_id, alert_id in completed_alert_ids:
            if self.remove_alert(user_id, alert_id):
                removed_count += 1

        if removed_count > 0:
            self.logger.info(f"🧹 Удалено {removed_count} выполненных уведомлений")

        return removed_count

    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику по уведомлениям.

        Returns:
            Dict: Статистика
        """
        total_alerts = self.get_total_alerts_count()
        total_users = len(self.user_alerts)

        # Статистика по направлениям
        up_count = 0
        down_count = 0

        for alerts in self.user_alerts.values():
            for alert in alerts:
                if alert.get('direction') == ALERT_DIRECTION_UP:
                    up_count += 1
                elif alert.get('direction') == ALERT_DIRECTION_DOWN:
                    down_count += 1

        avg_per_user = total_alerts / total_users if total_users > 0 else 0

        return {
            'total_alerts': total_alerts,
            'total_users': total_users,
            'up_alerts': up_count,
            'down_alerts': down_count,
            'avg_alerts_per_user': round(avg_per_user, 2)
        }