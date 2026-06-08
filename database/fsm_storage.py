import json
from typing import Any, Dict, Optional
from datetime import datetime
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.state import State

from database.db import db
from database.repositories import FSMStorageRepository
from logger import get_logger

logger = get_logger('fsm_storage')


class FSMStorage(BaseStorage):
    """
    Хранилище FSM состояний в PostgreSQL с привязкой к пользователю
    """

    def __init__(self):
        self._closed = False

    async def set_state(self, key: StorageKey, state: Optional[State] = None) -> None:
        """Установка состояния с привязкой к пользователю"""
        if self._closed:
            raise RuntimeError("Storage is closed")

        state_value = state.state if state is not None else None

        try:
            # Получаем текущие данные, чтобы не потерять их
            current = await FSMStorageRepository.get_state(self._key_to_str(key))
            current_data = current.get('data') if current else None

            await FSMStorageRepository.save_state(
                key=self._key_to_str(key),
                user_id=key.user_id,
                state=state_value,
                data=current_data
            )
            logger.debug(f"FSM: set_state key={key} state={state_value}")

        except Exception as e:
            logger.error(f"Ошибка при set_state: {e}")
            raise

    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Получение состояния"""
        if self._closed:
            raise RuntimeError("Storage is closed")

        try:
            result = await FSMStorageRepository.get_state(self._key_to_str(key))
            state_value = result['state'] if result else None
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
            # Получаем текущее состояние, чтобы не потерять его
            current = await FSMStorageRepository.get_state(self._key_to_str(key))
            current_state = current['state'] if current else None

            await FSMStorageRepository.save_state(
                key=self._key_to_str(key),
                user_id=key.user_id,
                state=current_state,
                data=data
            )
            logger.debug(f"FSM: set_data key={key} data={data}")

        except Exception as e:
            logger.error(f"Ошибка при set_data: {e}")
            raise

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        """Получение данных состояния"""
        if self._closed:
            raise RuntimeError("Storage is closed")

        try:
            result = await FSMStorageRepository.get_state(self._key_to_str(key))
            if result and 'data' in result:
                return result['data']
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
        return await FSMStorageRepository.cleanup_old_states(max_age_hours)

    async def get_user_states(self, user_id: int) -> list:
        """Получение всех состояний пользователя"""
        return await FSMStorageRepository.get_user_states(user_id)

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