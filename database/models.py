from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Numeric,
    DateTime, Boolean, ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

Base = declarative_base()


class User(Base):
    """Модель пользователя Telegram"""
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True)  # Telegram ID
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"


class Portfolio(Base):
    """Модель портфеля пользователя"""
    __tablename__ = 'portfolios'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    total_value = Column(Numeric(20, 8), default=0)
    currency = Column(String(10), default='RUB')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    user = relationship("User", back_populates="portfolios")
    assets = relationship("Asset", back_populates="portfolio", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="portfolio", cascade="all, delete-orphan")

    # Уникальность имени портфеля для пользователя
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_portfolio_user_name'),
    )

    def __repr__(self):
        return f"<Portfolio(id={self.id}, name={self.name}, user_id={self.user_id})>"


class Asset(Base):
    """Модель актива в портфеле"""
    __tablename__ = 'assets'

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.id', ondelete='CASCADE'), nullable=False)
    symbol = Column(String(50), nullable=False)  # Тикер на MOEX
    name = Column(String(255), nullable=False)  # Название
    asset_type = Column(String(50), nullable=False)  # stock, bond, etf, currency, futures
    quantity = Column(Numeric(20, 8), nullable=False)
    purchase_price = Column(Numeric(20, 8), nullable=False)
    current_price = Column(Numeric(20, 8), nullable=True)
    currency = Column(String(10), default='RUB')
    sector = Column(String(255), nullable=True)  # Сектор экономики
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    portfolio = relationship("Portfolio", back_populates="assets")
    alerts = relationship("Alert", back_populates="asset", cascade="all, delete-orphan")

    # Уникальность символа в портфеле
    __table_args__ = (
        UniqueConstraint('portfolio_id', 'symbol', name='uq_asset_portfolio_symbol'),
        Index('ix_assets_symbol', 'symbol'),
        Index('ix_assets_type', 'asset_type'),
    )

    @property
    def current_value(self) -> Decimal:
        """Текущая стоимость актива"""
        if self.current_price and self.quantity:
            return self.current_price * self.quantity
        return Decimal('0')

    @property
    def purchase_value(self) -> Decimal:
        """Стоимость покупки"""
        return self.purchase_price * self.quantity

    @property
    def profit(self) -> Decimal:
        """Абсолютная прибыль"""
        return self.current_value - self.purchase_value

    @property
    def profit_percent(self) -> Decimal:
        """Процент прибыли"""
        if self.purchase_value > 0:
            return (self.profit / self.purchase_value) * 100
        return Decimal('0')

    def __repr__(self):
        return f"<Asset(id={self.id}, symbol={self.symbol}, portfolio_id={self.portfolio_id})>"


class Alert(Base):
    """Модель уведомления"""
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    portfolio_id = Column(Integer, ForeignKey('portfolios.id', ondelete='CASCADE'), nullable=True)
    asset_id = Column(Integer, ForeignKey('assets.id', ondelete='CASCADE'), nullable=True)
    alert_type = Column(String(20), nullable=False)  # portfolio, asset
    condition_type = Column(String(20), nullable=False)  # price, percent
    direction = Column(String(10), nullable=False)  # up, down
    target_value = Column(Numeric(20, 8), nullable=False)
    current_value = Column(Numeric(20, 8), nullable=True)
    is_active = Column(Boolean, default=True)
    is_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    triggered_at = Column(DateTime, nullable=True)

    # Связи
    user = relationship("User", back_populates="alerts")
    portfolio = relationship("Portfolio", back_populates="alerts")
    asset = relationship("Asset", back_populates="alerts")

    # Проверка целостности
    __table_args__ = (
        Index('ix_alerts_user_active', 'user_id', 'is_active'),
        Index('ix_alerts_triggered', 'is_triggered'),
    )

    def __repr__(self):
        return f"<Alert(id={self.id}, type={self.alert_type}, user_id={self.user_id})>"


class PriceHistory(Base):
    """Модель истории цен (кэш)"""
    __tablename__ = 'price_history'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, unique=True)
    price = Column(Numeric(20, 8), nullable=False)
    currency = Column(String(10), default='RUB')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('ix_price_history_symbol', 'symbol'),
    )

    def __repr__(self):
        return f"<PriceHistory(symbol={self.symbol}, price={self.price})>"


class MarketData(Base):
    """Модель для хранения дополнительных рыночных данных"""
    __tablename__ = 'market_data'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    sector = Column(String(255), nullable=True)
    industry = Column(String(255), nullable=True)
    market_cap = Column(Numeric(20, 2), nullable=True)  # Капитализация
    volume_24h = Column(Numeric(20, 0), nullable=True)  # Объем за 24ч
    high_52w = Column(Numeric(20, 8), nullable=True)  # Максимум за 52 недели
    low_52w = Column(Numeric(20, 8), nullable=True)  # Минимум за 52 недели
    dividend_yield = Column(Numeric(10, 4), nullable=True)  # Дивидендная доходность
    pe_ratio = Column(Numeric(10, 4), nullable=True)  # P/E
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('ix_market_data_symbol', 'symbol'),
    )

    def __repr__(self):
        return f"<MarketData(symbol={self.symbol}, name={self.name})>"


# Функция для создания таблиц
def create_tables(engine):
    """Создание всех таблиц в БД"""
    Base.metadata.create_all(engine)