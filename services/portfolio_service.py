from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime, timedelta

from database.repositories import PortfolioRepository, AssetRepository
from services.price_service import price_service
from logger import get_logger
from utils import to_decimal, format_money, format_percent

logger = get_logger('portfolio_service')


class PortfolioService:
    """Сервис для работы с портфелями и расчета статистики"""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 60

    async def calculate_portfolio_summary(self, portfolio_id: int,
                                          force_update: bool = False) -> Dict[str, Any]:
        """
        Полный расчет портфеля со всей статистикой
        """
        cache_key = f"portfolio_{portfolio_id}"

        # Проверка кэша
        if not force_update and cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return data

        portfolio = await PortfolioRepository.get(portfolio_id)
        if not portfolio:
            return {}

        assets = await AssetRepository.get_portfolio_assets(portfolio_id)

        if not assets:
            result = {
                'portfolio': portfolio,
                'total_value': Decimal('0'),
                'total_cost': Decimal('0'),
                'total_profit': Decimal('0'),
                'total_profit_percent': Decimal('0'),
                'assets_count': 0,
                'assets': [],
                'type_allocation': {},
                'currency_allocation': {},
                'updated_at': datetime.now().isoformat()
            }
            return result

        # Обновляем цены если нужно
        if force_update or self._need_price_update(assets):
            await price_service.update_portfolio_prices(portfolio_id)
            assets = await AssetRepository.get_portfolio_assets(portfolio_id)

        # Расчеты
        total_value = Decimal('0')
        total_cost = Decimal('0')
        assets_data = []
        type_allocation = {}
        currency_allocation = {}

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

            asset_data = {
                **asset,
                'current_value': current_value,
                'cost': cost,
                'profit': profit,
                'profit_percent': profit_percent,
                'weight': Decimal('0'),
            }
            assets_data.append(asset_data)

            # Статистика по типам
            asset_type = asset['asset_type']
            type_allocation[asset_type] = type_allocation.get(asset_type, Decimal('0')) + current_value

            # Статистика по валютам
            currency = asset['currency']
            currency_allocation[currency] = currency_allocation.get(currency, Decimal('0')) + current_value

        total_profit = total_value - total_cost
        total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else Decimal('0')

        # Расчет весов
        if total_value > 0:
            for asset in assets_data:
                asset['weight'] = (asset['current_value'] / total_value * 100)

        # Сортировка по весу
        assets_data.sort(key=lambda x: x['weight'], reverse=True)

        # Конвертация в проценты
        type_allocation_pct = self._calculate_percentages(type_allocation, total_value)
        currency_allocation_pct = self._calculate_percentages(currency_allocation, total_value)

        result = {
            'portfolio': portfolio,
            'total_value': total_value,
            'total_cost': total_cost,
            'total_profit': total_profit,
            'total_profit_percent': total_profit_percent,
            'assets_count': len(assets),
            'assets': assets_data,
            'type_allocation': type_allocation_pct,
            'currency_allocation': currency_allocation_pct,
            'updated_at': datetime.now().isoformat()
        }

        self.cache[cache_key] = (result, datetime.now())
        await PortfolioRepository.update_value(portfolio_id, total_value)

        return result

    async def calculate_asset_details(self, asset_id: int, update_price: bool = True) -> Dict[str, Any]:
        """Детальный расчет по активу"""
        asset = await AssetRepository.get(asset_id)
        if not asset:
            return {}

        if update_price:
            current_price = await price_service.get_price(asset['symbol'], asset_type_hint=asset['asset_type'])
            if current_price:
                await AssetRepository.update_price(asset_id, current_price)
                asset['current_price'] = current_price

        quantity = asset['quantity']
        purchase_price = asset['purchase_price']
        current_price = asset['current_price'] or purchase_price

        current_value = quantity * current_price
        cost = quantity * purchase_price
        profit = current_value - cost
        profit_percent = (profit / cost * 100) if cost > 0 else Decimal('0')

        return {
            **asset,
            'current_value': current_value,
            'cost': cost,
            'profit': profit,
            'profit_percent': profit_percent,
        }

    def _need_price_update(self, assets: List[Dict]) -> bool:
        """Проверка необходимости обновления цен"""
        for asset in assets:
            if asset['current_price'] is None:
                return True
            if asset['updated_at']:
                age = datetime.now() - asset['updated_at']
                if age.total_seconds() > 7200:  # 2 часа
                    return True
        return False

    def _calculate_percentages(self, allocation: Dict[str, Decimal],
                               total: Decimal) -> Dict[str, float]:
        """Конвертация абсолютных значений в проценты"""
        if total <= 0:
            return {}

        result = {}
        for key, value in allocation.items():
            result[key] = float((value / total * 100))

        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

    def clear_cache(self):
        """Очистка кэша"""
        self.cache.clear()
        logger.info("🧹 Кэш портфелей очищен")


# Глобальный экземпляр
portfolio_service = PortfolioService()