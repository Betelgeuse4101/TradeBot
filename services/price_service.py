from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
import asyncio
import pytz
from collections import defaultdict
from datetime import datetime, timedelta
from moex_client import moex_client
from database.repositories import PriceHistoryRepository, AssetRepository
from logger import get_logger
from config import Config

logger = get_logger('price_service')


class PriceService:
    """Сервис для фонового обновления и отдачи цен из кэша"""

    def __init__(self):
        self._closed = False
        self.update_interval = Config.PRICE_UPDATE_INTERVAL
        self.last_update_time = {}
        self._update_lock = asyncio.Lock()
        self._last_market_close_update = None  # Время последнего обновления после закрытия

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

    def _was_market_closed_recently(self) -> bool:
        """Проверяет, не закрылся ли рынок недавно"""
        if self._is_market_open():
            return False

        msk_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(msk_tz)

        # Расчет времени закрытия на сегодня
        close_time = now.replace(
            hour=Config.MOEX_TRADING_END_HOUR,
            minute=Config.MOEX_TRADING_END_MINUTE,
            second=0,
            microsecond=0
        )

        # Если сейчас время после закрытия
        if now > close_time:
            time_since_close = (now - close_time).total_seconds() / 60
            return time_since_close < 30  # В течение 30 минут после закрытия

        return False

    def get_last_update_time(self, symbol: str) -> Optional[datetime]:
        """Получает время последнего обновления цены для символа (всегда в московском времени)"""
        last_update = self.last_update_time.get(symbol)
        if last_update and last_update.tzinfo is None:
            msk_tz = pytz.timezone('Europe/Moscow')
            last_update = msk_tz.localize(last_update)
        return last_update

    def is_price_fresh(self, symbol: str, max_age_minutes: int = 15) -> bool:
        """
        Проверяет, является ли цена свежей.
        Если рынок открыт - цена должна быть не старше max_age_minutes.
        Если рынок закрыт - цена считается свежей если это цена закрытия (обновлена после закрытия)
        """
        last_update = self.last_update_time.get(symbol)
        if not last_update:
            return False

        if last_update.tzinfo is None:
            msk_tz = pytz.timezone('Europe/Moscow')
            last_update = msk_tz.localize(last_update)

        if not self._is_market_open():
            msk_tz = pytz.timezone('Europe/Moscow')
            now = datetime.now(msk_tz)
            close_time = now.replace(
                hour=Config.MOEX_TRADING_END_HOUR,
                minute=Config.MOEX_TRADING_END_MINUTE,
                second=0,
                microsecond=0
            )

            if now > close_time:
                return last_update > close_time

            yesterday_close = close_time - timedelta(days=1)
            return last_update > yesterday_close

        now = datetime.now(pytz.timezone('Europe/Moscow'))
        age_minutes = (now - last_update).total_seconds() / 60
        return age_minutes < max_age_minutes

    def get_msk_time(self) -> datetime:
        """Возвращает текущее время по Москве"""
        return datetime.now(pytz.timezone('Europe/Moscow'))

    async def start_updater(self):
        """Фоновый воркер для обновления цен"""
        logger.info("🚀 Запуск фонового обновления цен")

        while not self._closed:
            try:
                if self._was_market_closed_recently():
                    if self._last_market_close_update is None or \
                            (datetime.now() - self._last_market_close_update).total_seconds() > 3600:
                        logger.info("📊 Рынок только что закрылся, обновляем финальные цены...")
                        await self._update_all_prices(after_close=True)
                        self._last_market_close_update = datetime.now()

                elif self._is_market_open():
                    last_update = self._last_market_close_update or datetime.now() - timedelta(hours=5)
                    hours_since_update = (datetime.now() - last_update).total_seconds() / 3600

                    if hours_since_update >= 4:
                        logger.info("🔄 Плановое обновление цен во время торгов...")
                        await self._update_all_prices(after_close=False)

                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"❌ Ошибка в цикле обновления цен: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _update_all_prices(self, after_close: bool = False):
        """Глобальное обновление цен всех отслеживаемых активов"""

        async with self._update_lock:
            if after_close:
                logger.info("📊 ОБНОВЛЕНИЕ ЦЕН ПОСЛЕ ЗАКРЫТИЯ РЫНКА")
            elif not self._is_market_open():
                logger.debug("Рынок закрыт, пропускаем обновление")
                return

            logger.info("🔄 Начало обновления цен...")

            all_assets = await AssetRepository.get_all_assets()
            if not all_assets:
                logger.info("📭 В базе нет активов для обновления.")
                return

            symbols_to_assets = defaultdict(list)
            for asset in all_assets:
                symbols_to_assets[asset['symbol']].append(asset)

            unique_symbols = list(symbols_to_assets.keys())
            logger.info(f"📊 Найдено {len(unique_symbols)} уникальных символов для {len(all_assets)} активов")

            semaphore = asyncio.Semaphore(10)

            async def update_single_symbol(symbol: str):
                async with semaphore:
                    try:
                        price = await moex_client.get_current_price(symbol)
                        if price and price > 0:
                            await PriceHistoryRepository.update_price(symbol, price)
                            msk_tz = pytz.timezone('Europe/Moscow')
                            self.last_update_time[symbol] = datetime.now(msk_tz)
                            logger.debug(f"✅ {symbol}: {price}")
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

            logger.info(f"✅ Обновлено {updated_count} записей ({len(unique_symbols)} уникальных тикеров)")

            if after_close:
                logger.info("🎯 ФИНАЛЬНЫЕ ЦЕНЫ ЗАКРЫТИЯ УСТАНОВЛЕНЫ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ")

    async def update_portfolio_prices(self, portfolio_id: int) -> None:
        """
        Обновляет цены всех активов в портфеле.
        Используется при принудительном обновлении пользователем.
        """
        if not self._is_market_open():
            logger.debug("Рынок закрыт, принудительное обновление цен отключено")
            return

        try:
            assets = await AssetRepository.get_portfolio_assets(portfolio_id)
            if not assets:
                return

            logger.info(f"🔄 Принудительное обновление цен для портфеля {portfolio_id}")

            for asset in assets:
                symbol = asset['symbol']
                price = await self.get_price(symbol, use_cache=False)
                if price and price > 0:
                    await AssetRepository.update_price(asset['id'], price)
                    self.last_update_time[symbol] = datetime.now()
                    logger.debug(f"✅ Цена {symbol}: {price}")

        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении цен портфеля {portfolio_id}: {e}")

    async def calculate_portfolio_value(self, portfolio_id: int, assets: List[Dict] = None) -> Dict[str, Any]:
        """
        Рассчитывает текущую стоимость портфеля на основе цен активов.
        """
        try:
            if assets is None:
                assets = await AssetRepository.get_portfolio_assets(portfolio_id)

            total_value = Decimal('0')
            total_cost = Decimal('0')
            stale_data = False

            for asset in assets:
                quantity = asset['quantity']
                purchase_price = asset['purchase_price']
                current_price = asset['current_price'] or purchase_price

                # Проверяем свежесть цены
                is_fresh = self.is_price_fresh(asset['symbol'])
                if not is_fresh and current_price != purchase_price:
                    stale_data = True

                total_value += quantity * current_price
                total_cost += quantity * purchase_price

            total_profit = total_value - total_cost

            return {
                'total_value': total_value,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'assets_count': len(assets) if assets else 0,
                'is_market_open': self._is_market_open(),
                'stale_data': stale_data
            }

        except Exception as e:
            logger.error(f"❌ Ошибка при расчете стоимости портфеля {portfolio_id}: {e}")
            return {
                'total_value': Decimal('0'),
                'total_cost': Decimal('0'),
                'total_profit': Decimal('0'),
                'assets_count': 0,
                'is_market_open': self._is_market_open(),
                'stale_data': False
            }

    async def get_price(self, symbol: str, use_cache: bool = True,
                        force: bool = False, asset_type_hint: str = None) -> Optional[Decimal]:
        """
        Получение цены из кэша или MOEX.
        """
        if use_cache:
            cached = await PriceHistoryRepository.get_price(symbol)
            if cached and cached.get('price'):
                logger.debug(f"📦 Цена {symbol} из кэша: {cached['price']}")
                return cached['price']

        try:
            price = await moex_client.get_current_price(symbol, asset_type_hint)
            if price and price > 0:
                await PriceHistoryRepository.update_price(symbol, price)
                self.last_update_time[symbol] = datetime.now()
                logger.info(f"💰 Получена цена {symbol}: {price}")
                return price
            else:
                logger.warning(f"⚠️ MOEX вернул некорректную цену для {symbol}")
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены {symbol}: {e}")

        # Если не удалось получить новую цену, пробуем кэш ещё раз
        cached = await PriceHistoryRepository.get_price(symbol)
        if cached and cached.get('price'):
            logger.warning(f"⚠️ Использую устаревший кэш для {symbol}: {cached['price']}")
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