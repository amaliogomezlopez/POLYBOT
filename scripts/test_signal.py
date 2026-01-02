#!/usr/bin/env python3
"""
🧪 TEST SIGNAL INJECTION
=========================
Inyecta un trade fake y un near-miss en la base de datos y logs
para verificar que el pipeline del dashboard funciona correctamente.

Uso (en VPS):
    cd /root/polybot
    python scripts/test_signal.py

Esto debería aparecer instantáneamente en:
    - Dashboard: Trade en "Recent Trades"
    - Dashboard: Near Miss en "Near Misses" panel
    - Dashboard: Stats actualizados
"""

import os
import sys
import uuid
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Configure logging to write to the same log file as the daemon
# Use the correct production path
LOG_DIR = Path("/opt/polymarket-bot/logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "multi_strategy.log"

# Setup logger that writes to the daemon's log file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,%(msecs)03d | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test_signal")

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://polybot:PolyBot2026Trading!@localhost:5432/polymarket"
)

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.db.multi_strategy_models import (
        Base, Trade, TradeStatus, Side, Outcome, Strategy
    )
    
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    DB_AVAILABLE = True
except ImportError as e:
    logger.error(f"SQLAlchemy import error: {e}")
    DB_AVAILABLE = False
except Exception as e:
    logger.error(f"Database connection error: {e}")
    DB_AVAILABLE = False

# =============================================================================
# TEST DATA
# =============================================================================

def generate_fake_trade_id():
    """Generate a unique trade ID."""
    timestamp = int(datetime.utcnow().timestamp())
    unique = uuid.uuid4().hex[:8]
    return f"SNIPER_MICRO_V1-TEST-{timestamp}-{unique}"

FAKE_TRADE = {
    "trade_id": generate_fake_trade_id(),
    "strategy_id": "SNIPER_MICRO_V1",
    "condition_id": "0x123456789abcdef_TEST",
    "token_id": "fake_token_12345",
    "market_slug": "test-fake-market-for-dashboard",
    "question": "🧪 TEST: Will this fake trade appear in the dashboard?",
    "side": Side.BUY,
    "outcome": Outcome.YES,
    "entry_price": Decimal("0.035"),
    "size": Decimal("100"),  # 100 shares
    "stake": Decimal("3.50"),  # $3.50 invested
    "potential_payout": Decimal("100.00"),  # If YES wins
    "potential_multiplier": 28.57,  # 100/3.5
    "realized_pnl": Decimal("0.00"),
    "status": TradeStatus.FILLED,  # FILLED = active/open
    "paper_mode": True,
    "snapshot_data": {
        "timestamp": datetime.utcnow().isoformat(),
        "test": True,
        "best_bid": 0.033,
        "best_ask": 0.037,
        "mid_price": 0.035,
        "spread_bps": 114,
        "volume_24h": 50000,
        "injected_by": "test_signal.py"
    },
    "signal_data": {
        "trigger_reason": "TEST_INJECTION",
        "confidence_score": 0.99,
        "note": "This is a fake trade for dashboard testing"
    },
    "signal_at": datetime.utcnow(),
    "entered_at": datetime.utcnow(),
}

# =============================================================================
# INJECT TRADE
# =============================================================================

def inject_fake_trade():
    """Inject a fake trade into the database."""
    if not DB_AVAILABLE:
        logger.error("❌ Database not available. Cannot inject trade.")
        return None
    
    db = SessionLocal()
    try:
        # First check if strategy exists
        strategy = db.query(Strategy).filter_by(strategy_id="SNIPER_MICRO_V1").first()
        if not strategy:
            logger.warning("⚠️ Strategy SNIPER_MICRO_V1 not found, creating...")
            from src.db.multi_strategy_models import StrategyType
            strategy = Strategy(
                strategy_id="SNIPER_MICRO_V1",
                name="Sniper Micro Strategy V1",
                strategy_type=StrategyType.SNIPER,
                is_active=True,
                paper_mode=True,
            )
            db.add(strategy)
            db.commit()
            logger.info("✅ Strategy created")
        
        # Create the fake trade
        trade = Trade(**FAKE_TRADE)
        
        db.add(trade)
        db.commit()
        db.refresh(trade)
        
        logger.info(f"✅ FAKE TRADE INJECTED: {trade.trade_id}")
        logger.info(f"   Strategy: {trade.strategy_id}")
        logger.info(f"   Question: {trade.question}")
        logger.info(f"   Entry: ${trade.entry_price} | Stake: ${trade.stake}")
        logger.info(f"   Status: {trade.status.value}")
        
        return trade
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to inject trade: {e}")
        return None
    finally:
        db.close()

