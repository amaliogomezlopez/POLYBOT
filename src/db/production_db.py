"""
🗄️ PRODUCTION DATABASE MODELS - POSTGRESQL + TIMESCALEDB
=========================================================
Optimized for high-frequency trading data with:
- Hypertables for time-series data (prices, trades)
- Proper indexing for fast queries
- Compression for historical data
- JSONB for flexible metadata storage
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, Index, Enum, DECIMAL, JSON,
    BigInteger, UniqueConstraint, CheckConstraint, func, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.pool import QueuePool
import enum
import uuid

# =============================================================================
# CONFIGURATION
# =============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://polybot:PolyBot2026Trading!@localhost:5432/polymarket"
)

# Production-optimized connection pool
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# =============================================================================
# ENUMS
# =============================================================================

class BetStatus(enum.Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class BetType(enum.Enum):
    TAIL = "tail"
    ARBITRAGE = "arbitrage"
    DIRECTIONAL = "directional"

class OrderSide(enum.Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(enum.Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

# =============================================================================
# CORE MODELS
# =============================================================================

class Market(Base):
    """
    Polymarket market/event information.
    Stores market metadata and resolution status.
    """
    __tablename__ = "markets"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    condition_id = Column(String(100), unique=True, nullable=False)
    question = Column(Text, nullable=False)
    description = Column(Text)
    market_slug = Column(String(255))
    
    # Categorization
    category = Column(String(100))
    subcategory = Column(String(100))
    tags = Column(JSONB, default=[])
    
    # Market parameters
    min_tick_size = Column(DECIMAL(18, 8), default=0.001)
    min_order_size = Column(DECIMAL(18, 8), default=1.0)
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    is_closed = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, index=True)
    resolved_at = Column(DateTime)
    
    # Resolution
    resolution = Column(String(10))  # "Yes", "No", null
    resolution_source = Column(String(255))
    
    # Volume & Liquidity
    total_volume = Column(DECIMAL(18, 2), default=0)
    open_interest = Column(DECIMAL(18, 2), default=0)
    
    # Metadata
    metadata = Column(JSONB, default={})
    
    # Relationships
    positions = relationship("Position", back_populates="market", lazy="dynamic")
    orders = relationship("Order", back_populates="market", lazy="dynamic")
    
    __table_args__ = (
        Index('ix_markets_category_active', 'category', 'is_active'),
        Index('ix_markets_end_date_active', 'end_date', 'is_active'),
        Index('ix_markets_condition_id_hash', 'condition_id', postgresql_using='hash'),
    )


class Position(Base):
    """
    Trading positions (bets placed).
    Core table for tracking all bets.
    """
    __tablename__ = "positions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    position_id = Column(String(50), unique=True, nullable=False, default=lambda: f"POS-{uuid.uuid4().hex[:12]}")
    
    # Market reference
    market_id = Column(BigInteger, ForeignKey("markets.id", ondelete="CASCADE"))
    condition_id = Column(String(100), nullable=False)
    token_id = Column(String(100))
    
    # Position details
    side = Column(String(10), default="Yes", nullable=False)  # "Yes" or "No"
    bet_type = Column(Enum(BetType), default=BetType.TAIL)
    
    # Sizing (using DECIMAL for precision)
    entry_price = Column(DECIMAL(18, 8), nullable=False)
    size = Column(DECIMAL(18, 8), nullable=False)  # Number of shares/tokens
    stake = Column(DECIMAL(18, 8), nullable=False)  # USDC invested
    
    # Target/Risk
    target_price = Column(DECIMAL(18, 8))
    stop_loss = Column(DECIMAL(18, 8))
    potential_multiplier = Column(Float)
    
    # ML Scoring
    ml_score = Column(Float)
    ml_features = Column(JSONB, default={})
    
    # Status
    status = Column(Enum(BetStatus), default=BetStatus.PENDING, index=True)
    is_paper = Column(Boolean, default=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime)
    
    # Results
    exit_price = Column(DECIMAL(18, 8))
    payout = Column(DECIMAL(18, 8), default=0)
    profit = Column(DECIMAL(18, 8), default=0)
    roi_percent = Column(Float, default=0)
    
    # Transaction info
    entry_tx_hash = Column(String(100))
    exit_tx_hash = Column(String(100))
    
    # Fees
    entry_fee = Column(DECIMAL(18, 8), default=0)
    exit_fee = Column(DECIMAL(18, 8), default=0)
    
    # Metadata
    notes = Column(Text)
    metadata = Column(JSONB, default={})
    
    # Relationships
    market = relationship("Market", back_populates="positions")
    orders = relationship("Order", back_populates="position", lazy="dynamic")
    
    __table_args__ = (
        Index('ix_positions_status_created', 'status', 'created_at'),
        Index('ix_positions_market_status', 'market_id', 'status'),
        Index('ix_positions_condition_id', 'condition_id'),
        Index('ix_positions_is_paper_status', 'is_paper', 'status'),
    )


class Order(Base):
    """
    Individual orders executed.
    Tracks all order executions for audit trail.
    """
    __tablename__ = "orders"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(String(100), unique=True, nullable=False)
    
    # References
    market_id = Column(BigInteger, ForeignKey("markets.id", ondelete="CASCADE"))
    position_id = Column(BigInteger, ForeignKey("positions.id", ondelete="SET NULL"))
    condition_id = Column(String(100), nullable=False)
    token_id = Column(String(100))
    
    # Order details
    side = Column(Enum(OrderSide), nullable=False)
    order_type = Column(String(20), default="MARKET")  # MARKET, LIMIT, IOC
    
    # Pricing
    price = Column(DECIMAL(18, 8), nullable=False)
    size = Column(DECIMAL(18, 8), nullable=False)
    filled_size = Column(DECIMAL(18, 8), default=0)
    
    # Status
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, index=True)
    is_paper = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    filled_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    
    # Execution details
    avg_fill_price = Column(DECIMAL(18, 8))
    fee = Column(DECIMAL(18, 8), default=0)
    slippage = Column(DECIMAL(18, 8), default=0)
    
    # Transaction
    tx_hash = Column(String(100))
    block_number = Column(BigInteger)
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Metadata
    metadata = Column(JSONB, default={})
    
    # Relationships
    market = relationship("Market", back_populates="orders")
    position = relationship("Position", back_populates="orders")
    
    __table_args__ = (
        Index('ix_orders_status_created', 'status', 'created_at'),
        Index('ix_orders_condition_created', 'condition_id', 'created_at'),
    )


class PriceSnapshot(Base):
    """
    Time-series price data.
    Optimized for TimescaleDB hypertable.
    """
    __tablename__ = "price_snapshots"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    condition_id = Column(String(100), nullable=False)
    
    # Prices
    yes_price = Column(DECIMAL(18, 8))
    no_price = Column(DECIMAL(18, 8))
    spread = Column(DECIMAL(18, 8))
    
    # Order book snapshot
    yes_bid = Column(DECIMAL(18, 8))
    yes_ask = Column(DECIMAL(18, 8))
    no_bid = Column(DECIMAL(18, 8))
    no_ask = Column(DECIMAL(18, 8))
    
    # Volume
    volume_24h = Column(DECIMAL(18, 2))
    
    # Source
    source = Column(String(50), default="clob")
    
    __table_args__ = (
        Index('ix_price_time_condition', 'timestamp', 'condition_id'),
    )


class TradingSession(Base):
    """
    Trading session aggregates.
    Daily/hourly performance summary.
    """
    __tablename__ = "trading_sessions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(50), unique=True, nullable=False)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    ended_at = Column(DateTime)
    duration_minutes = Column(Integer)
    
    # Statistics
    positions_opened = Column(Integer, default=0)
    positions_closed = Column(Integer, default=0)
    positions_won = Column(Integer, default=0)
    positions_lost = Column(Integer, default=0)
    
    # Financial
    total_invested = Column(DECIMAL(18, 8), default=0)
    total_payout = Column(DECIMAL(18, 8), default=0)
    total_profit = Column(DECIMAL(18, 8), default=0)
    total_fees = Column(DECIMAL(18, 8), default=0)
    
    # Performance metrics
    win_rate = Column(Float, default=0)
    avg_roi = Column(Float, default=0)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)
    
    # Mode
    is_paper = Column(Boolean, default=True)
    
    # Metadata
    config_snapshot = Column(JSONB, default={})


class MLModel(Base):
    """
    ML model versions and performance.
    Track model iterations.
    """
    __tablename__ = "ml_models"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_id = Column(String(50), unique=True, nullable=False)
    model_type = Column(String(50), default="xgboost")  # xgboost, lightgbm, etc.
    
    # Version
    version = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=False, index=True)
    
    # Training info
    trained_at = Column(DateTime, default=datetime.utcnow)
    training_samples = Column(Integer)
    training_duration_seconds = Column(Integer)
    
    # Features
    features = Column(JSONB, default=[])
    hyperparameters = Column(JSONB, default={})
    
    # Performance metrics
    accuracy = Column(Float)
    precision = Column(Float)
    recall = Column(Float)
    f1_score = Column(Float)
    auc_roc = Column(Float)
    
    # Live performance
    live_predictions = Column(Integer, default=0)
    live_correct = Column(Integer, default=0)
    live_accuracy = Column(Float)
    
    # Model storage
    model_path = Column(String(255))
    model_size_bytes = Column(BigInteger)


class MLTrainingData(Base):
    """
    Training data for ML models.
    Historical labeled data.
    """
    __tablename__ = "ml_training_data"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    position_id = Column(String(50), ForeignKey("positions.position_id"))
    
    # Features
    features = Column(JSONB, nullable=False)
    
    # Core features (denormalized for quick access)
    category = Column(String(100))
    entry_price = Column(Float)
    multiplier = Column(Float)
    ml_score = Column(Float)
    question_length = Column(Integer)
    
    # Target
    outcome = Column(Integer)  # 1 = won, 0 = lost
    profit = Column(Float)
    hold_duration_hours = Column(Float)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    model_version = Column(String(20))


class SystemLog(Base):
    """
    System activity and error logs.
    """
    __tablename__ = "system_logs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    level = Column(String(10), default="INFO", index=True)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    component = Column(String(50), index=True)  # scanner, trader, monitor, ml
    
    message = Column(Text, nullable=False)
    details = Column(JSONB, default={})
    
    # Error tracking
    error_type = Column(String(100))
    stack_trace = Column(Text)
    
    # Context
    position_id = Column(String(50))
    market_id = Column(String(100))


class AlertLog(Base):
    """
    Alert and notification logs.
    """
    __tablename__ = "alert_logs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    alert_type = Column(String(50), nullable=False)  # trade, error, performance, threshold
    severity = Column(String(20), default="info")  # info, warning, critical
    
    title = Column(String(255), nullable=False)
    message = Column(Text)
    
    # Delivery
    channel = Column(String(50))  # telegram, email, webhook
    delivered = Column(Boolean, default=False)
    delivered_at = Column(DateTime)
    
    # Reference
    reference_type = Column(String(50))
    reference_id = Column(String(100))


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def create_tables():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")

def create_indexes():
    """Create additional performance indexes."""
    with engine.connect() as conn:
        # Additional indexes for common queries
        indexes = [
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_positions_profit ON positions (profit) WHERE status = 'won'",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_markets_volume ON markets (total_volume DESC) WHERE is_active = true",
        ]
        for idx in indexes:
            try:
                conn.execute(text(idx))
                conn.commit()
            except Exception as e:
                print(f"Index warning: {e}")
    print("✅ Performance indexes created")

def setup_timescaledb():
    """Setup TimescaleDB hypertables for time-series data."""
    with engine.connect() as conn:
        try:
            # Check if TimescaleDB is available
            result = conn.execute(text("SELECT installed_version FROM pg_available_extensions WHERE name = 'timescaledb'"))
            row = result.fetchone()
            
            if row:
                # Enable extension
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
                conn.commit()
                
                # Convert price_snapshots to hypertable
                conn.execute(text("""
                    SELECT create_hypertable('price_snapshots', 'timestamp', 
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    )
                """))
                conn.commit()
                
                # Enable compression
                conn.execute(text("""
                    ALTER TABLE price_snapshots SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'condition_id'
                    )
                """))
                conn.commit()
                
                # Add compression policy (compress data older than 7 days)
                conn.execute(text("""
                    SELECT add_compression_policy('price_snapshots', INTERVAL '7 days', if_not_exists => TRUE)
                """))
                conn.commit()
                
                print("✅ TimescaleDB hypertables configured")
            else:
                print("⚠️ TimescaleDB not installed, using standard PostgreSQL")
                
        except Exception as e:
            print(f"⚠️ TimescaleDB setup skipped: {e}")

def get_session():
    """Get database session."""
    return SessionLocal()

def init_database():
    """Full database initialization."""
    print("🗄️ Initializing database...")
    create_tables()
    create_indexes()
    setup_timescaledb()
    print("✅ Database initialization complete")

# =============================================================================
# DATA MIGRATION FROM JSON
# =============================================================================

def migrate_from_json(bets_file: str = "data/tail_bot/bets.json"):
    """Migrate existing JSON bets to PostgreSQL."""
    bets_path = Path(bets_file)
    if not bets_path.exists():
        print("⚠️ No bets.json file found")
        return 0
    
    bets_data = json.loads(bets_path.read_text())
    session = get_session()
    migrated = 0
    
    try:
        for bet_data in bets_data:
            condition_id = bet_data.get('condition_id')
            
            # Get or create market
            market = session.query(Market).filter_by(condition_id=condition_id).first()
            if not market:
                market = Market(
                    condition_id=condition_id,
                    question=bet_data.get('question', ''),
                )
                session.add(market)
                session.flush()
            
            # Check if position already exists
            position_id = bet_data.get('id', f"MIGRATED-{migrated}")
            existing = session.query(Position).filter_by(position_id=position_id).first()
            if existing:
                continue
            
            # Map status
            status_str = bet_data.get('status', 'pending')
            status_map = {
                'pending': BetStatus.PENDING,
                'won': BetStatus.WON,
                'lost': BetStatus.LOST
            }
            status = status_map.get(status_str, BetStatus.PENDING)
            
            # Get entry price
            entry_price = bet_data.get('entry_price') or bet_data.get('price', 0.02)
            
            # Create position
            position = Position(
                position_id=position_id,
                market_id=market.id,
                condition_id=condition_id,
                token_id=bet_data.get('token_id'),
                side="Yes",
                bet_type=BetType.TAIL,
                entry_price=Decimal(str(entry_price)),
                size=Decimal(str(bet_data.get('size', 2 / entry_price if entry_price > 0 else 100))),
                stake=Decimal(str(bet_data.get('stake', 2.0))),
                potential_multiplier=bet_data.get('potential_multiplier') or (1/entry_price if entry_price > 0 else 50),
                ml_score=bet_data.get('ml_score'),
                status=status,
                is_paper=True,
                created_at=datetime.fromtimestamp(bet_data.get('timestamp', datetime.now().timestamp())),
                payout=Decimal(str(bet_data.get('payout', 0))),
                profit=Decimal(str(bet_data.get('profit', 0))),
            )
            
            if bet_data.get('resolved_at'):
                try:
                    position.resolved_at = datetime.fromisoformat(bet_data['resolved_at'])
                except:
                    pass
            
            session.add(position)
            migrated += 1
        
        session.commit()
        print(f"✅ Migrated {migrated} positions to database")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Migration error: {e}")
        raise
    finally:
        session.close()
    
    return migrated

# =============================================================================
# STATISTICS QUERIES
# =============================================================================

def get_portfolio_stats(session=None) -> Dict[str, Any]:
    """Get current portfolio statistics."""
    close_session = session is None
    if session is None:
        session = get_session()
    
    try:
        stats = {
            'total_positions': session.query(Position).count(),
            'pending_positions': session.query(Position).filter(Position.status == BetStatus.PENDING).count(),
            'won_positions': session.query(Position).filter(Position.status == BetStatus.WON).count(),
            'lost_positions': session.query(Position).filter(Position.status == BetStatus.LOST).count(),
            'total_invested': float(session.query(func.sum(Position.stake)).filter(Position.status == BetStatus.PENDING).scalar() or 0),
            'total_profit': float(session.query(func.sum(Position.profit)).scalar() or 0),
            'total_payout': float(session.query(func.sum(Position.payout)).filter(Position.status == BetStatus.WON).scalar() or 0),
        }
        
        resolved = stats['won_positions'] + stats['lost_positions']
        stats['hit_rate'] = (stats['won_positions'] / resolved * 100) if resolved > 0 else 0
        stats['resolved_count'] = resolved
        
        return stats
    finally:
        if close_session:
            session.close()

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Management")
    parser.add_argument("--init", action="store_true", help="Initialize database")
    parser.add_argument("--migrate", action="store_true", help="Migrate from JSON")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    
    args = parser.parse_args()
    
    if args.init:
        init_database()
    
    if args.migrate:
        migrate_from_json()
    
    if args.stats:
        stats = get_portfolio_stats()
        print("\n📊 Portfolio Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    if not any([args.init, args.migrate, args.stats]):
        print("Usage:")
        print("  python production_db.py --init      # Create tables")
        print("  python production_db.py --migrate   # Migrate from JSON")
        print("  python production_db.py --stats     # Show statistics")
