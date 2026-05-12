from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
import asyncio
import pytz
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
        msk_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(msk_tz)

        if now.weekday() >= 5:
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

    def get_msk_time(self) -> datetime:
        """Возвращает текущее время по Москве"""
        return datetime.now(pytz.timezone('Europe/Moscow'))

    async def start_updater(self):
        """Фоновый воркер для обновления цен"""
        logger.info("🚀 Запуск фонового обновления цен (интервал: 4 часа)")

        await self.update_prices_on_startup()

        while not self._closed:
            try:
                for _ in range(self.update_interval):
                    if self._closed:
                        break
                    await asyncio.sleep(1)

                await self._update_all_prices()

            except Exception as e:
                logger.error(f"❌ Ошибка в цикле обновления цен: {e}", exc_info=True)

    async def _update_all_prices(self):
        """Глобальное обновление цен всех отслеживаемых активов"""
        if not self._is_market_open():
            logger.info("😴 Рынок закрыт. Пропуск планового обновления цен.")
            return

        logger.info("🔄 Начало планового обновления цен с MOEX...")

        all_assets = await AssetRepository.get_all_assets()
        if not all_assets:
            logger.info("📭 В базе нет активов для обновления.")
            return

        symbols_to_assets = defaultdict(list)
        for asset in all_assets:
            symbols_to_assets[asset['symbol']].append(asset)

        unique_symbols = list(symbols_to_assets.keys())
        logger.info(f"📊 Найдено {len(unique_symbols)} уникальных символов для обновления.")

        async def update_single_symbol(symbol: str):
            try:
                price = await self.get_price(symbol, use_cache=False)
                if price and price > 0:
                    await PriceHistoryRepository.update_price(symbol, price)
                    return symbol, price
                return symbol, None
            except Exception as e:
                logger.error(f"❌ Ошибка получения цены для {symbol}: {e}")
                return symbol, None

        tasks = [update_single_symbol(s) for s in unique_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        updated_count = 0
        for result in results:
            if isinstance(result, Exception):
                continue
            symbol, price = result
            if price:
                for asset in symbols_to_assets[symbol]:
                    try:
                        await AssetRepository.update_price(asset['id'], price)
                        updated_count += 1
                    except Exception as e:
                        logger.error(f"❌ Ошибка обновления цены для актива {asset['id']}: {e}")

        logger.info(f"✅ Плановое обновление завершено. Обновлено {updated_count} записей в портфелях.")

    async def update_portfolio_prices(self, portfolio_id: int) -> None:
        """
        Обновляет цены всех активов в портфеле из кэша или MOEX.
        Используется при создании уведомлений для получения актуальных цен.

        Args:
            portfolio_id: ID портфеля
        """
        try:
            assets = await AssetRepository.get_portfolio_assets(portfolio_id)
            if not assets:
                return

            logger.info(f"🔄 Обновление цен для портфеля {portfolio_id} ({len(assets)} активов)")

            for asset in assets:
                symbol = asset['symbol']
                # Пробуем получить цену (сначала из кэша, потом из MOEX)
                price = await self.get_price(symbol)
                if price and price > 0:
                    await AssetRepository.update_price(asset['id'], price)
                    logger.debug(f"✅ Цена {symbol}: {price}")
                else:
                    logger.debug(f"⚠️ Не удалось обновить цену для {symbol}")

        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении цен портфеля {portfolio_id}: {e}")

    async def calculate_portfolio_value(self, portfolio_id: int, assets: List[Dict] = None) -> Dict[str, Any]:
        """
        Рассчитывает текущую стоимость портфеля на основе цен активов.

        Args:
            portfolio_id: ID портфеля
            assets: Список активов (если уже загружены)

        Returns:
            Dict с ключами: total_value, total_cost, total_profit, assets_count
        """
        try:
            if assets is None:
                assets = await AssetRepository.get_portfolio_assets(portfolio_id)

            total_value = Decimal('0')
            total_cost = Decimal('0')

            for asset in assets:
                quantity = asset['quantity']
                purchase_price = asset['purchase_price']
                current_price = asset['current_price'] or purchase_price

                total_value += quantity * current_price
                total_cost += quantity * purchase_price

            total_profit = total_value - total_cost

            return {
                'total_value': total_value,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'assets_count': len(assets) if assets else 0
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при расчете стоимости портфеля {portfolio_id}: {e}")
            return {
                'total_value': Decimal('0'),
                'total_cost': Decimal('0'),
                'total_profit': Decimal('0'),
                'assets_count': 0
            }

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

    async def update_prices_on_startup(self):
        """Обновление цен при запуске бота (всегда, независимо от рынка)"""
        logger.info("🔄 Запуск обновления цен при старте бота...")

        try:
            all_assets = await AssetRepository.get_all_assets()
            if not all_assets:
                logger.info("📭 В базе нет активов для обновления.")
                return

            symbols_to_assets = defaultdict(list)
            for asset in all_assets:
                symbols_to_assets[asset['symbol']].append(asset)

            unique_symbols = list(symbols_to_assets.keys())
            logger.info(f"📊 Найдено {len(unique_symbols)} уникальных символов для обновления.")

            semaphore = asyncio.Semaphore(5)

            async def update_single_symbol(symbol: str):
                async with semaphore:
                    try:
                        price = await self.get_price(symbol, use_cache=False)
                        if price and price > 0:
                            await PriceHistoryRepository.update_price(symbol, price)
                            return symbol, price
                        return symbol, None
                    except Exception as e:
                        logger.error(f"❌ Ошибка получения цены для {symbol}: {e}")
                        return symbol, None

            tasks = [update_single_symbol(s) for s in unique_symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            updated_count = 0
            for result in results:
                if isinstance(result, Exception):
                    continue

                symbol, price = result
                if price:
                    for asset in symbols_to_assets[symbol]:
                        try:
                            await AssetRepository.update_price(asset['id'], price)
                            updated_count += 1
                        except Exception as e:
                            logger.error(f"❌ Ошибка обновления цены для актива {asset['id']}: {e}")

            logger.info(f"✅ Стартовое обновление завершено. Обновлено {updated_count} записей.")

        except Exception as e:
            logger.error(f"❌ Ошибка при стартовом обновлении цен: {e}")


price_service = PriceService()