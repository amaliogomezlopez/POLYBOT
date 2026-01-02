"""
🧠 MULTI-STRATEGY DAEMON
=========================
Central orchestrator that runs all strategies in parallel.

Architecture:
1. Single MarketScanner feeds data to all strategies
2. Strategies evaluate independently (async)
3. Signals are recorded immediately to SQL
4. JSON backup maintained for debugging

Features:
- Async-first design for maximum throughput
- Low memory footprint (512MB VPS compatible)
- Automatic strategy registration
- Real-time signal recording
- Performance tracking per strategy

Usage:
    python scripts/multi_strategy_daemon.py --daemon --interval 60
"""

import asyncio
import json
import httpx
import logging
import sys
import os
import signal
import gc
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from collections import deque
import argparse

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# LOGGING SETUP
# =============================================================================

Path('logs').mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/multi_strategy.log')
    ]
)
logger = logging.getLogger("orchestrator")

# Reduce noise from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# =============================================================================
# IMPORTS (with graceful fallbacks)
# =============================================================================

# Try database
try:
    from src.db.multi_strategy_models import (
        get_session, Trade, TradeStatus, Side, Outcome,
        record_trade, get_strategy_stats, init_database
    )
    DB_AVAILABLE = True
    logger.info("✅ Database available")
except Exception as e:
    DB_AVAILABLE = False
    logger.warning(f"⚠️ Database not available: {e}")

# Try strategies
try:
    from src.trading.strategies import (
        MarketData,
        TradeSignal,
        SignalType,
        strategy_registry,
        ArbitrageStrategy,
        SniperStrategy,
        TailStrategy
    )
    STRATEGIES_AVAILABLE = True
except Exception as e:
    STRATEGIES_AVAILABLE = False
    logger.error(f"❌ Strategies not available: {e}")

# Try PredictBase client
try:
    from src.exchanges.predictbase_client import PredictBaseClient
    PB_AVAILABLE = True
except Exception as e:
    PB_AVAILABLE = False
    logger.warning(f"⚠️ PredictBase client not available: {e}")

# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    # API
    POLYMARKET_API = "https://clob.polymarket.com"
    GAMMA_API = "https://gamma-api.polymarket.com"
    
    # Storage
    DATA_DIR = Path("data/multi_strategy")
    SIGNALS_FILE = DATA_DIR / "signals.json"
    STATS_FILE = DATA_DIR / "stats.json"
    
    # Performance
    MAX_MARKETS_PER_CYCLE = 200  # Limit to save RAM
    REQUEST_DELAY = 0.1  # seconds between API calls
    
    # Memory management
    GC_INTERVAL_CYCLES = 10  # Run GC every N cycles

# Ensure directories exist
Config.DATA_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# MARKET SCANNER
# =============================================================================

