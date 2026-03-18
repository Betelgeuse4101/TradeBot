from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from database.db import db
from logger import get_logger

logger = get_logger('repositories')


class UserRepository:
    """Репозиторий для работы с пользователями"""

    @staticmethod
    async def create_or_update(user_id: int, username: str = None,
                               first_name: str = None, last_name: str = None,
                               broker_type: str = None, broker_token: str = None) -> bool:
        """Создание или обновление пользователя"""
        query = """
        INSERT INTO users (id, username, first_name, last_name, created_at, updated_at)
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            updated_at = CURRENT_TIMESTAMP
        """
        try:
            await db.execute(query, user_id, username, first_name, last_name)
            logger.info(f"👤 Пользователь {user_id} сохранен")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения пользователя {user_id}: {e}")
            return False

    @staticmethod
    async def get(user_id: int) -> Optional[Dict]:
        """Получение пользователя"""
        query = "SELECT * FROM users WHERE id = $1"
        row = await db.fetchrow(query, user_id)
        return dict(row) if row else None


class PortfolioRepository:
    """Репозиторий для работы с портфелями"""

    @staticmethod
    async def create(user_id: int, name: str, description: str = None,
                     currency: str = 'RUB') -> Optional[int]:
        """Создание портфеля"""
        query = """
        INSERT INTO portfolios (user_id, name, description, currency)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """
        try:
            portfolio_id = await db.fetchval(query, user_id, name, description, currency)
            logger.info(f"📊 Портфель '{name}' создан для пользователя {user_id}")
            return portfolio_id
        except Exception as e:
            logger.error(f"Ошибка создания портфеля: {e}")
            return None

    @staticmethod
    async def get_user_portfolios(user_id: int) -> List[Dict]:
        """Получение всех портфелей пользователя"""
        query = """
        SELECT p.*, 
               COUNT(a.id) as assets_count,
               COALESCE(SUM(a.quantity * COALESCE(a.current_price, a.purchase_price)), 0) as current_value
        FROM portfolios p
        LEFT JOIN assets a ON p.id = a.portfolio_id
        WHERE p.user_id = $1
        GROUP BY p.id
        ORDER BY p.created_at
        """
        rows = await db.fetch(query, user_id)
        return [dict(row) for row in rows]

    @staticmethod
    async def update_name(portfolio_id: int, name: str) -> bool:
        """Обновление названия портфеля"""
        query = """
        UPDATE portfolios 
        SET name = $1, updated_at = CURRENT_TIMESTAMP 
        WHERE id = $2
        """
        try:
            await db.execute(query, name, portfolio_id)
            logger.info(f"✏️ Название портфеля {portfolio_id} обновлено на '{name}'")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления названия портфеля {portfolio_id}: {e}")
            return False

    @staticmethod
    async def update_description(portfolio_id: int, description: str = None) -> bool:
        """Обновление описания портфеля"""
        query = """
        UPDATE portfolios 
        SET description = $1, updated_at = CURRENT_TIMESTAMP 
        WHERE id = $2
        """
        try:
            await db.execute(query, description, portfolio_id)
            logger.info(f"✏️ Описание портфеля {portfolio_id} обновлено")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления описания портфеля {portfolio_id}: {e}")
            return False

    @staticmethod
    async def get(portfolio_id: int) -> Optional[Dict]:
        """Получение портфеля по ID"""
        query = "SELECT * FROM portfolios WHERE id = $1"
        row = await db.fetchrow(query, portfolio_id)
        return dict(row) if row else None

    @staticmethod
    async def update_value(portfolio_id: int, total_value: Decimal):
        """Обновление общей стоимости портфеля"""
        query = "UPDATE portfolios SET total_value = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2"
        await db.execute(query, total_value, portfolio_id)

    @staticmethod
    async def delete(portfolio_id: int) -> bool:
        """Удаление портфеля"""
        query = "DELETE FROM portfolios WHERE id = $1"
        try:
            await db.execute(query, portfolio_id)
            logger.info(f"🗑️ Портфель {portfolio_id} удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления портфеля {portfolio_id}: {e}")
            return False


