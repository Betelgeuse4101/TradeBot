from typing import Dict, Any
from decimal import Decimal
from datetime import datetime
from config import Config
from database.repositories import PortfolioRepository, AssetRepository
from logger import get_logger
from utils import format_money, format_percent

logger = get_logger('portfolio_service')


class PortfolioService:
    """Сервис для расчета статистики портфеля на основе БД (без внешних запросов)"""

    async def calculate_portfolio_summary(self, portfolio_id: int) -> Dict[str, Any]:
        """Мгновенный расчет портфеля со всей статистикой из локальной БД"""

        portfolio = await PortfolioRepository.get(portfolio_id)
        if not portfolio:
            return {}

        assets = await AssetRepository.get_portfolio_assets(portfolio_id)

        if not assets:
            return {
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

            asset_type = asset['asset_type']
            type_allocation[asset_type] = type_allocation.get(asset_type, Decimal('0')) + current_value

            currency = asset['currency']
            currency_allocation[currency] = currency_allocation.get(currency, Decimal('0')) + current_value

        total_profit = total_value - total_cost
        total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else Decimal('0')

        if total_value > 0:
            for asset in assets_data:
                asset['weight'] = (asset['current_value'] / total_value * 100)

        assets_data.sort(key=lambda x: x['weight'], reverse=True)

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

        await PortfolioRepository.update_value(portfolio_id, total_value)

        return result

    async def calculate_asset_details(self, asset_id: int) -> Dict[str, Any]:
        """Мгновенный расчет по активу"""
        asset = await AssetRepository.get(asset_id)
        if not asset:
            return {}

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

    def _calculate_percentages(self, allocation: Dict[str, Decimal], total: Decimal) -> Dict[str, float]:
        """Конвертация абсолютных значений в проценты"""
        if total <= 0:
            return {}
        result = {}
        for key, value in allocation.items():
            result[key] = float((value / total * 100))
        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))


portfolio_service = PortfolioService()