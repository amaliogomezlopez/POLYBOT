"""SQLAlchemy database models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MarketRecord(Base):
    """Market metadata cache."""

    __tablename__ = "markets"

    id = Column(String(100), primary_key=True)
    condition_id = Column(String(100), index=True)
    question = Column(Text)
    slug = Column(String(200))
    asset = Column(String(10), index=True)
    up_token_id = Column(String(100))
    down_token_id = Column(String(100))
    end_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PositionRecord(Base):
    """Position record for tracking open and closed positions."""

    __tablename__ = "positions"

    id = Column(String(36), primary_key=True)
    market_id = Column(String(100), index=True)
    state = Column(String(20), index=True)

    # UP leg
    up_token_id = Column(String(100))
    up_contracts = Column(Float, default=0.0)
    up_avg_price = Column(Float, default=0.0)
    up_order_id = Column(String(100))

    # DOWN leg
    down_token_id = Column(String(100))
    down_contracts = Column(Float, default=0.0)
    down_avg_price = Column(Float, default=0.0)
    down_order_id = Column(String(100))

    # Cost and P&L
    total_cost = Column(Float, default=0.0)
    settlement_value = Column(Float)
    realized_pnl = Column(Float)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    settled_at = Column(DateTime)


class TradeRecord(Base):
    """Individual trade record."""

    __tablename__ = "trades"

    id = Column(String(36), primary_key=True)
    position_id = Column(String(36), index=True)
    order_id = Column(String(100))
    market_id = Column(String(100), index=True)
    token_id = Column(String(100))
    outcome_type = Column(String(10))  # UP/DOWN
    side = Column(String(10))  # BUY/SELL
    price = Column(Float)
    size = Column(Float)
    fee = Column(Float, default=0.0)
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)


class PnLSnapshotRecord(Base):
    """Periodic P&L snapshot for tracking performance over time."""

    __tablename__ = "pnl_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    unrealized_pnl = Column(Float)
    realized_pnl = Column(Float)
    total_pnl = Column(Float)
    open_positions = Column(Integer)
    total_exposure = Column(Float)
    daily_trades = Column(Integer)


class AlertRecord(Base):
    """Alert history record."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), index=True)
    title = Column(String(200))
    message = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)