class AssetRepository:
    """Репозиторий для работы с активами"""

    @staticmethod
    async def add(portfolio_id: int, symbol: str, name: str, asset_type: str,
                  quantity: Decimal, purchase_price: Decimal, currency: str = 'RUB',
                  sector: str = None, notes: str = None) -> Optional[int]:
        """Добавление актива в портфель"""

        # Валидация
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным")
        if purchase_price <= 0:
            raise ValueError("Цена покупки должна быть положительной")

        query = """
        INSERT INTO assets (portfolio_id, symbol, name, asset_type, quantity, 
                           purchase_price, currency, sector, notes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (portfolio_id, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            purchase_price = EXCLUDED.purchase_price,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
        """
        try:
            asset_id = await db.fetchval(query, portfolio_id, symbol.upper(), name,
                                         asset_type, quantity, purchase_price,
                                         currency, sector, notes)
            logger.info(f"➕ Актив {symbol} добавлен в портфель {portfolio_id}")
            return asset_id
        except Exception as e:
            logger.error(f"Ошибка добавления актива: {e}")
            return None

    @staticmethod
    async def get_portfolio_assets(portfolio_id: int) -> List[Dict]:
        """Получение всех активов портфеля"""
        query = """
        SELECT * FROM assets 
        WHERE portfolio_id = $1 
        ORDER BY symbol
        """
        rows = await db.fetch(query, portfolio_id)
        return [dict(row) for row in rows]

    @staticmethod
    async def get_all_assets() -> List[Dict]:
        """Получение всех активов всех пользователей"""
        query = """
        SELECT a.*, p.user_id 
        FROM assets a
        JOIN portfolios p ON a.portfolio_id = p.id
        """
        rows = await db.fetch(query)
        return [dict(row) for row in rows]

    @staticmethod
    async def get(asset_id: int) -> Optional[Dict]:
        """Получение актива по ID"""
        query = "SELECT * FROM assets WHERE id = $1"
        row = await db.fetchrow(query, asset_id)
        return dict(row) if row else None

    @staticmethod
    async def update_price(asset_id: int, current_price: Decimal):
        """Обновление текущей цены актива"""
        query = "UPDATE assets SET current_price = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2"
        await db.execute(query, current_price, asset_id)

    @staticmethod
    async def update_quantity(asset_id: int, quantity: Decimal):
        """Обновление количества актива"""
        if quantity < 0:
            raise ValueError("Количество не может быть отрицательным")

        query = "UPDATE assets SET quantity = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2"
        await db.execute(query, quantity, asset_id)

    @staticmethod
    async def delete(asset_id: int) -> bool:
        """Удаление актива"""
        query = "DELETE FROM assets WHERE id = $1"
        try:
            await db.execute(query, asset_id)
            logger.info(f"🗑️ Актив {asset_id} удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления актива {asset_id}: {e}")
            return False


