from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import asyncio
from collections import defaultdict
from datetime import datetime

from moex_client import moex_client
from database.repositories import PriceHistoryRepository, AssetRepository
from logger import get_logger
from config import Config

logger = get_logger('price_service')


class PriceService:
    """Сервис для фонового обновления и отдачи цен из кэша (БД)"""

    def __init__(self):
        self._closed = False
        self.update_interval = Config.PRICE_UPDATE_INTERVAL

    def _is_market_open(self) -> bool:
        """Проверяет, открыта ли биржа в данный момент"""
        now = datetime.now()
        if now.weekday() >= 5:  # Сб, Вс
            return False

        current_hour = now.hour
        current_minute = now.minute

        if current_hour < Config.MOEX_TRADING_START_HOUR:
            return False
        if current_hour > Config.MOEX_TRADING_END_HOUR:
            return False
        if (current_hour == Config.MOEX_TRADING_END_HOUR and
                current_minute > Config.MOEX_TRADING_END_MINUTE):
            return False

        return True

    async def start_updater(self):
        """Фоновый воркер для обновления цен раз в 4 часа"""
        logger.info("🚀 Запуск фонового обновления цен (интервал: 4 часа)")
        while not self._closed:
            try:
                await self._update_all_prices()
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле обновления цен: {e}", exc_info=True)

            for _ in range(self.update_interval):
                if self._closed:
                    break
                await asyncio.sleep(1)

    async def _update_all_prices(self):
        """Глобальное обновление цен всех отслеживаемых активов"""
        if not self._is_market_open():
            logger.info("😴 Рынок закрыт. Пропуск планового обновления цен.")
            return

        logger.info("🔄 Начало планового обновления цен с MOEX...")

        # 1. Получаем уникальные символы, а не все активы
        all_assets = await AssetRepository.get_all_assets()
        if not all_assets:
            logger.info("📭 В базе нет активов для обновления.")
            return

        # Группируем по символу для массового обновления БД позже
        symbols_to_assets = defaultdict(list)
        for asset in all_assets:
            symbols_to_assets[asset['symbol']].append(asset)

        unique_symbols = list(symbols_to_assets.keys())
        logger.info(f"📊 Найдено {len(unique_symbols)} уникальных символов для обновления.")

        # 2. Используем семафор для ограничения количества одновременных запросов к MOEX
        semaphore = asyncio.Semaphore(5)  # Максимум 5 одновременных запросов

        async def update_single_symbol(symbol: str):
            async with semaphore:
                try:
                    # Принудительно обновляем, минуя кэш, чтобы получить свежие данные
                    price = await self.get_price(symbol, use_cache=False)
                    if price and price > 0:
                        # Сохраняем цену в кэш
                        await PriceHistoryRepository.update_price(symbol, price)
                        logger.info(f"💾 Цена обновлена в кэше: {symbol} = {price}")
                        return symbol, price
                    else:
                        logger.warning(f"⚠️ Не удалось получить цену для {symbol}")
                        return symbol, None
                except Exception as e:
                    logger.error(f"❌ Ошибка получения цены для {symbol}: {e}")
                    return symbol, None

        # 3. Запускаем задачи на обновление конкурентно
        tasks = [update_single_symbol(s) for s in unique_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. Пакетно обновляем цены в таблице `assets`
        updated_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"❌ Ошибка в фоновой задаче: {result}")
                continue

            symbol, price = result
            if price:
                # Обновляем все активы с этим символом во всех портфелях
                for asset in symbols_to_assets[symbol]:
                    try:
                        await AssetRepository.update_price(asset['id'], price)
                        updated_count += 1
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления цены для актива {asset['id']}: {e}")

        logger.info(f"✅ Плановое обновление завершено. Обновлено {updated_count} записей в портфелях.")

    async def get_price(self, symbol: str, use_cache: bool = True,
                        asset_type_hint: str = None) -> Optional[Decimal]:
        """Получение цены СТРОГО ИЗ КЭША (БД). MOEX используется только при первичном поиске."""

        if use_cache:
            cached = await PriceHistoryRepository.get_price(symbol)
            if cached and cached.get('price'):
                return cached['price']

        try:
            price = await moex_client.get_current_price(symbol, asset_type_hint)
            if price and price > 0:
                await PriceHistoryRepository.update_price(symbol, price)
                return price
        except Exception as e:
            logger.error(f"Ошибка разового получения цены {symbol}: {e}")

        cached = await PriceHistoryRepository.get_price(symbol)
        if cached:
            return cached['price']

        return None

    async def validate_symbol_with_info(self, symbol: str, asset_type_hint: str = None) -> Tuple[bool, Optional[Dict]]:
        """Проверка существования символа и получение информации"""
        is_valid, info = await moex_client.validate_symbol(symbol, asset_type_hint)

        if info:
            type_names = {
                'stock': 'Акция', 'bond': 'Облигация', 'etf': 'ETF',
                'currency': 'Валюта', 'futures': 'Фьючерс', 'index': 'Индекс'
            }
            info['asset_type_display'] = type_names.get(info.get('asset_type', 'stock'), 'Акция')

        return is_valid, info

    async def close(self):
        """Закрытие соединений"""
        if self._closed:
            return

        logger.info("🔄 Остановка сервиса цен...")
        self._closed = True
        await moex_client.close()
        logger.info("✅ Сервис цен остановлен")


price_service = PriceService()