class MarketScanner:
    """
    Fetches market data from Polymarket APIs.
    Single source of truth for all strategies.
    """
    
    def __init__(self, pb_client: Optional[Any] = None):
        self.client: Optional[httpx.AsyncClient] = None
        self.pb_client = pb_client
        
        # Cache
        self._market_cache: Dict[str, dict] = {}
        self._cache_ttl = 60  # seconds
        self._last_cache_time = 0
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    async def get_active_markets(self, limit: int = 200) -> List[MarketData]:
        """
        Fetch active markets from Polymarket.
        
        Returns:
            List of MarketData objects ready for strategy processing
        """
        markets = []
        
        # Fetch from sampling endpoint (most active markets)
        cursors = ['LTE=', 'MA==', 'MjA=', 'NDA=', 'NjA=', 'ODA=', 'MTAw']
        seen_ids = set()
        
        for cursor in cursors:
            if len(markets) >= limit:
                break
            
            try:
                url = f"{Config.POLYMARKET_API}/sampling-markets"
                params = {"next_cursor": cursor}
                
                resp = await self.client.get(url, params=params)
                
                if resp.status_code != 200:
                    continue
                
                data = resp.json()
                
                for m in data.get("data", []):
                    cid = m.get("condition_id")
                    
                    if cid in seen_ids:
                        continue
                    seen_ids.add(cid)
                    
                    market_data = await self._parse_market(m)
                    if market_data:
                        markets.append(market_data)
                
                await asyncio.sleep(Config.REQUEST_DELAY)
                
            except Exception as e:
                logger.debug(f"Error fetching cursor {cursor}: {e}")
        
        logger.info(f"📥 Scanned {len(markets)} active markets")
        return markets[:limit]
    
    async def _parse_market(self, raw: dict) -> Optional[MarketData]:
        """Parse raw market data into MarketData object."""
        try:
            cid = raw.get("condition_id")
            question = raw.get("question", "")
            
            # Find YES token
            yes_price = 0.0
            no_price = 0.0
            token_id = None
            
            for token in raw.get("tokens", []):
                outcome = token.get("outcome", "").upper()
                price = float(token.get("price", 0))
                
                if outcome == "YES":
                    yes_price = price
                    token_id = token.get("token_id")
                elif outcome == "NO":
                    no_price = price
            
            if yes_price == 0:
                return None
            
            # Calculate derived fields
            mid_price = (yes_price + no_price) / 2 if no_price > 0 else yes_price
            spread_bps = abs(yes_price - (1 - no_price)) * 10000 if no_price > 0 else 0
            
            # Parse end date
            hours_to_expiry = None
            end_date = raw.get("end_date_iso")
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    hours_to_expiry = (end_dt - datetime.now(end_dt.tzinfo)).total_seconds() / 3600
                except:
                    pass
            
            # NOTE: competitor_prices se obtienen en ArbitrageStrategy, no aquí
            # Esto evita llamar a PredictBase para CADA mercado
            competitor_prices = {}
            
            return MarketData(
                condition_id=cid,
                question=question,
                token_id=token_id,
                market_slug=raw.get("market_slug"),
                yes_price=yes_price,
                no_price=no_price,
                best_bid=yes_price * 0.99,  # Estimate
                best_ask=yes_price * 1.01,  # Estimate
                mid_price=mid_price,
                spread_bps=spread_bps,
                volume_24h=float(raw.get("volume", 0)),
                hours_to_expiry=hours_to_expiry,
                competitor_prices=competitor_prices,
                raw_data=raw
            )
            
        except Exception as e:
            logger.debug(f"Error parsing market: {e}")
            return None

# =============================================================================
# SIGNAL RECORDER
# =============================================================================

