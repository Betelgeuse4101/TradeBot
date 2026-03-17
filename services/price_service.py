from typing import Dict, List, Optional, Set, Any
from decimal import Decimal
import asyncio
from datetime import datetime, timedelta

from moex_client import moex_client
from database.repositories import PriceHistoryRepository, AssetRepository
from logger import get_logger
from utils import to_decimal, format_money

logger = get_logger('price_service')


class PriceService:
    """Сервис для получения и кэширования цен с MOEX"""

    def __init__(self):
        self.price_cache = {}  # symbol -> (price, timestamp)
        self.info_cache = {}  # symbol -> (info, timestamp)
        self.cache_ttl = 300  # 5 минут для MOEX
        self._closed = False

    async def get_price(self, symbol: str, use_cache: bool = True) -> Optional[Decimal]:
        """Получение цены символа с MOEX"""
        if self._closed:
            logger.warning("⚠️ Сервис цен закрыт, возвращаем кэшированные данные")
            # Пробуем взять из истории БД
            cached = await PriceHistoryRepository.get_price(symbol)
            if cached:
                return cached['price']
            return None

        cache_key = symbol.upper()

        # Проверка кэша
        if use_cache and cache_key in self.price_cache:
            price, timestamp = self.price_cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                logger.debug(f"Цена {symbol} из кэша: {price}")
                return price

        try:
            # Запрашиваем с MOEX
            price = await moex_client.get_current_price(symbol)

            if price and price > 0:
                # Сохраняем в кэш
                self.price_cache[cache_key] = (price, datetime.now())

                # Сохраняем в историю БД
                await PriceHistoryRepository.update_price(symbol, price)

                logger.info(f"✅ Получена цена {symbol}: {price}")
                return price
            else:
                logger.warning(f"⚠️ Не удалось получить цену {symbol}")

        except Exception as e:
            logger.error(f"Ошибка получения цены {symbol}: {e}")

        # Пробуем взять из истории БД
        cached = await PriceHistoryRepository.get_price(symbol)
        if cached:
            logger.info(f"📦 Цена {symbol} из истории БД: {cached['price']}")
            return cached['price']

        return None

    async def get_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """Получение цен нескольких символов"""
        if self._closed:
            logger.warning("⚠️ Сервис цен закрыт, возвращаем пустой результат")
            return {}

        result = {}
        tasks = []

        for symbol in symbols:
            tasks.append(self.get_price(symbol))

        prices = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, price in zip(symbols, prices):
            if isinstance(price, Decimal) and price > 0:
                result[symbol] = price

        logger.info(f"📊 Получено цен: {len(result)} из {len(symbols)}")
        return result

    async def get_asset_info(self, symbol: str) -> Optional[Dict]:
        """Получение информации об активе"""
        if self._closed:
            return None

        cache_key = f"info_{symbol.upper()}"

        # Проверка кэша
        if cache_key in self.info_cache:
            info, timestamp = self.info_cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl * 2):
                return info

        try:
            info = await moex_client.get_security_info(symbol)
            if info:
                self.info_cache[cache_key] = (info, datetime.now())
                return info
        except Exception as e:
            logger.error(f"Ошибка получения информации {symbol}: {e}")

        return None

    async def search_assets(self, query: str, limit: int = 10) -> List[Dict]:
        """Поиск активов на MOEX"""
        if self._closed:
            return []

        try:
            results = await moex_client.search_securities(query, limit)
            return results
        except Exception as e:
            logger.error(f"Ошибка поиска '{query}': {e}")
            return []

    async def update_portfolio_prices(self, portfolio_id: int):
        """Обновление цен всех активов портфеля"""
        if self._closed:
            logger.warning(f"⚠️ Сервис цен закрыт, пропускаем обновление портфеля {portfolio_id}")
            return 0

        from database.repositories import AssetRepository

        assets = await AssetRepository.get_portfolio_assets(portfolio_id)
        if not assets:
            logger.info(f"📭 Нет активов в портфеле {portfolio_id}")
            return 0

        symbols = [a['symbol'] for a in assets]
        logger.info(f"🔄 Обновление цен для портфеля {portfolio_id}: {symbols}")

        prices = await self.get_prices(symbols)

        updated_count = 0
        for asset in assets:
            if asset['symbol'] in prices:
                await AssetRepository.update_price(asset['id'], prices[asset['symbol']])
                updated_count += 1

        logger.info(f"✅ Обновлены цены для портфеля {portfolio_id}: {updated_count}/{len(assets)} активов")
        return updated_count

    async def calculate_portfolio_value(self, portfolio_id: int, assets: List[Dict] = None) -> Dict:
        """Расчет стоимости портфеля"""
        if assets is None:
            from database.repositories import AssetRepository
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

    async def get_market_status(self, symbol: str = None) -> Dict[str, Any]:
        """Получение статуса рынка для инструмента"""
        if self._closed:
            return {'market': 'closed'}

        if symbol:
            return await moex_client.get_market_trading_status(symbol)
        else:
            # Общий статус рынка (по индексу IMOEX)
            imoex_info = await self.get_asset_info('IMOEX')
            if imoex_info:
                return {
                    'market': 'IMOEX',
                    'last_price': imoex_info.get('market_data', {}).get('LAST'),
                    'change': imoex_info.get('market_data', {}).get('LASTCHANGE'),
                    'change_percent': imoex_info.get('market_data', {}).get('LASTCHANGEPRCNT')
                }
            return {'market': 'unknown'}

    async def validate_symbol(self, symbol: str) -> bool:
        """Проверка существования символа на MOEX"""
        if self._closed:
            return False

        # Сначала пробуем получить информацию об инструменте
        info = await self.get_asset_info(symbol)
        if info and info.get('name'):
            return True

        # Если не получили информацию, пробуем получить цену
        price = await self.get_price(symbol, use_cache=False)
        return price is not None and price > 0

    async def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """Получение списка самых растущих акций"""
        return []

    async def get_top_losers(self, limit: int = 10) -> List[Dict]:
        """Получение списка самых падающих акций"""
        return []

    def clear_cache(self):
        """Очистка кэша"""
        self.price_cache.clear()
        self.info_cache.clear()
        logger.info("🧹 Кэш цен очищен")

    async def close(self):
        """Закрытие соединений"""
        if self._closed:
            return

        logger.info("🔄 Закрытие сервиса цен...")
        self._closed = True
        self.clear_cache()

        try:
            # Даем время на завершение текущих запросов
            await asyncio.sleep(1)
            await moex_client.close()
        except Exception as e:
            logger.error(f"Ошибка при закрытии сервиса цен: {e}")
        finally:
            logger.info("✅ Сервис цен закрыт")


# Глобальный экземпляр
price_service = PriceService()