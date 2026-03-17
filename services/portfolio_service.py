from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from datetime import datetime, timedelta
import asyncio
import math

from database.repositories import PortfolioRepository, AssetRepository, PriceHistoryRepository
from services.price_service import price_service
from logger import get_logger
from utils import to_decimal, format_money, format_percent

logger = get_logger('portfolio_service')


class PortfolioService:
    """Сервис для работы с портфелями и расчета статистики"""

    def __init__(self):
        self.cache = {}  # Кэш для расчетов портфелей
        self.cache_ttl = 60  # секунд

    async def calculate_portfolio_summary(self, portfolio_id: int,
                                          force_update: bool = False) -> Dict[str, Any]:
        """
        Полный расчет портфеля со всей статистикой

        Args:
            portfolio_id: ID портфеля
            force_update: Принудительное обновление цен

        Returns:
            Dict с полной статистикой портфеля
        """
        cache_key = f"portfolio_{portfolio_id}"

        # Проверка кэша
        if not force_update and cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return data

        # Получаем портфель
        portfolio = await PortfolioRepository.get(portfolio_id)
        if not portfolio:
            logger.warning(f"⚠️ Портфель {portfolio_id} не найден")
            return {}

        # Получаем активы
        assets = await AssetRepository.get_portfolio_assets(portfolio_id)

        # Если нет активов
        if not assets:
            result = {
                'portfolio': portfolio,
                'total_value': Decimal('0'),
                'total_cost': Decimal('0'),
                'total_profit': Decimal('0'),
                'total_profit_percent': Decimal('0'),
                'assets_count': 0,
                'assets': [],
                'sector_allocation': {},
                'type_allocation': {},
                'currency_allocation': {},
                'updated_at': datetime.now().isoformat()
            }
            return result

        # Обновляем цены если нужно
        if force_update or self._need_price_update(assets):
            await price_service.update_portfolio_prices(portfolio_id)
            # Обновляем данные активов
            assets = await AssetRepository.get_portfolio_assets(portfolio_id)

        # Расчеты по портфелю
        total_value = Decimal('0')
        total_cost = Decimal('0')
        total_profit = Decimal('0')
        total_profit_percent = Decimal('0')

        assets_data = []
        sector_allocation = {}
        type_allocation = {}
        currency_allocation = {}

        for asset in assets:
            # Основные показатели
            quantity = asset['quantity']
            purchase_price = asset['purchase_price']
            current_price = asset['current_price'] or purchase_price

            current_value = quantity * current_price
            cost = quantity * purchase_price
            profit = current_value - cost
            profit_percent = (profit / cost * 100) if cost > 0 else Decimal('0')

            # Добавляем к общим суммам
            total_value += current_value
            total_cost += cost
            total_profit += profit

            # Данные по активу
            asset_data = {
                **asset,
                'current_value': current_value,
                'cost': cost,
                'profit': profit,
                'profit_percent': profit_percent,
                'weight': Decimal('0'),  # Вес в портфеле (будет рассчитан позже)
            }
            assets_data.append(asset_data)

            # Статистика по секторам
            sector = asset.get('sector', 'Другое')
            if sector not in sector_allocation:
                sector_allocation[sector] = Decimal('0')
            sector_allocation[sector] += current_value

            # Статистика по типам
            asset_type = asset['asset_type']
            if asset_type not in type_allocation:
                type_allocation[asset_type] = Decimal('0')
            type_allocation[asset_type] += current_value

            # Статистика по валютам
            currency = asset['currency']
            if currency not in currency_allocation:
                currency_allocation[currency] = Decimal('0')
            currency_allocation[currency] += current_value

        # Расчет общего процента прибыли
        if total_cost > 0:
            total_profit_percent = (total_profit / total_cost * 100)

        # Расчет весов активов
        if total_value > 0:
            for asset in assets_data:
                asset['weight'] = (asset['current_value'] / total_value * 100)

        # Сортировка активов по весу (от большего к меньшему)
        assets_data.sort(key=lambda x: x['weight'], reverse=True)

        # Конвертация аллокаций в проценты
        sector_allocation_pct = self._calculate_percentages(sector_allocation, total_value)
        type_allocation_pct = self._calculate_percentages(type_allocation, total_value)
        currency_allocation_pct = self._calculate_percentages(currency_allocation, total_value)

        # Итоговый результат
        result = {
            'portfolio': portfolio,
            'total_value': total_value,
            'total_cost': total_cost,
            'total_profit': total_profit,
            'total_profit_percent': total_profit_percent,
            'assets_count': len(assets),
            'assets': assets_data,
            'sector_allocation': sector_allocation_pct,
            'type_allocation': type_allocation_pct,
            'currency_allocation': currency_allocation_pct,
            'updated_at': datetime.now().isoformat()
        }

        # Сохраняем в кэш
        self.cache[cache_key] = (result, datetime.now())

        # Обновляем общую стоимость в БД
        await PortfolioRepository.update_value(portfolio_id, total_value)

        logger.info(f"📊 Рассчитан портфель {portfolio_id}: {format_money(total_value)}, {len(assets)} активов")
        return result

    async def calculate_asset_details(self, asset_id: int, update_price: bool = True) -> Dict[str, Any]:
        """
        Детальный расчет по активу

        Args:
            asset_id: ID актива
            update_price: Обновлять ли цену

        Returns:
            Dict с детальной статистикой актива
        """
        asset = await AssetRepository.get(asset_id)
        if not asset:
            logger.warning(f"⚠️ Актив {asset_id} не найден")
            return {}

        # Обновляем цену
        if update_price:
            current_price = await price_service.get_price(asset['symbol'])
            if current_price:
                await AssetRepository.update_price(asset_id, current_price)
                asset['current_price'] = current_price

        # Основные расчеты
        quantity = asset['quantity']
        purchase_price = asset['purchase_price']
        current_price = asset['current_price'] or purchase_price

        current_value = quantity * current_price
        cost = quantity * purchase_price
        profit = current_value - cost
        profit_percent = (profit / cost * 100) if cost > 0 else Decimal('0')

        # Расчет для разных периодов (если есть история цен)
        price_history = await self._get_price_history(asset['symbol'])

        # Изменения за периоды
        changes = await self._calculate_period_changes(current_price, asset['symbol'])

        # Получаем информацию с MOEX
        moex_info = await price_service.get_asset_info(asset['symbol'])

        return {
            **asset,
            'current_value': current_value,
            'cost': cost,
            'profit': profit,
            'profit_percent': profit_percent,
            'price_change_1d': changes.get('day', Decimal('0')),
            'price_change_1w': changes.get('week', Decimal('0')),
            'price_change_1m': changes.get('month', Decimal('0')),
            'break_even': purchase_price,  # Цена безубыточности
            'required_for_double': purchase_price * 2,  # Цена для удвоения
            'required_for_half': purchase_price / 2,  # Цена для падения вдвое
            'moex_info': moex_info
        }

    async def calculate_portfolio_risk_metrics(self, portfolio_id: int) -> Dict[str, Any]:
        """
        Расчет риск-метрик портфеля

        Args:
            portfolio_id: ID портфеля

        Returns:
            Dict с метриками риска
        """
        summary = await self.calculate_portfolio_summary(portfolio_id)
        if not summary or summary['assets_count'] == 0:
            return {}

        assets = summary['assets']
        total_value = summary['total_value']

        # Концентрация (доля крупнейшего актива)
        if assets and total_value > 0:
            max_weight = float(assets[0]['weight'])
        else:
            max_weight = 0.0

        # Диверсификация (количество активов с весом > 5%)
        diversified = sum(1 for a in assets if a['weight'] > 5)

        # Индекс Херфиндаля-Хиршмана (сумма квадратов долей)
        hhi = sum(float(a['weight'] / 100) ** 2 for a in assets) * 10000

        # Валютный риск (доля не в RUB)
        currency_risk = Decimal('0')
        for asset in assets:
            if asset['currency'] != 'RUB':
                currency_risk += asset['current_value']
        if total_value > 0:
            currency_risk_pct = float(currency_risk / total_value * 100)
        else:
            currency_risk_pct = 0.0

        # Прибыльные/убыточные активы
        profitable = sum(1 for a in assets if a['profit'] > 0)
        unprofitable = sum(1 for a in assets if a['profit'] < 0)

        # Средняя доходность (взвешенная)
        if assets and total_value > 0:
            weighted_return = sum(float(a['profit_percent'] * a['weight'] / 100) for a in assets)
        else:
            weighted_return = 0.0

        # Волатильность портфеля (упрощенно)
        volatility = await self._estimate_portfolio_volatility(assets)

        return {
            'max_concentration': max_weight,
            'diversified_count': diversified,
            'hhi_index': hhi,  # >2500 - высокая концентрация
            'currency_risk_pct': currency_risk_pct,
            'profitable_count': profitable,
            'unprofitable_count': unprofitable,
            'weighted_return': weighted_return,
            'volatility': volatility,
            'risk_level': self._calculate_risk_level(max_weight, diversified, currency_risk_pct, hhi)
        }

    async def get_recommendations(self, portfolio_id: int) -> List[Dict]:
        """
        Получение рекомендаций по портфелю

        Args:
            portfolio_id: ID портфеля

        Returns:
            List с рекомендациями
        """
        summary = await self.calculate_portfolio_summary(portfolio_id)
        if not summary or summary['assets_count'] == 0:
            return [{'type': 'info', 'text': '📭 Портфель пуст', 'action': 'Добавьте активы'}]

        assets = summary['assets']
        total_value = summary['total_value']
        recommendations = []

        # Проверка на слишком большую концентрацию
        if assets and assets[0]['weight'] > 40:
            recommendations.append({
                'type': 'warning',
                'text': f"⚠️ Критически высокая концентрация в {assets[0]['name']} ({assets[0]['weight']:.1f}%)",
                'action': 'Рассмотрите диверсификацию - это снизит риски'
            })
        elif assets and assets[0]['weight'] > 25:
            recommendations.append({
                'type': 'info',
                'text': f"📊 Высокая концентрация в {assets[0]['name']} ({assets[0]['weight']:.1f}%)",
                'action': 'Желательно снизить долю до 15-20%'
            })

        # Проверка на убыточные активы
        losers = [a for a in assets if a['profit_percent'] < -15]
        if losers:
            names = ', '.join([a['symbol'] for a in losers[:3]])
            recommendations.append({
                'type': 'danger',
                'text': f"🔻 Сильно убыточные активы: {names}",
                'action': 'Проанализируйте причины падения, возможно стоит зафиксировать убыток'
            })

        # Проверка на валютный риск
        non_rub = [a for a in assets if a['currency'] != 'RUB']
        if non_rub:
            non_rub_value = sum(a['current_value'] for a in non_rub)
            non_rub_pct = float(non_rub_value / total_value * 100) if total_value > 0 else 0
            if non_rub_pct > 70:
                recommendations.append({
                    'type': 'warning',
                    'text': f"💱 Очень высокая доля валютных активов ({non_rub_pct:.1f}%)",
                    'action': 'Высокий валютный риск, рассмотрите хеджирование'
                })
            elif non_rub_pct > 40:
                recommendations.append({
                    'type': 'info',
                    'text': f"💱 Значительная доля валютных активов ({non_rub_pct:.1f}%)",
                    'action': 'Следите за курсом валют'
                })

        # Проверка на слишком большое количество активов
        if len(assets) > 20:
            recommendations.append({
                'type': 'info',
                'text': f"📊 Много активов ({len(assets)} шт.)",
                'action': 'Сложно отслеживать, рассмотрите консолидацию до 10-15 позиций'
            })
        elif len(assets) < 5 and len(assets) > 0:
            recommendations.append({
                'type': 'info',
                'text': f"📊 Мало активов ({len(assets)} шт.)",
                'action': 'Для диверсификации добавьте еще 3-5 инструментов'
            })

        # Проверка на общую доходность
        if summary['total_profit_percent'] < -10:
            recommendations.append({
                'type': 'warning',
                'text': f"📉 Портфель сильно падает ({summary['total_profit_percent']:.1f}%)",
                'action': 'Проверьте рыночную ситуацию, возможно стоит пересмотреть стратегию'
            })
        elif summary['total_profit_percent'] > 30:
            recommendations.append({
                'type': 'success',
                'text': f"📈 Отличная доходность! ({summary['total_profit_percent']:.1f}%)",
                'action': 'Рассмотрите фиксацию части прибыли'
            })

        # Проверка на отсутствие роста (долгосрочные активы)
        flat_assets = [a for a in assets if abs(a['profit_percent']) < 3 and
                       (datetime.now() - a['created_at']).days > 90]
        if flat_assets:
            symbols = ', '.join([a['symbol'] for a in flat_assets[:3]])
            recommendations.append({
                'type': 'info',
                'text': f"⏸️ Активы без движения: {symbols}",
                'action': 'Рассмотрите замену на более волатильные инструменты'
            })

        return recommendations

    async def get_diversification_suggestions(self, portfolio_id: int) -> List[Dict]:
        """
        Получение предложений по диверсификации

        Args:
            portfolio_id: ID портфеля

        Returns:
            List с предложениями
        """
        summary = await self.calculate_portfolio_summary(portfolio_id)
        if not summary or summary['assets_count'] == 0:
            return []

        assets = summary['assets']
        type_allocation = summary['type_allocation']

        suggestions = []

        # Проверка на отсутствие облигаций
        if 'bond' not in type_allocation and summary['assets_count'] > 3:
            suggestions.append({
                'asset_type': 'bond',
                'text': '📊 Добавьте облигации для снижения волатильности',
                'examples': ['ОФЗ 26238 (SU26238RMFS5)', 'Сбер Sb31R']
            })

        # Проверка на отсутствие ETF
        if 'etf' not in type_allocation and summary['assets_count'] > 5:
            suggestions.append({
                'asset_type': 'etf',
                'text': '📦 Рассмотрите ETF для диверсификации',
                'examples': ['FXUS (акции США)', 'FXIT (технологии)', 'FXMM (денежный рынок)']
            })

        # Проверка на отсутствие валютной диверсификации
        if len(summary['currency_allocation']) == 1 and 'RUB' in summary['currency_allocation']:
            suggestions.append({
                'asset_type': 'currency',
                'text': '💵 Добавьте валютные активы',
                'examples': ['USD/RUB', 'EUR/RUB', 'FXMM']
            })

        return suggestions

    def _need_price_update(self, assets: List[Dict]) -> bool:
        """Проверка необходимости обновления цен"""
        for asset in assets:
            if asset['current_price'] is None:
                return True
            # Если цена не обновлялась больше 2 часов
            if asset['updated_at']:
                age = datetime.now() - asset['updated_at']
                if age.total_seconds() > 7200:
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

        # Сортировка по убыванию
        result = dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
        return result

    async def _get_price_history(self, symbol: str) -> List[Dict]:
        """Получение истории цен из БД"""
        from database.repositories import PriceHistoryRepository
        # Здесь можно расширить для получения истории
        return []

    async def _calculate_period_changes(self, current_price: Decimal, symbol: str) -> Dict[str, Decimal]:
        """Расчет изменений за периоды"""
        from database.repositories import PriceHistoryRepository

        changes = {
            'day': Decimal('0'),
            'week': Decimal('0'),
            'month': Decimal('0'),
            'year': Decimal('0')
        }

        # Получаем историческую цену из БД
        history = await PriceHistoryRepository.get_price(symbol)
        if history:
            # Здесь можно добавить расчет изменений
            pass

        return changes

    async def _estimate_portfolio_volatility(self, assets: List[Dict]) -> float:
        """Упрощенная оценка волатильности портфеля"""
        # В реальности нужно считать на основе исторических данных
        # Пока используем упрощенную оценку по типам активов
        volatility_map = {
            'stock': 30.0,
            'bond': 5.0,
            'etf': 20.0,
            'currency': 10.0,
            'futures': 40.0,
            'other': 15.0
        }

        weighted_vol = 0.0
        for asset in assets:
            vol = volatility_map.get(asset['asset_type'], 15.0)
            weighted_vol += vol * float(asset['weight'] / 100)

        return round(weighted_vol, 1)

    def _calculate_risk_level(self, max_weight: float, diversified: int,
                              currency_risk: float, hhi: float) -> str:
        """Расчет уровня риска"""
        risk_score = 0

        # Концентрация
        if max_weight > 50:
            risk_score += 4
        elif max_weight > 35:
            risk_score += 3
        elif max_weight > 20:
            risk_score += 2
        elif max_weight > 10:
            risk_score += 1

        # HHI индекс (>2500 - высокая концентрация)
        if hhi > 3000:
            risk_score += 3
        elif hhi > 2000:
            risk_score += 2
        elif hhi > 1500:
            risk_score += 1

        # Диверсификация
        if diversified < 3:
            risk_score += 3
        elif diversified < 5:
            risk_score += 2
        elif diversified < 8:
            risk_score += 1

        # Валютный риск
        if currency_risk > 70:
            risk_score += 3
        elif currency_risk > 50:
            risk_score += 2
        elif currency_risk > 30:
            risk_score += 1

        if risk_score >= 10:
            return "🔴 Высокий"
        elif risk_score >= 6:
            return "🟡 Средний"
        else:
            return "🟢 Низкий"

    async def export_portfolio(self, portfolio_id: int, format: str = 'csv') -> str:
        """
        Экспорт портфеля в файл

        Args:
            portfolio_id: ID портфеля
            format: Формат экспорта (csv, json)

        Returns:
            str: Данные для экспорта
        """
        summary = await self.calculate_portfolio_summary(portfolio_id)
        if not summary:
            return ""

        if format == 'json':
            import json

            # Конвертируем Decimal в float для JSON
            def decimal_default(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                raise TypeError

            return json.dumps(summary, default=decimal_default, indent=2, ensure_ascii=False)
        else:  # csv
            import csv
            from io import StringIO

            output = StringIO()
            writer = csv.writer(output)

            # Заголовки
            writer.writerow(['Символ', 'Название', 'Тип', 'Количество', 'Валюта',
                             'Цена покупки', 'Текущая цена', 'Стоимость',
                             'Прибыль', 'Прибыль %', 'Вес %'])

            # Данные
            for asset in summary['assets']:
                writer.writerow([
                    asset['symbol'],
                    asset['name'],
                    asset['asset_type'],
                    float(asset['quantity']),
                    asset['currency'],
                    float(asset['purchase_price']),
                    float(asset['current_price'] or 0),
                    float(asset['current_value']),
                    float(asset['profit']),
                    float(asset['profit_percent']),
                    float(asset['weight'])
                ])

            return output.getvalue()

    def clear_cache(self):
        """Очистка кэша"""
        self.cache.clear()
        logger.info("🧹 Кэш портфелей очищен")


# Глобальный экземпляр сервиса
portfolio_service = PortfolioService()