# =============================================================================
# INJECT NEAR MISS LOG
# =============================================================================

def inject_near_miss_log():
    """
    Inject a fake near-miss log entry.
    The dashboard scans for 'Near miss' or 'NEAR_MISS' in log lines.
    """
    
    # Multiple near misses for different strategies
    near_misses = [
        # SNIPER near miss
        "🔍 NEAR_MISS | SNIPER | Market: test-btc-prediction "
        "| Drop: 13.5% (need 15%) | Volume: $42k (need $50k) "
        "| Score: 82% | Reason: Close to crash threshold",
        
        # TAIL near miss
        "🔍 NEAR_MISS | TAIL | Market: test-long-shot-event "
        "| Price: $0.052 (need <$0.04) | ML Score: 52% (need 55%) "
        "| Score: 78% | Reason: Almost triggered tail bet",
        
        # ARB near miss
        "🔍 NEAR_MISS | ARB | Market: test-arb-opportunity "
        "| Spread: 2.1% (need 3%) | PredictBase: 0.45 vs Poly: 0.43 "
        "| Score: 85% | Reason: Spread narrowing",
    ]
    
    for msg in near_misses:
        logger.info(msg)
    
    logger.info(f"✅ {len(near_misses)} NEAR MISS LOGS INJECTED")
    return len(near_misses)

# =============================================================================
# CLEANUP (Optional)
# =============================================================================

def cleanup_test_trades():
    """Remove test trades from database."""
    if not DB_AVAILABLE:
        return
    
    db = SessionLocal()
    try:
        # Delete trades with TEST in trade_id
        deleted = db.query(Trade).filter(
            Trade.trade_id.like("%TEST%")
        ).delete(synchronize_session=False)
        
        db.commit()
        logger.info(f"🧹 Cleaned up {deleted} test trades")
        return deleted
    except Exception as e:
        db.rollback()
        logger.error(f"Cleanup error: {e}")
        return 0
    finally:
        db.close()

# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main function."""
    print("\n" + "="*60)
    print("🧪 POLYBOT DASHBOARD TEST - SIGNAL INJECTION")
    print("="*60 + "\n")
    
    # Step 1: Inject fake trade
    print("📊 Step 1: Injecting fake trade into database...")
    trade = inject_fake_trade()
    
    if trade:
        print(f"   ✅ Trade ID: {trade.trade_id}")
    else:
        print("   ❌ Trade injection failed!")
    
    # Step 2: Inject near miss logs
    print("\n📝 Step 2: Injecting near-miss log entries...")
    count = inject_near_miss_log()
    print(f"   ✅ {count} near-miss entries written to {LOG_FILE}")
    
    # Summary
    print("\n" + "="*60)
    print("📺 NOW CHECK YOUR DASHBOARD:")
    print(f"   🌐 http://94.143.138.8")
    print(f"   👤 User: polybot")
    print(f"   🔑 Pass: Poly2026Dashboard!")
    print("="*60)
    print("\nYou should see:")
    print("  ✅ 1 new trade in 'RECENT TRADES' table")
    print("  ✅ SNIPER card showing 1 Trade, +$0.00 PnL")
    print("  ✅ 3 near misses in 'NEAR MISSES' panel")
    print("\n💡 To cleanup test data, run:")
    print("   python scripts/test_signal.py --cleanup")
    print()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        print("🧹 Cleaning up test trades...")
        cleanup_test_trades()
    else:
        main()
