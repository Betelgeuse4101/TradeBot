from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
import asyncio
from datetime import datetime, timedelta

from moex_client import moex_client
from database.repositories import PriceHistoryRepository, AssetRepository
from logger import get_logger
from utils import to_decimal
from config import Config

logger = get_logger('price_service')


class PriceService:
    """Сервис для получения и кэширования цен с MOEX"""

    def __init__(self):
        self.price_cache = {}
        self.cache_ttl = Config.PRICE_CACHE_TTL
        self._closed = False
        self._last_market_check = None
        self._market_was_open = False

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

    async def get_price(self, symbol: str, use_cache: bool = True,
                        asset_type_hint: str = None) -> Optional[Decimal]:
        """Получение цены символа с MOEX"""
        if self._closed:
            cached = await PriceHistoryRepository.get_price(symbol)
            return cached['price'] if cached else None

        cache_key = symbol.upper()

        # Проверка кэша
        if use_cache and cache_key in self.price_cache:
            price, timestamp = self.price_cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return price

        try:
            price = await moex_client.get_current_price(symbol, asset_type_hint)

            if price and price > 0:
                self.price_cache[cache_key] = (price, datetime.now())
                await PriceHistoryRepository.update_price(symbol, price)
                return price

        except Exception as e:
            logger.error(f"Ошибка получения цены {symbol}: {e}")

        # Пробуем из истории
        cached = await PriceHistoryRepository.get_price(symbol)
        if cached:
            return cached['price']

        return None

    async def validate_symbol_with_info(self, symbol: str, asset_type_hint: str = None) -> Tuple[bool, Optional[Dict]]:
        """Проверка существования символа и получение информации"""
        is_valid, info = await moex_client.validate_symbol(symbol, asset_type_hint)

        if info:
            type_names = {
                'stock': 'Акция',
                'bond': 'Облигация',
                'etf': 'ETF',
                'currency': 'Валюта',
                'futures': 'Фьючерс',
                'index': 'Индекс'
            }
            info['asset_type_display'] = type_names.get(info.get('asset_type', 'stock'), 'Акция')

        return is_valid, info

    async def get_prices(self, symbols: List[str], asset_types: Dict[str, str] = None) -> Dict[str, Decimal]:
        """Получение цен нескольких символов"""
        if self._closed:
            return {}

        return await moex_client.get_prices(symbols, asset_types)

    async def update_portfolio_prices(self, portfolio_id: int) -> int:
        """Обновление цен всех активов портфеля"""
        if self._closed:
            return 0

        if not self._is_market_open():
            logger.debug(f"Рынок закрыт, пропускаем обновление портфеля {portfolio_id}")
            return 0

        assets = await AssetRepository.get_portfolio_assets(portfolio_id)
        if not assets:
            return 0

        # Собираем символы и их типы
        symbols = []
        asset_types = {}
        for a in assets:
            symbols.append(a['symbol'])
            asset_types[a['symbol']] = a['asset_type']

        logger.info(f"🔄 Обновление цен для портфеля {portfolio_id}: {len(symbols)} активов")

        prices = await self.get_prices(symbols, asset_types)

        updated_count = 0
        for asset in assets:
            if asset['symbol'] in prices:
                await AssetRepository.update_price(asset['id'], prices[asset['symbol']])
                updated_count += 1

        logger.info(f"✅ Обновлены цены для портфеля {portfolio_id}: {updated_count}/{len(assets)}")
        return updated_count

    async def calculate_portfolio_value(self, portfolio_id: int, assets: List[Dict] = None) -> Dict:
        """Расчет стоимости портфеля"""
        if assets is None:
            assets = await AssetRepository.get_portfolio_assets(portfolio_id)

        total_value = Decimal('0')
        total_cost = Decimal('0')
        assets_data = []

        for asset in assets:
            quantity = asset['quantity']
            purchase_price = asset['purchase_price']
            current_price = asset['current_price'] or purchase_price

            current_value = quantity * current_price
            cost = quantity * purchase_price

            total_value += current_value
            total_cost += cost

            profit = current_value - cost
            profit_percent = (profit / cost * 100) if cost > 0 else Decimal('0')

            assets_data.append({
                **asset,
                'current_value': current_value,
                'cost': cost,
                'profit': profit,
                'profit_percent': profit_percent
            })

        total_profit = total_value - total_cost
        total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else Decimal('0')

        return {
            'total_value': total_value,
            'total_cost': total_cost,
            'total_profit': total_profit,
            'total_profit_percent': total_profit_percent,
            'assets': assets_data,
            'assets_count': len(assets)
        }

    async def search_assets(self, query: str, limit: int = 10) -> List[Dict]:
        """Поиск активов на MOEX"""
        if self._closed:
            return []
        return await moex_client.search_securities(query, limit)

    async def get_market_structure(self) -> Dict:
        """Получение структуры рынков"""
        return await moex_client.get_market_structure()

    async def close(self):
        """Закрытие соединений"""
        if self._closed:
            return

        logger.info("🔄 Закрытие сервиса цен...")
        self._closed = True
        self.price_cache.clear()
        await moex_client.close()
        logger.info("✅ Сервис цен закрыт")


# Глобальный экземпляр
price_service = PriceService()