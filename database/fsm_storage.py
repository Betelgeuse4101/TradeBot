import json
from typing import Any, Dict, Optional
from datetime import datetime
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.state import State

from database.db import db
from logger import get_logger

logger = get_logger('fsm_storage')


class AsyncpgStorage(BaseStorage):
    """
    Хранилище FSM состояний в PostgreSQL
    """

    def __init__(self):
        self._closed = False

    async def set_state(self, key: StorageKey, state: Optional[State] = None) -> None:
        """Установка состояния"""
        if self._closed:
            raise RuntimeError("Storage is closed")

        state_value = state.state if state is not None else None

        try:
            await db.execute("""
                INSERT INTO fsm_states (key, state, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                    state = EXCLUDED.state,
                    updated_at = CURRENT_TIMESTAMP
            """, self._key_to_str(key), state_value)

            logger.debug(f"FSM: set_state key={key} state={state_value}")

        except Exception as e:
            logger.error(f"Ошибка при set_state: {e}")
            raise

    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Получение состояния"""
        if self._closed:
            raise RuntimeError("Storage is closed")

        try:
            row = await db.fetchrow("""
                SELECT state FROM fsm_states WHERE key = $1
            """, self._key_to_str(key))

            state_value = row['state'] if row else None
            logger.debug(f"FSM: get_state key={key} state={state_value}")
            return state_value

        except Exception as e:
            logger.error(f"Ошибка при get_state: {e}")
            return None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        """Установка данных состояния"""
        if self._closed:
            raise RuntimeError("Storage is closed")

        try:
            json_data = json.dumps(data, default=self._json_serializer)

            await db.execute("""
                INSERT INTO fsm_states (key, data, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                    data = EXCLUDED.data,
                    updated_at = CURRENT_TIMESTAMP
            """, self._key_to_str(key), json_data)

            logger.debug(f"FSM: set_data key={key} data={data}")

        except Exception as e:
            logger.error(f"Ошибка при set_data: {e}")
            raise

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        """Получение данных состояния"""
        if self._closed:
            raise RuntimeError("Storage is closed")

        try:
            row = await db.fetchrow("""
                SELECT data FROM fsm_states WHERE key = $1
            """, self._key_to_str(key))

            if row and row['data']:
                return json.loads(row['data'])
            return {}

        except Exception as e:
            logger.error(f"Ошибка при get_data: {e}")
            return {}

    async def close(self) -> None:
        """Закрытие хранилища"""
        if not self._closed:
            self._closed = True
            logger.info("FSM Storage закрыт")

    async def cleanup_old_states(self, max_age_hours: int = 24) -> int:
        """Очистка старых состояний"""
        try:
            result = await db.execute("""
                DELETE FROM fsm_states 
                WHERE updated_at < NOW() - INTERVAL '1 hour' * $1
            """, max_age_hours)

            deleted = int(result.split()[1]) if result.startswith('DELETE') else 0

            if deleted > 0:
                logger.info(f"Очищено {deleted} устаревших FSM состояний")

            return deleted

        except Exception as e:
            logger.error(f"Ошибка при очистке FSM состояний: {e}")
            return 0

    @staticmethod
    def _key_to_str(key: StorageKey) -> str:
        """Преобразование StorageKey в строку для БД"""
        parts = [
            str(key.bot_id),
            str(key.chat_id),
            str(key.user_id),
        ]
        if key.thread_id:
            parts.append(str(key.thread_id))

        return ":".join(parts)

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Сериализатор для JSON"""
        from decimal import Decimal

        if isinstance(obj, Decimal):
            return float(obj) if obj.is_finite() else str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")