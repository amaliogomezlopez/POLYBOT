"""
🗃️ MULTI-STRATEGY DATABASE MODELS
===================================
SQLAlchemy models optimized for multi-strategy paper trading
with rich metadata for ML retraining.

Tables:
- Strategy: Strategy configuration registry
- Trade: All trades with strategy attribution
- MarketSnapshot: Point-in-time market state
- StrategyPerformance: Aggregated metrics per strategy
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
import enum

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, Index, Enum, JSON, DECIMAL,
    UniqueConstraint, CheckConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB

import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://polybot:PolyBot2026Trading!@localhost:5432/polymarket"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =============================================================================
# ENUMS
# =============================================================================

class StrategyType(enum.Enum):
    """Strategy types supported by the system."""
    ARBITRAGE = "ARBITRAGE"           # Cross-exchange arbitrage
    SNIPER = "SNIPER"                 # Microstructure sniper
    TAIL = "TAIL"                     # Tail betting
    CUSTOM = "CUSTOM"                 # User-defined

class TradeStatus(enum.Enum):
    """Trade lifecycle status."""
    SIGNAL = "SIGNAL"                 # Signal generated, not executed
    PENDING = "PENDING"               # Order submitted
    FILLED = "FILLED"                 # Order filled
    PARTIAL = "PARTIAL"               # Partially filled
    CANCELLED = "CANCELLED"           # Cancelled
    RESOLVED_WIN = "RESOLVED_WIN"     # Market resolved, won
    RESOLVED_LOSS = "RESOLVED_LOSS"   # Market resolved, lost
    EXPIRED = "EXPIRED"               # Expired without resolution

class Side(enum.Enum):
    """Trade side."""
    BUY = "BUY"
    SELL = "SELL"

class Outcome(enum.Enum):
    """Market outcome."""
    YES = "YES"
    NO = "NO"

# =============================================================================
# STRATEGY REGISTRY
# =============================================================================

class Strategy(Base):
    """
    Strategy configuration and metadata.
    Each strategy instance is registered here with its parameters.
    """
    __tablename__ = "strategies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identity
    strategy_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    strategy_type = Column(Enum(StrategyType), nullable=False)
    version = Column(String(20), default="1.0.0")
    
    # Configuration (JSON for flexibility)
    parameters = Column(JSONB, default={})
    
    # State
    is_active = Column(Boolean, default=True)
    paper_mode = Column(Boolean, default=True)
    
    # Limits
    max_position_size = Column(DECIMAL(18, 8), default=100)
    max_daily_trades = Column(Integer, default=50)
    max_drawdown_pct = Column(Float, default=20.0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    trades = relationship("Trade", back_populates="strategy")
    
    def __repr__(self):
        return f"<Strategy {self.strategy_id} ({self.strategy_type.value})>"

# =============================================================================
# TRADE MODEL (ENHANCED)
# =============================================================================

class Trade(Base):
    """
    Individual trade record with full attribution and market snapshot.
    Designed for ML retraining with rich contextual data.
    """
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Strategy Attribution (CRITICAL for multi-strategy)
    strategy_id = Column(String(50), ForeignKey("strategies.strategy_id"), nullable=False, index=True)
    
    # Market Identification
    condition_id = Column(String(100), nullable=False, index=True)
    token_id = Column(String(100))
    market_slug = Column(String(255))
    question = Column(Text)
    
    # Trade Details
    side = Column(Enum(Side), nullable=False)
    outcome = Column(Enum(Outcome), nullable=False)
    
    # Pricing
    entry_price = Column(DECIMAL(18, 8), nullable=False)
    exit_price = Column(DECIMAL(18, 8))
    size = Column(DECIMAL(18, 8), nullable=False)  # Number of shares
    stake = Column(DECIMAL(18, 8), nullable=False)  # USD invested
    
    # Calculated Fields
    potential_payout = Column(DECIMAL(18, 8))
    potential_multiplier = Column(Float)
    realized_pnl = Column(DECIMAL(18, 8), default=0)
    
    # Status
    status = Column(Enum(TradeStatus), default=TradeStatus.SIGNAL, index=True)
    paper_mode = Column(Boolean, default=True, index=True)
    
    # Market Snapshot at Entry (CRITICAL for ML retraining)
    snapshot_data = Column(JSONB, default={})
    """
    Expected snapshot_data structure:
    {
        "timestamp": "2026-01-02T10:30:00Z",
        "best_bid": 0.023,
        "best_ask": 0.025,
        "mid_price": 0.024,
        "spread_bps": 80,
        "bid_depth_10pct": 5000,
        "ask_depth_10pct": 3000,
        "volume_24h": 150000,
        "volume_1h": 5000,
        "price_change_1h": -0.05,
        "price_change_24h": -0.12,
        "orderbook_imbalance": 0.25,
        "time_to_expiry_hours": 18.5,
        "competitor_prices": {
            "predictbase": {"yes": 0.03, "no": 0.95}
        }
    }
    """
    
    # Signal Metadata (why the strategy triggered)
    signal_data = Column(JSONB, default={})
    """
    Expected signal_data structure:
    {
        "trigger_reason": "price_drop_15pct",
        "confidence_score": 0.85,
        "ml_features": {...},
        "arb_spread": 0.05,
        "expected_value": 1.25
    }
    """
    
    # Execution Details
    order_id = Column(String(100))
    execution_price = Column(DECIMAL(18, 8))
    slippage_bps = Column(Float)
    fees_paid = Column(DECIMAL(18, 8), default=0)
    
    # Timestamps
    signal_at = Column(DateTime, default=datetime.utcnow)
    entered_at = Column(DateTime)
    exited_at = Column(DateTime)
    resolved_at = Column(DateTime)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="trades")
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_trades_strategy_status', 'strategy_id', 'status'),
        Index('idx_trades_condition_strategy', 'condition_id', 'strategy_id'),
        Index('idx_trades_paper_status', 'paper_mode', 'status'),
        Index('idx_trades_signal_at', 'signal_at'),
    )
    
    def __repr__(self):
        return f"<Trade {self.trade_id} [{self.strategy_id}] {self.outcome.value}@{self.entry_price}>"
    
    @property
    def is_resolved(self) -> bool:
        return self.status in (TradeStatus.RESOLVED_WIN, TradeStatus.RESOLVED_LOSS)
    
    @property
    def is_winner(self) -> bool:
        return self.status == TradeStatus.RESOLVED_WIN

# =============================================================================
# MARKET SNAPSHOT (TIME-SERIES)
# =============================================================================

class MarketSnapshot(Base):
    """
    Point-in-time market state for historical analysis.
    High-frequency data - consider TimescaleDB hypertable.
    """
    __tablename__ = "market_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Market Identity
    condition_id = Column(String(100), nullable=False, index=True)
    
    # Timestamp (indexed for time-series queries)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Price Data
    yes_price = Column(DECIMAL(18, 8))
    no_price = Column(DECIMAL(18, 8))
    best_bid = Column(DECIMAL(18, 8))
    best_ask = Column(DECIMAL(18, 8))
    spread_bps = Column(Float)
    
    # Volume
    volume_24h = Column(DECIMAL(18, 2))
    volume_1h = Column(DECIMAL(18, 2))
    
    # Orderbook Depth
    bid_depth = Column(JSONB)  # {"0.01": 1000, "0.02": 2000, ...}
    ask_depth = Column(JSONB)
    
    # Cross-Exchange (if available)
    competitor_data = Column(JSONB)  # {"predictbase": {"yes": 0.03, ...}}
    
    __table_args__ = (
        Index('idx_snapshots_condition_time', 'condition_id', 'timestamp'),
    )

# =============================================================================
# STRATEGY PERFORMANCE (AGGREGATED)
# =============================================================================

class StrategyPerformance(Base):
    """
    Aggregated performance metrics per strategy per day.
    For dashboards and strategy comparison.
    """
    __tablename__ = "strategy_performance"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identity
    strategy_id = Column(String(50), ForeignKey("strategies.strategy_id"), nullable=False)
    date = Column(DateTime, nullable=False)
    
    # Trade Counts
    total_signals = Column(Integer, default=0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    # Financial
    total_invested = Column(DECIMAL(18, 2), default=0)
    total_pnl = Column(DECIMAL(18, 2), default=0)
    max_drawdown = Column(DECIMAL(18, 2), default=0)
    
    # Ratios
    win_rate = Column(Float)
    avg_return = Column(Float)
    sharpe_ratio = Column(Float)
    
    # Metadata
    paper_mode = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint('strategy_id', 'date', 'paper_mode', name='uq_strategy_date'),
        Index('idx_perf_strategy_date', 'strategy_id', 'date'),
    )

# =============================================================================
# CROSS-EXCHANGE MARKET MAPPING
# =============================================================================

class MarketMapping(Base):
    """
    Maps markets across exchanges for arbitrage detection.
    Polymarket <-> PredictBase matching.
    """
    __tablename__ = "market_mappings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Polymarket
    poly_condition_id = Column(String(100), nullable=False, unique=True, index=True)
    poly_question = Column(Text)
    poly_slug = Column(String(255))
    
    # PredictBase
    pb_market_id = Column(String(100))
    pb_question = Column(Text)
    pb_url = Column(String(500))
    
    # Matching Metadata
    match_score = Column(Float)  # Fuzzy matching score (0-100)
    match_method = Column(String(50))  # "fuzzy", "exact", "manual"
    is_verified = Column(Boolean, default=False)
    
    # State
    is_active = Column(Boolean, default=True)
    last_checked = Column(DateTime, default=datetime.utcnow)
    
    created_at = Column(DateTime, default=datetime.utcnow)

# =============================================================================
# INITIALIZATION
# =============================================================================

def init_database():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")
    
    # Create default strategies
    db = SessionLocal()
    try:
        default_strategies = [
            Strategy(
                strategy_id="ARB_PREDICTBASE_V1",
                name="Cross-Exchange Arbitrage (Polymarket vs PredictBase)",
                strategy_type=StrategyType.ARBITRAGE,
                parameters={
                    "min_spread_pct": 3.0,
                    "max_spread_pct": 15.0,
                    "min_liquidity": 1000,
                    "fuzzy_match_threshold": 90
                }
            ),
            Strategy(
                strategy_id="SNIPER_MICRO_V1",
                name="Microstructure Sniper (Price Drop Detector)",
                strategy_type=StrategyType.SNIPER,
                parameters={
                    "price_drop_threshold": 0.15,
                    "volume_spike_multiplier": 2.0,
                    "lookback_minutes": 10,
                    "max_expiry_hours": 24,
                    "min_volume_24h": 10000
                }
            ),
            Strategy(
                strategy_id="TAIL_BETTING_V1",
                name="Tail Betting (Low Price High Multiplier)",
                strategy_type=StrategyType.TAIL,
                parameters={
                    "max_price": 0.04,
                    "min_price": 0.001,
                    "min_multiplier": 25,
                    "stake_size": 2.0,
                    "min_ml_score": 0.55
                }
            ),
        ]
        
        for strat in default_strategies:
            existing = db.query(Strategy).filter_by(strategy_id=strat.strategy_id).first()
            if not existing:
                db.add(strat)
                print(f"   ➕ Added strategy: {strat.strategy_id}")
        
        db.commit()
    finally:
        db.close()

def get_session():
    """Get a new database session."""
    return SessionLocal()

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def record_trade(
    strategy_id: str,
    condition_id: str,
    outcome: str,
    entry_price: float,
    stake: float,
    snapshot_data: dict = None,
    signal_data: dict = None,
    paper_mode: bool = True,
    **kwargs
) -> Trade:
    """
    Record a new trade signal/execution.
    
    Args:
        strategy_id: Strategy that generated the signal
        condition_id: Polymarket condition ID
        outcome: "YES" or "NO"
        entry_price: Entry price
        stake: USD amount invested
        snapshot_data: Market state at entry
        signal_data: Why the signal was generated
        paper_mode: Whether this is paper trading
    
    Returns:
        Created Trade object
    """
    import uuid
    
    db = SessionLocal()
    try:
        trade = Trade(
            trade_id=f"{strategy_id}-{int(datetime.utcnow().timestamp())}-{uuid.uuid4().hex[:8]}",
            strategy_id=strategy_id,
            condition_id=condition_id,
            token_id=kwargs.get('token_id'),
            market_slug=kwargs.get('market_slug'),
            question=kwargs.get('question'),
            side=Side.BUY,
            outcome=Outcome.YES if outcome.upper() == "YES" else Outcome.NO,
            entry_price=Decimal(str(entry_price)),
            size=Decimal(str(stake / entry_price)),
            stake=Decimal(str(stake)),
            potential_payout=Decimal(str(stake / entry_price)),
            potential_multiplier=1 / entry_price,
            status=TradeStatus.SIGNAL if paper_mode else TradeStatus.PENDING,
            paper_mode=paper_mode,
            snapshot_data=snapshot_data or {},
            signal_data=signal_data or {},
        )
        
        db.add(trade)
        db.commit()
        db.refresh(trade)
        
        return trade
    finally:
        db.close()

def get_strategy_stats(strategy_id: str = None, paper_mode: bool = True) -> dict:
    """Get aggregated stats for a strategy or all strategies."""
    db = SessionLocal()
    try:
        query = db.query(Trade).filter(Trade.paper_mode == paper_mode)
        
        if strategy_id:
            query = query.filter(Trade.strategy_id == strategy_id)
        
        trades = query.all()
        
        if not trades:
            return {"total": 0, "pending": 0, "won": 0, "lost": 0, "invested": 0, "pnl": 0}
        
        pending = [t for t in trades if t.status == TradeStatus.SIGNAL]
        won = [t for t in trades if t.status == TradeStatus.RESOLVED_WIN]
        lost = [t for t in trades if t.status == TradeStatus.RESOLVED_LOSS]
        
        return {
            "total": len(trades),
            "pending": len(pending),
            "won": len(won),
            "lost": len(lost),
            "invested": float(sum(t.stake for t in trades)),
            "pnl": float(sum(t.realized_pnl or 0 for t in trades)),
            "win_rate": len(won) / max(1, len(won) + len(lost)) * 100,
            "avg_multiplier": sum(t.potential_multiplier or 0 for t in trades) / max(1, len(trades))
        }
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    if "--init" in sys.argv:
        init_database()
    else:
        print("Use --init to create tables")