class AlertRepository:
    """Репозиторий для работы с уведомлениями"""

    @staticmethod
    async def create_portfolio_alert(user_id: int, portfolio_id: int,
                                     condition_type: str, direction: str,
                                     target_value: Decimal) -> Optional[int]:
        """Создание уведомления для портфеля"""

        if target_value <= 0:
            raise ValueError("Целевое значение должно быть положительным")

        query = """
        INSERT INTO alerts (user_id, portfolio_id, alert_type, condition_type, 
                           direction, target_value, is_active)
        VALUES ($1, $2, 'portfolio', $3, $4, $5, true)
        RETURNING id
        """
        try:
            alert_id = await db.fetchval(query, user_id, portfolio_id,
                                         condition_type, direction, target_value)
            logger.info(f"🔔 Создано уведомление портфеля {alert_id}")
            return alert_id
        except Exception as e:
            logger.error(f"Ошибка создания уведомления портфеля: {e}")
            return None

    @staticmethod
    async def create_asset_alert(user_id: int, asset_id: int,
                                 condition_type: str, direction: str,
                                 target_value: Decimal) -> Optional[int]:
        """Создание уведомления для актива"""

        if target_value <= 0:
            raise ValueError("Целевое значение должно быть положительным")

        query = """
        INSERT INTO alerts (user_id, asset_id, alert_type, condition_type, 
                           direction, target_value, is_active)
        VALUES ($1, $2, 'asset', $3, $4, $5, true)
        RETURNING id
        """
        try:
            alert_id = await db.fetchval(query, user_id, asset_id,
                                         condition_type, direction, target_value)
            logger.info(f"🔔 Создано уведомление актива {alert_id}")
            return alert_id
        except Exception as e:
            logger.error(f"Ошибка создания уведомления актива: {e}")
            return None

    @staticmethod
    async def get_user_alerts(user_id: int, active_only: bool = True) -> List[Dict]:
        """Получение уведомлений пользователя"""
        query = """
        SELECT a.*, 
               p.name as portfolio_name,
               p.currency as portfolio_currency,
               ast.symbol as asset_symbol,
               ast.name as asset_name,
               ast.currency as asset_currency
        FROM alerts a
        LEFT JOIN portfolios p ON a.portfolio_id = p.id
        LEFT JOIN assets ast ON a.asset_id = ast.id
        WHERE a.user_id = $1
        """
        if active_only:
            query += " AND a.is_active = true"
        query += " ORDER BY a.created_at DESC"

        rows = await db.fetch(query, user_id)
        return [dict(row) for row in rows]

    @staticmethod
    async def get_active_alerts() -> List[Dict]:
        """Получение всех активных уведомлений для проверки"""
        query = """
        SELECT a.*, 
               p.user_id as portfolio_user_id,
               p.name as portfolio_name,
               ast.portfolio_id as asset_portfolio_id,
               ast.symbol as asset_symbol,
               ast.name as asset_name,
               ast.current_price as asset_current_price
        FROM alerts a
        LEFT JOIN portfolios p ON a.portfolio_id = p.id
        LEFT JOIN assets ast ON a.asset_id = ast.id
        WHERE a.is_active = true AND a.is_triggered = false
        """
        rows = await db.fetch(query)
        return [dict(row) for row in rows]

    @staticmethod
    async def get(alert_id: int) -> Optional[Dict]:
        """Получение уведомления по ID"""
        query = """
        SELECT a.*, 
               p.name as portfolio_name,
               ast.symbol as asset_symbol,
               ast.name as asset_name
        FROM alerts a
        LEFT JOIN portfolios p ON a.portfolio_id = p.id
        LEFT JOIN assets ast ON a.asset_id = ast.id
        WHERE a.id = $1
        """
        row = await db.fetchrow(query, alert_id)
        return dict(row) if row else None

    @staticmethod
    async def update_current_value(alert_id: int, current_value: Decimal):
        """Обновление текущего значения"""
        query = "UPDATE alerts SET current_value = $1 WHERE id = $2"
        await db.execute(query, current_value, alert_id)

    @staticmethod
    async def mark_triggered(alert_id: int):
        """Отметить уведомление как сработавшее"""
        query = """
        UPDATE alerts 
        SET is_triggered = true, triggered_at = CURRENT_TIMESTAMP 
        WHERE id = $1
        """
        await db.execute(query, alert_id)

    @staticmethod
    async def deactivate(alert_id: int):
        """Деактивировать уведомление"""
        query = "UPDATE alerts SET is_active = false WHERE id = $1"
        await db.execute(query, alert_id)

    @staticmethod
    async def reactivate(alert_id: int):
        """Реактивировать уведомление"""
        query = """
        UPDATE alerts 
        SET is_active = true, is_triggered = false, triggered_at = NULL 
        WHERE id = $1
        """
        await db.execute(query, alert_id)

    @staticmethod
    async def delete(alert_id: int) -> bool:
        """Удаление уведомления"""
        query = "DELETE FROM alerts WHERE id = $1"
        try:
            await db.execute(query, alert_id)
            logger.info(f"🗑️ Уведомление {alert_id} удалено")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления уведомления {alert_id}: {e}")
            return False


class PriceHistoryRepository:
    """Репозиторий для хранения цен"""

    @staticmethod
    async def update_price(symbol: str, price: Decimal, currency: str = 'RUB'):
        """Обновление цены символа"""
        query = """
        INSERT INTO price_history (symbol, price, currency, updated_at)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ON CONFLICT (symbol) DO UPDATE SET
            price = EXCLUDED.price,
            currency = EXCLUDED.currency,
            updated_at = CURRENT_TIMESTAMP
        """
        await db.execute(query, symbol.upper(), price, currency)

    @staticmethod
    async def get_price(symbol: str) -> Optional[Dict]:
        """Получение последней цены"""
        query = "SELECT * FROM price_history WHERE symbol = $1"
        row = await db.fetchrow(query, symbol.upper())
        return dict(row) if row else None

    @staticmethod
    async def get_all_prices() -> List[Dict]:
        """Получение всех цен"""
        rows = await db.fetch("SELECT * FROM price_history")
        return [dict(row) for row in rows]

    @staticmethod
    async def get_price_history(symbol: str, days: int = 30) -> List[Dict]:
        """Получение истории цен (заглушка, можно расширить)"""
        # Здесь можно добавить логику получения истории
        return []
