from typing import List, Dict, Any, Optional
from decimal import Decimal
import asyncio
from datetime import datetime, timedelta

from database.repositories import AlertRepository, PortfolioRepository, AssetRepository
from services.price_service import price_service
from services.portfolio_service import portfolio_service
from logger import get_logger
from aiogram import Bot
from utils import format_money, format_percent

logger = get_logger('alert_service')


class AlertService:
    """Сервис для проверки и отправки уведомлений"""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False
        self.check_interval = 60  # секунд
        self.notification_cooldown = {}  # Для защиты от спама

    async def start(self):
        """Запуск фоновой проверки"""
        self.is_running = True
        logger.info("🚀 Запуск сервиса уведомлений")

        while self.is_running:
            try:
                await self.check_alerts()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Ошибка в сервисе уведомлений: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        """Остановка сервиса"""
        self.is_running = False
        logger.info("🛑 Сервис уведомлений остановлен")

    async def check_alerts(self):
        """Проверка всех активных уведомлений"""
        alerts = await AlertRepository.get_active_alerts()

        if not alerts:
            return

        logger.info(f"🔍 Проверка {len(alerts)} уведомлений")

        # Группируем уведомления по пользователям для оптимизации
        alerts_by_user = {}
        for alert in alerts:
            user_id = alert['user_id']
            if user_id not in alerts_by_user:
                alerts_by_user[user_id] = []
            alerts_by_user[user_id].append(alert)

        for user_id, user_alerts in alerts_by_user.items():
            await self._check_user_alerts(user_id, user_alerts)

    async def _check_user_alerts(self, user_id: int, alerts: List[Dict]):
        """Проверка уведомлений конкретного пользователя"""
        for alert in alerts:
            try:
                # Проверка на cooldown (не чаще раза в 5 минут для одного уведомления)
                cooldown_key = f"{user_id}_{alert['id']}"
                if cooldown_key in self.notification_cooldown:
                    last_check = self.notification_cooldown[cooldown_key]
                    if datetime.now() - last_check < timedelta(minutes=5):
                        continue

                await self.check_alert(alert)
                self.notification_cooldown[cooldown_key] = datetime.now()

            except Exception as e:
                logger.error(f"Ошибка проверки уведомления {alert['id']}: {e}")

    async def check_alert(self, alert: Dict[str, Any]):
        """Проверка конкретного уведомления"""
        alert_id = alert['id']
        user_id = alert['user_id']
        condition_type = alert['condition_type']
        direction = alert['direction']
        target_value = alert['target_value']

        current_value = None
        current_price = None
        asset_symbol = None

        if alert['alert_type'] == 'portfolio':
            # Уведомление по портфелю
            portfolio_id = alert['portfolio_id']

            # Получаем активы портфеля
            assets = await AssetRepository.get_portfolio_assets(portfolio_id)

            if not assets:
                logger.debug(f"Портфель {portfolio_id} пуст, пропускаем уведомление {alert_id}")
                return

            # Обновляем цены если нужно
            need_update = any(not a['current_price'] for a in assets)
            if need_update:
                await price_service.update_portfolio_prices(portfolio_id)
                assets = await AssetRepository.get_portfolio_assets(portfolio_id)

            # Считаем стоимость портфеля
            portfolio_value = await price_service.calculate_portfolio_value(portfolio_id, assets)
            current_value = portfolio_value['total_value']

        else:
            # Уведомление по активу
            asset_id = alert['asset_id']
            asset = await AssetRepository.get(asset_id)

            if not asset:
                logger.warning(f"Актив {asset_id} не найден, деактивируем уведомление {alert_id}")
                await AlertRepository.deactivate(alert_id)
                return

            asset_symbol = asset['symbol']

            if condition_type == 'price':
                # Обновляем цену
                current_price = await price_service.get_price(asset['symbol'])
                if current_price:
                    await AssetRepository.update_price(asset_id, current_price)
                    asset['current_price'] = current_price
                current_value = asset['current_price'] or asset['purchase_price']
            else:  # percent
                # Обновляем цену для расчета процента
                current_price = await price_service.get_price(asset['symbol'])
                if current_price:
                    await AssetRepository.update_price(asset_id, current_price)
                    asset['current_price'] = current_price

                # Рассчитываем процент изменения от цены покупки
                if asset['purchase_price'] > 0:
                    price = asset['current_price'] or asset['purchase_price']
                    current_value = ((price - asset['purchase_price']) / asset['purchase_price']) * 100
                else:
                    current_value = Decimal('0')

        if current_value is None:
            return

        # Сохраняем текущее значение
        await AlertRepository.update_current_value(alert_id, current_value)

        # Проверяем условие
        triggered = False

        if condition_type == 'price':
            if direction == 'up' and current_value >= target_value:
                triggered = True
                logger.info(f"🎯 Уведомление {alert_id} сработало: {current_value} >= {target_value}")
            elif direction == 'down' and current_value <= target_value:
                triggered = True
                logger.info(f"🎯 Уведомление {alert_id} сработало: {current_value} <= {target_value}")
        else:  # percent
            if direction == 'up' and current_value >= target_value:
                triggered = True
                logger.info(f"🎯 Уведомление {alert_id} сработало: {current_value}% >= {target_value}%")
            elif direction == 'down' and current_value <= target_value:
                triggered = True
                logger.info(f"🎯 Уведомление {alert_id} сработало: {current_value}% <= {target_value}%")

        if triggered:
            await self.trigger_alert(alert, current_value, current_price)

    async def trigger_alert(self, alert: Dict[str, Any], current_value: Decimal, current_price: Decimal = None):
        """Срабатывание уведомления"""
        alert_id = alert['id']
        user_id = alert['user_id']

        # Отмечаем как сработавшее
        await AlertRepository.mark_triggered(alert_id)

        # Формируем сообщение
        if alert['alert_type'] == 'portfolio':
            text = await self._format_portfolio_alert(alert, current_value)
        else:
            text = await self._format_asset_alert(alert, current_value, current_price)

        # Отправляем уведомление
        try:
            await self.bot.send_message(user_id, text)
            logger.info(f"📨 Отправлено уведомление #{alert_id} пользователю {user_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления #{alert_id}: {e}")

    async def _format_portfolio_alert(self, alert: Dict, current_value: Decimal) -> str:
        """Форматирование уведомления по портфелю"""
        direction_icon = "📈" if alert['direction'] == 'up' else "📉"
        direction_text = "выше" if alert['direction'] == 'up' else "ниже"

        if alert['condition_type'] == 'price':
            target_text = format_money(alert['target_value'])
            current_text = format_money(current_value)
        else:
            target_text = f"{float(alert['target_value']):+.1f}%"
            current_text = f"{float(current_value):+.1f}%"

        # Получаем детали портфеля для более информативного сообщения
        portfolio_id = alert['portfolio_id']
        portfolio = await PortfolioRepository.get(portfolio_id)

        portfolio_name = portfolio['name'] if portfolio else f"ID:{portfolio_id}"

        return f"""
🚨 <b>УВЕДОМЛЕНИЕ ПО ПОРТФЕЛЮ</b>

📊 Портфель: <b>{portfolio_name}</b>

{direction_icon} Цель: {direction_text} {target_text}
💰 Текущая стоимость: <b>{current_text}</b>

📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}

<i>Уведомление выполнено ✅</i>
        """

    async def _format_asset_alert(self, alert: Dict, current_value: Decimal, current_price: Decimal = None) -> str:
        """Форматирование уведомления по активу"""
        direction_icon = "📈" if alert['direction'] == 'up' else "📉"
        direction_text = "выше" if alert['direction'] == 'up' else "ниже"

        asset_name = alert.get('asset_name', alert.get('asset_symbol', 'Неизвестно'))
        asset_symbol = alert.get('asset_symbol', '')

        if alert['condition_type'] == 'price':
            target_text = format_money(alert['target_value'])
            current_text = format_money(current_value)
            details = f"💰 Текущая цена: <b>{current_text}</b>"
        else:
            target_text = f"{float(alert['target_value']):+.1f}%"
            current_text = f"{float(current_value):+.1f}%"

            if current_price:
                price_text = format_money(current_price)
                details = f"💰 Текущая цена: {price_text}\n📊 Изменение: <b>{current_text}</b>"
            else:
                details = f"📊 Изменение: <b>{current_text}</b>"

        return f"""
🚨 <b>УВЕДОМЛЕНИЕ ПО АКТИВУ</b>

💎 Актив: <b>{asset_name}</b> ({asset_symbol})

{direction_icon} Цель: {direction_text} {target_text}
{details}

📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}

<i>Уведомление выполнено ✅</i>
        """

    async def create_test_notification(self, user_id: int, message: str):
        """Создание тестового уведомления (для отладки)"""
        try:
            await self.bot.send_message(
                user_id,
                f"🧪 <b>Тестовое уведомление</b>\n\n{message}",
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка тестового уведомления: {e}")
            return False