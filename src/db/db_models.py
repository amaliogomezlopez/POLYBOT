"""
🗄️ DATABASE MODELS FOR POLYMARKET BOT
======================================
SQLAlchemy models for robust data persistence.
Supports SQLite (local) and PostgreSQL (production).
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, 
    DateTime, Text, ForeignKey, Index, Enum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum
import os

# =============================================================================
# CONFIGURATION
# =============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./data/polymarket_bot.db"
)

# Handle PostgreSQL URL format from some providers
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, echo=False)
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

class BetType(enum.Enum):
    TAIL = "tail"          # Low probability, high reward
    ARBITRAGE = "arbitrage"  # Delta-neutral
    DIRECTIONAL = "directional"

# =============================================================================
# MODELS
# =============================================================================

class Market(Base):
    """
    Polymarket market information.
    """
    __tablename__ = "markets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    condition_id = Column(String(100), unique=True, nullable=False, index=True)
    question = Column(Text, nullable=False)
    market_slug = Column(String(200))
    category = Column(String(50))
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime)
    resolved_at = Column(DateTime)
    resolution = Column(String(10))  # "Yes", "No", or null
    
    # Relationships
    bets = relationship("Bet", back_populates="market")
    price_history = relationship("PriceSnapshot", back_populates="market")
    
    def __repr__(self):
        return f"<Market {self.condition_id[:16]}... '{self.question[:30]}...'>"


class Bet(Base):
    """
    Individual bet/position record.
    """
    __tablename__ = "bets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bet_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Market reference
    market_id = Column(Integer, ForeignKey("markets.id"))
    condition_id = Column(String(100), nullable=False, index=True)
    token_id = Column(String(100))
    
    # Bet details
    bet_type = Column(Enum(BetType), default=BetType.TAIL)
    side = Column(String(10), default="Yes")  # "Yes" or "No"
    entry_price = Column(Float, nullable=False)
    stake = Column(Float, nullable=False)
    size = Column(Float)  # Number of tokens
    potential_multiplier = Column(Float)
    
    # ML scoring
    ml_score = Column(Float)
    category_score = Column(Float)
    
    # Status
    status = Column(Enum(BetStatus), default=BetStatus.PENDING, index=True)
    is_paper = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    
    # Results
    exit_price = Column(Float)
    payout = Column(Float, default=0)
    profit = Column(Float, default=0)
    
    # Transaction info (for real bets)
    tx_hash = Column(String(100))
    
    # Relationships
    market = relationship("Market", back_populates="bets")
    
    # Indexes
    __table_args__ = (
        Index('ix_bets_status_created', 'status', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Bet {self.bet_id} {self.side} @ ${self.entry_price:.4f} - {self.status.value}>"


class PriceSnapshot(Base):
    """
    Historical price data for markets.
    """
    __tablename__ = "price_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(Integer, ForeignKey("markets.id"))
    condition_id = Column(String(100), nullable=False, index=True)
    
    # Prices
    yes_price = Column(Float)
    no_price = Column(Float)
    
    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    market = relationship("Market", back_populates="price_history")
    
    def __repr__(self):
        return f"<PriceSnapshot {self.condition_id[:16]}... Yes=${self.yes_price:.4f}>"


class TradingSession(Base):
    """
    Trading session statistics.
    """
    __tablename__ = "trading_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), unique=True, nullable=False)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    
    # Statistics
    bets_placed = Column(Integer, default=0)
    bets_resolved = Column(Integer, default=0)
    bets_won = Column(Integer, default=0)
    bets_lost = Column(Integer, default=0)
    
    total_invested = Column(Float, default=0)
    total_payout = Column(Float, default=0)
    total_profit = Column(Float, default=0)
    
    # Mode
    is_paper = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<TradingSession {self.session_id} P&L=${self.total_profit:.2f}>"


class MLTrainingData(Base):
    """
    Training data for XGBoost model.
    """
    __tablename__ = "ml_training_data"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bet_id = Column(String(50), ForeignKey("bets.bet_id"))
    
    # Features
    question = Column(Text)
    category = Column(String(50))
    entry_price = Column(Float)
    multiplier = Column(Float)
    ml_score = Column(Float)
    
    # Additional features
    question_length = Column(Integer)
    has_date = Column(Boolean)
    has_number = Column(Boolean)
    market_age_days = Column(Integer)
    
    # Target
    outcome = Column(Integer)  # 1 = won, 0 = lost
    profit = Column(Float)
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<MLTrainingData outcome={self.outcome} profit=${self.profit:.2f}>"


class SystemLog(Base):
    """
    System activity logs.
    """
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(10), default="INFO")  # INFO, WARNING, ERROR
    component = Column(String(50))  # scanner, trader, monitor
    message = Column(Text)
    details = Column(Text)  # JSON string for additional data
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<SystemLog [{self.level}] {self.component}: {self.message[:30]}...>"


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def create_tables():
    """Create all tables in database."""
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully")

def get_session():
    """Get database session."""
    return SessionLocal()

def init_database():
    """Initialize database with tables."""
    create_tables()
    
    # Create initial session record
    session = get_session()
    try:
        existing = session.query(TradingSession).first()
        if not existing:
            initial_session = TradingSession(
                session_id=f"SESSION-{int(datetime.now().timestamp())}",
                is_paper=True
            )
            session.add(initial_session)
            session.commit()
            print("✅ Initial trading session created")
    finally:
        session.close()

# =============================================================================
# MIGRATION FROM JSON
# =============================================================================

def migrate_from_json(bets_file: str = "data/tail_bot/bets.json"):
    """
    Migrate existing JSON bets to database.
    """
    import json
    from pathlib import Path
    
    bets_path = Path(bets_file)
    if not bets_path.exists():
        print("⚠️ No bets.json file found")
        return
    
    bets_data = json.loads(bets_path.read_text())
    session = get_session()
    
    migrated = 0
    skipped = 0
    
    try:
        for bet_data in bets_data:
            bet_id = bet_data.get('id', f"MIGRATED-{migrated}")
            
            # Check if already exists
            existing = session.query(Bet).filter_by(bet_id=bet_id).first()
            if existing:
                skipped += 1
                continue
            
            # Create market if not exists
            condition_id = bet_data.get('condition_id')
            market = session.query(Market).filter_by(condition_id=condition_id).first()
            if not market:
                market = Market(
                    condition_id=condition_id,
                    question=bet_data.get('question', ''),
                )
                session.add(market)
                session.flush()
            
            # Determine status
            status_str = bet_data.get('status', 'pending')
            status = BetStatus.PENDING
            if status_str == 'won':
                status = BetStatus.WON
            elif status_str == 'lost':
                status = BetStatus.LOST
            
            # Create bet record
            entry_price = bet_data.get('entry_price') or bet_data.get('price', 0.02)
            bet = Bet(
                bet_id=bet_id,
                market_id=market.id,
                condition_id=condition_id,
                token_id=bet_data.get('token_id'),
                bet_type=BetType.TAIL,
                side="Yes",
                entry_price=entry_price,
                stake=bet_data.get('stake', 2.0),
                size=bet_data.get('size'),
                potential_multiplier=bet_data.get('potential_multiplier') or (1/entry_price if entry_price > 0 else 50),
                ml_score=bet_data.get('ml_score'),
                status=status,
                is_paper=True,
                created_at=datetime.fromtimestamp(bet_data.get('timestamp', datetime.now().timestamp())),
                payout=bet_data.get('payout', 0),
                profit=bet_data.get('profit', 0),
            )
            
            if bet_data.get('resolved_at'):
                bet.resolved_at = datetime.fromisoformat(bet_data['resolved_at'])
            
            session.add(bet)
            migrated += 1
        
        session.commit()
        print(f"✅ Migrated {migrated} bets to database ({skipped} skipped)")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        session.close()

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Management")
    parser.add_argument("--init", action="store_true", help="Initialize database")
    parser.add_argument("--migrate", action="store_true", help="Migrate from JSON")
    
    args = parser.parse_args()
    
    if args.init:
        init_database()
    
    if args.migrate:
        migrate_from_json()
    
    if not args.init and not args.migrate:
        print("Usage:")
        print("  python db_models.py --init      # Create tables")
        print("  python db_models.py --migrate   # Migrate from JSON")