class SignalRecorder:
    """
    Records signals to database and JSON backup.
    """
    
    def __init__(self):
        self._signals_today: List[dict] = []
        self._load_existing()
    
    def _load_existing(self):
        """Load existing signals from JSON."""
        if Config.SIGNALS_FILE.exists():
            try:
                self._signals_today = json.loads(Config.SIGNALS_FILE.read_text())
            except:
                self._signals_today = []
    
    def record(self, signal: TradeSignal) -> str:
        """
        Record a signal to database and JSON.
        
        Returns:
            Trade ID
        """
        trade_id = f"{signal.strategy_id}-{int(datetime.utcnow().timestamp())}"
        
        # Save to database
        if DB_AVAILABLE:
            try:
                trade = record_trade(
                    strategy_id=signal.strategy_id,
                    condition_id=signal.condition_id,
                    outcome=signal.outcome,
                    entry_price=signal.entry_price,
                    stake=signal.stake,
                    snapshot_data=signal.snapshot_data,
                    signal_data=signal.signal_data,
                    paper_mode=True,
                    token_id=signal.token_id,
                    question=signal.question
                )
                trade_id = trade.trade_id
            except Exception as e:
                logger.error(f"DB record error: {e}")
        
        # Save to JSON backup
        signal_dict = {
            "trade_id": trade_id,
            "strategy_id": signal.strategy_id,
            "timestamp": datetime.utcnow().isoformat(),
            "condition_id": signal.condition_id,
            "question": signal.question,
            "outcome": signal.outcome,
            "entry_price": signal.entry_price,
            "stake": signal.stake,
            "confidence": signal.confidence,
            "expected_value": signal.expected_value,
            "trigger_reason": signal.trigger_reason,
            "signal_data": signal.signal_data,
            "snapshot_data": signal.snapshot_data,
        }
        
        self._signals_today.append(signal_dict)
        self._save_json()
        
        return trade_id
    
    def _save_json(self):
        """Save signals to JSON file."""
        try:
            Config.SIGNALS_FILE.write_text(
                json.dumps(self._signals_today, indent=2, default=str)
            )
        except Exception as e:
            logger.error(f"JSON save error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get signal statistics."""
        stats = {
            "total_signals": len(self._signals_today),
            "by_strategy": {},
            "total_stake": 0,
        }
        
        for s in self._signals_today:
            sid = s.get("strategy_id", "unknown")
            if sid not in stats["by_strategy"]:
                stats["by_strategy"][sid] = {"count": 0, "stake": 0}
            
            stats["by_strategy"][sid]["count"] += 1
            stats["by_strategy"][sid]["stake"] += s.get("stake", 0)
            stats["total_stake"] += s.get("stake", 0)
        
        return stats

# =============================================================================
# ORCHESTRATOR
# =============================================================================

class MultiStrategyOrchestrator:
    """
    Main orchestrator that coordinates all components.
    
    Flow:
    1. Scanner fetches market data
    2. All strategies process in parallel
    3. Signals are recorded immediately
    4. Stats are updated
    """
    
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.scanner: Optional[MarketScanner] = None
        self.recorder = SignalRecorder()
        self.pb_client = None
        
        # Runtime state
        self._is_running = False
        self._cycle_count = 0
        self._start_time = None
        
        # Stats
        self.stats = {
            "cycles": 0,
            "markets_scanned": 0,
            "signals_generated": 0,
            "errors": 0,
        }
    
    async def __aenter__(self):
        # Initialize PredictBase client
        if PB_AVAILABLE:
            self.pb_client = PredictBaseClient()
            await self.pb_client.__aenter__()
        
        # Initialize scanner
        self.scanner = MarketScanner(pb_client=self.pb_client)
        await self.scanner.__aenter__()
        
        # Register strategies
        self._register_strategies()
        
        self._start_time = datetime.utcnow()
        return self
    
    async def __aexit__(self, *args):
        if self.scanner:
            await self.scanner.__aexit__(*args)
        if self.pb_client:
            await self.pb_client.__aexit__(*args)
    
    def _register_strategies(self):
        """Register all strategies."""
        if not STRATEGIES_AVAILABLE:
            logger.error("Strategies not available!")
            return
        
        # Clear existing
        strategy_registry._strategies.clear()
        
        # Register each strategy
        strategies = [
            ArbitrageStrategy(paper_mode=self.paper_mode, stake_size=10.0),
            SniperStrategy(paper_mode=self.paper_mode, stake_size=5.0),
            TailStrategy(paper_mode=self.paper_mode, stake_size=2.0),
        ]
        
        for s in strategies:
            strategy_registry.register(s)
            s._is_running = True
            logger.info(f"   📊 {s.strategy_id}: {s.get_config()}")
    
    async def run_cycle(self) -> Dict[str, Any]:
        """
        Run a single scanning and processing cycle.
        
        Returns:
            Cycle results with stats
        """
        self._cycle_count += 1
        cycle_start = datetime.utcnow()
        
        logger.info("=" * 60)
        logger.info(f"🔄 CYCLE {self._cycle_count} - {cycle_start.strftime('%H:%M:%S')}")
        logger.info("=" * 60)
        
        results = {
            "cycle": self._cycle_count,
            "markets_scanned": 0,
            "signals": [],
            "errors": [],
        }
        
        try:
            # 1. Fetch markets
            markets = await self.scanner.get_active_markets(limit=Config.MAX_MARKETS_PER_CYCLE)
            results["markets_scanned"] = len(markets)
            self.stats["markets_scanned"] += len(markets)
            
            # 2. Process each market through all strategies
            for market in markets:
                try:
                    signals = await strategy_registry.process_all(market)
                    
                    for signal in signals:
                        if signal and signal.signal_type == SignalType.BUY:
                            # Record signal
                            trade_id = self.recorder.record(signal)
                            
                            results["signals"].append({
                                "trade_id": trade_id,
                                "strategy": signal.strategy_id,
                                "question": signal.question[:50],
                                "price": signal.entry_price,
                                "stake": signal.stake,
                            })
                            
                            self.stats["signals_generated"] += 1
                            
                            logger.info(
                                f"✅ SIGNAL [{signal.strategy_id}] "
                                f"${signal.entry_price:.4f} | "
                                f"EV: ${signal.expected_value:+.2f} | "
                                f"{signal.question[:40]}..."
                            )
                    
                except Exception as e:
                    results["errors"].append(str(e))
                    logger.debug(f"Market processing error: {e}")
            
            # 3. Log cycle summary
            duration = (datetime.utcnow() - cycle_start).total_seconds()
            
            logger.info("-" * 40)
            logger.info(f"📊 Cycle Summary:")
            logger.info(f"   Markets: {results['markets_scanned']}")
            logger.info(f"   Signals: {len(results['signals'])}")
            logger.info(f"   Duration: {duration:.1f}s")
            
            # Strategy stats
            for sid, stats in strategy_registry.get_all_stats().items():
                logger.info(f"   {sid}: {stats['signals_generated']} signals, {stats['trades_today']} today")
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cycle error: {e}")
            results["errors"].append(str(e))
        
        # Memory management
        if self._cycle_count % Config.GC_INTERVAL_CYCLES == 0:
            gc.collect()
            logger.debug("🧹 Garbage collection completed")
        
        self.stats["cycles"] += 1
        return results
    
    async def run_daemon(self, interval_seconds: int = 60):
        """
        Run as daemon with specified interval.
        
        Args:
            interval_seconds: Seconds between cycles
        """
        self._is_running = True
        
        logger.info("=" * 60)
        logger.info("🚀 MULTI-STRATEGY DAEMON STARTING")
        logger.info("=" * 60)
        logger.info(f"   Paper Mode: {self.paper_mode}")
        logger.info(f"   Interval: {interval_seconds}s")
        logger.info(f"   Strategies: {len(strategy_registry.get_all())}")
        logger.info(f"   Database: {'✅' if DB_AVAILABLE else '❌'}")
        logger.info(f"   PredictBase: {'✅' if PB_AVAILABLE else '❌'}")
        logger.info("=" * 60)
        
        # Setup signal handlers
        def handle_shutdown(signum, frame):
            logger.info("\n👋 Shutdown requested...")
            self._is_running = False
        
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        while self._is_running:
            try:
                await self.run_cycle()
                
                if self._is_running:
                    logger.info(f"⏰ Next cycle in {interval_seconds}s...\n")
                    await asyncio.sleep(interval_seconds)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Daemon error: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(30)
        
        # Final stats
        logger.info("=" * 60)
        logger.info("📊 FINAL STATISTICS")
        logger.info("=" * 60)
        logger.info(f"   Cycles: {self.stats['cycles']}")
        logger.info(f"   Markets Scanned: {self.stats['markets_scanned']}")
        logger.info(f"   Signals Generated: {self.stats['signals_generated']}")
        logger.info(f"   Errors: {self.stats['errors']}")
        
        recorder_stats = self.recorder.get_stats()
        logger.info(f"   Total Stake: ${recorder_stats['total_stake']:.2f}")
        
        for sid, s in recorder_stats['by_strategy'].items():
            logger.info(f"   {sid}: {s['count']} signals, ${s['stake']:.2f}")
        
        logger.info("=" * 60)
        logger.info("👋 Daemon stopped")

# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Multi-Strategy Trading Daemon")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run as daemon")
    parser.add_argument("--interval", "-i", type=int, default=60, help="Interval (seconds)")
    parser.add_argument("--live", action="store_true", help="Live mode (DANGEROUS)")
    parser.add_argument("--init-db", action="store_true", help="Initialize database")
    
    args = parser.parse_args()
    
    # Initialize database if requested
    if args.init_db:
        if DB_AVAILABLE:
            init_database()
            print("✅ Database initialized")
        else:
            print("❌ Database not available")
        return
    
    # Run orchestrator
    paper_mode = not args.live
    
    async with MultiStrategyOrchestrator(paper_mode=paper_mode) as orchestrator:
        if args.daemon:
            await orchestrator.run_daemon(interval_seconds=args.interval)
        else:
            # Single cycle
            await orchestrator.run_cycle()

if __name__ == "__main__":
    asyncio.run(main())
