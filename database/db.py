import asyncpg
from typing import Optional
from contextlib import asynccontextmanager
from logger import get_logger
from config import Config

logger = get_logger('database')


class Database:
    """Управление подключением к PostgreSQL"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Создание пула подключений"""
        try:
            self.pool = await asyncpg.create_pool(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                min_size=5,
                max_size=20,
                command_timeout=60,
                max_queries=50000,
                max_inactive_connection_lifetime=300
            )
            logger.info("✅ Подключение к БД установлено")

            # Создаем таблицы при первом запуске
            await self.create_tables()

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    async def disconnect(self):
        """Закрытие пула подключений"""
        if self.pool:
            await self.pool.close()
            logger.info("👋 Подключение к БД закрыто")

    @asynccontextmanager
    async def acquire(self):
        """Получение соединения из пула"""
        async with self.pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, *args):
        """Выполнение запроса"""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        """Получение нескольких записей"""
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        """Получение одной записи"""
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Получение одного значения"""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def create_tables(self):
        """Создание таблиц при первом запуске"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS portfolios (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                total_value DECIMAL(20, 8) DEFAULT 0,
                currency TEXT DEFAULT 'RUB',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS assets (
                id SERIAL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                quantity DECIMAL(20, 8) NOT NULL,
                purchase_price DECIMAL(20, 8) NOT NULL,
                current_price DECIMAL(20, 8),
                currency TEXT DEFAULT 'RUB',
                sector TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(portfolio_id, symbol)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
                asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
                alert_type TEXT NOT NULL,
                condition_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                target_value DECIMAL(20, 8) NOT NULL,
                current_value DECIMAL(20, 8),
                is_active BOOLEAN DEFAULT TRUE,
                is_triggered BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered_at TIMESTAMP,
                CHECK (
                    (alert_type = 'portfolio' AND portfolio_id IS NOT NULL AND asset_id IS NULL) OR
                    (alert_type = 'asset' AND asset_id IS NOT NULL AND portfolio_id IS NULL)
                )
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL UNIQUE,
                price DECIMAL(20, 8) NOT NULL,
                currency TEXT DEFAULT 'RUB',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS market_data (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL UNIQUE,
                name TEXT,
                sector TEXT,
                industry TEXT,
                market_cap DECIMAL(20, 2),
                volume_24h DECIMAL(20, 0),
                high_52w DECIMAL(20, 8),
                low_52w DECIMAL(20, 8),
                dividend_yield DECIMAL(10, 4),
                pe_ratio DECIMAL(10, 4),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_assets_portfolio ON assets(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_assets_symbol ON assets(symbol);
            CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
            CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);
            CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(is_active) WHERE is_active = true;
            CREATE INDEX IF NOT EXISTS idx_alerts_triggered ON alerts(is_triggered) WHERE is_triggered = false;
            CREATE INDEX IF NOT EXISTS idx_price_history_symbol ON price_history(symbol);
            CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol);
            """
        ]

        for query in queries:
            try:
                await self.execute(query)
            except Exception as e:
                logger.error(f"Ошибка создания таблицы: {e}")

        logger.info("✅ Таблицы проверены/созданы")


# Глобальный экземпляр БД
db = Database()