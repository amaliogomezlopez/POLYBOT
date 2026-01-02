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

# CRITICAL: Import MarketData first (needed for type hints even if strategies fail)
try:
    from src.trading.strategies.base_strategy import MarketData, TradeSignal, SignalType
    MARKET_DATA_AVAILABLE = True
except Exception as e:
    MARKET_DATA_AVAILABLE = False
    logger.error(f"❌ CRITICAL: MarketData not available: {e}")
    # Create a dummy MarketData for type hints (daemon will fail gracefully)
    from dataclasses import dataclass, field
    from typing import Dict, Any, List
    from datetime import datetime
    
    @dataclass
    class MarketData:
        condition_id: str = ""
        question: str = ""
        token_id: str = ""
        yes_price: float = 0.0
        no_price: float = 0.0
        volume_24h: float = 0.0
        liquidity: float = 0.0
    
    class SignalType:
        BUY = "BUY"
        SELL = "SELL"
    
    TradeSignal = None

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

# Try strategies (MarketData/TradeSignal/SignalType already imported above)
try:
    from src.trading.strategies import (
        strategy_registry,
        InternalArbStrategy,  # NEW: Internal orderbook arbitrage
        SniperStrategy,
        TailStrategy,
        EsportsOracleStrategy,
        OracleStrategyRunner,
    )
    STRATEGIES_AVAILABLE = True
    logger.info("✅ Strategies available")
except Exception as e:
    STRATEGIES_AVAILABLE = False
    logger.error(f"❌ Strategies not available: {e}")

# Try Riot client for ORACLE
try:
    from src.exchanges.riot_client import RiotGuard, create_riot_client, KeyExpiredError
    RIOT_AVAILABLE = True
except Exception as e:
    RIOT_AVAILABLE = False
    logger.warning(f"⚠️ Riot client not available: {e}")

# PredictBase DEPRECATED (Jan 2026 analysis: 0 liquidity)
# from src.exchanges.predictbase_client import PredictBaseClient
PB_AVAILABLE = False  # Disabled - no liquidity on PredictBase

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
    
    # Performance - Now with full pagination, we can scan more!
    # The scanner filters aggressively, so 500 accepted = ~4000 scanned
    MAX_MARKETS_PER_CYCLE = 500  # Actionable markets after filtering
    REQUEST_DELAY = 0.1  # seconds between API calls (10 req/s)
    
    # Memory management
    GC_INTERVAL_CYCLES = 5  # Run GC every N cycles (more frequent now)

# Ensure directories exist
Config.DATA_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# MARKET SCANNER (OPTIMIZED WITH FULL PAGINATION)
# =============================================================================

class MarketScanner:
    """
    Fetches market data from Polymarket APIs with full pagination.
    
    Features:
    - Paginates through ALL active markets (~4000+) using Gamma API
    - On-the-fly filtering to minimize RAM usage
    - Rate limiting (10 req/s safe for Gamma's 300 req/10s limit)
    - Memory efficient: processes and discards each batch immediately
    
    Target: Scan 100% of Polymarket with <50MB RAM overhead
    """
    
    # Filtering thresholds (markets below these are discarded)
    MIN_VOLUME_24H = 500       # Minimum 24h volume in USD
    MIN_LIQUIDITY = 100        # Minimum liquidity
    MIN_PRICE = 0.001          # Exclude dead markets with 0 prices
    MAX_PRICE = 0.999          # Exclude already-settled markets (YES=1.0)
    
    # Pagination settings
    BATCH_SIZE = 100           # Markets per API call (Gamma max)
    REQUEST_DELAY = 0.1        # 100ms between requests (10 req/s)
    MAX_RETRIES = 3            # Retries per failed request
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        
        # Stats for logging
        self._total_scanned = 0
        self._total_filtered = 0
        self._total_accepted = 0
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    async def get_active_markets(self, limit: int = 500) -> List[MarketData]:
        """
        Fetch ALL active markets from Polymarket with pagination.
        
        Process:
        1. Paginate through Gamma API (100 markets per call)
        2. Filter on-the-fly (active, volume, liquidity)
        3. Parse only qualifying markets into MarketData
        4. Release memory after each batch
        
        Args:
            limit: Maximum markets to return (default 500, 0 = unlimited)
        
        Returns:
            List of MarketData objects ready for strategy processing
        """
        markets: List[MarketData] = []
        seen_ids: set = set()
        offset = 0
        
        # Reset stats
        self._total_scanned = 0
        self._total_filtered = 0
        self._total_accepted = 0
        
        logger.info("🔍 Starting full market scan with pagination...")
        
        while True:
            # Fetch batch from Gamma API
            batch = await self._fetch_batch(offset)
            
            # Stop if empty response (no more markets)
            if not batch:
                logger.debug(f"Empty batch at offset {offset}, stopping")
                break
            
            batch_size = len(batch)
            self._total_scanned += batch_size
            
            # Process batch on-the-fly
            for raw_market in batch:
                # Gamma uses conditionId, CLOB uses condition_id
                cid = raw_market.get("conditionId") or raw_market.get("condition_id")
                
                # Skip if no condition ID
                if not cid:
                    self._total_filtered += 1
                    continue
                
                # Skip duplicates
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                
                # Quick filter (before expensive parsing)
                if not self._quick_filter(raw_market):
                    self._total_filtered += 1
                    continue
                
                # Parse to MarketData
                market_data = self._parse_market_sync(raw_market)
                if market_data:
                    markets.append(market_data)
                    self._total_accepted += 1
                    
                    # Check limit
                    if limit > 0 and len(markets) >= limit:
                        break
                else:
                    # Failed parsing (e.g., invalid prices)
                    self._total_filtered += 1
            
            # Log progress every 1000 markets
            if self._total_scanned % 1000 == 0:
                logger.info(f"📊 Scanned {self._total_scanned} markets... "
                           f"({self._total_accepted} accepted)")
            
            # Release batch memory
            del batch
            
            # Check if we hit limit
            if limit > 0 and len(markets) >= limit:
                break
            
            # Move to next page
            offset += self.BATCH_SIZE
            
            # Rate limiting - be nice to the API
            await asyncio.sleep(self.REQUEST_DELAY)
            
            # Safety check: if batch was smaller than BATCH_SIZE, we're at the end
            if batch_size < self.BATCH_SIZE:
                break
        
        # Force garbage collection after full scan
        gc.collect()
        
        # Final log
        logger.info(f"✅ Scan complete: {self._total_accepted} actionable markets "
                   f"out of {self._total_scanned} scanned "
                   f"({self._total_filtered} filtered out)")
        
        return markets
    
    async def _fetch_batch(self, offset: int) -> List[dict]:
        """
        Fetch a single batch from Gamma API with retries.
        
        Args:
            offset: Starting position for pagination
            
        Returns:
            List of raw market dicts, or empty list on failure
        """
        url = f"{Config.GAMMA_API}/markets"
        params = {
            "limit": self.BATCH_SIZE,
            "offset": offset,
            "active": "true",      # Only active markets
            "closed": "false",     # Not closed
        }
        
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = await self.client.get(url, params=params)
                
                if resp.status_code == 200:
                    data = resp.json()
                    # Gamma returns list directly, not wrapped in "data"
                    return data if isinstance(data, list) else data.get("data", [])
                
                elif resp.status_code == 429:
                    # Rate limited - back off
                    wait_time = 2 ** attempt
                    logger.warning(f"⚠️ Rate limited at offset {offset}, "
                                  f"waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    
                else:
                    logger.debug(f"API error {resp.status_code} at offset {offset}")
                    
            except httpx.TimeoutException:
                logger.debug(f"Timeout at offset {offset}, retry {attempt + 1}")
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.debug(f"Error fetching batch at offset {offset}: {e}")
                await asyncio.sleep(0.5)
        
        return []
    
    def _quick_filter(self, raw: dict) -> bool:
        """
        Fast pre-filter before expensive parsing.
        Rejects obviously unsuitable markets.
        
        Gamma API returns:
        - volume/liquidity as strings
        - outcomes/outcomePrices as JSON strings
        - conditionId (not condition_id)
        
        Args:
            raw: Raw market dict from API
            
        Returns:
            True if market passes quick filter
        """
        # Must be active
        if raw.get("active") is False:
            return False
        
        # Must not be closed
        if raw.get("closed") is True:
            return False
        
        # Check volume threshold (Gamma returns as string)
        volume = 0
        try:
            vol_str = raw.get("volume") or raw.get("volumeNum") or "0"
            volume = float(vol_str)
        except (ValueError, TypeError):
            pass
        
        if volume < self.MIN_VOLUME_24H:
            return False
        
        # Check liquidity (Gamma returns as string)
        liquidity = 0
        try:
            liq_str = raw.get("liquidity") or raw.get("liquidityNum") or "0"
            liquidity = float(liq_str)
        except (ValueError, TypeError):
            pass
        
        if liquidity > 0 and liquidity < self.MIN_LIQUIDITY:
            return False
        
        # Must have outcomes (Gamma uses "outcomes" as JSON string or "tokens")
        outcomes = raw.get("outcomes") or raw.get("tokens")
        if not outcomes:
            return False
        
        # Must have prices
        prices = raw.get("outcomePrices") or raw.get("tokens")
        if not prices:
            return False
        
        return True
    
    def _parse_market_sync(self, raw: dict) -> Optional[MarketData]:
        """
        Parse raw market data into MarketData object (sync version).
        
        Handles both Gamma API format (strings) and CLOB format (objects).
        Extracts only essential fields to minimize memory.
        """
        try:
            # Gamma uses conditionId, CLOB uses condition_id
            cid = raw.get("conditionId") or raw.get("condition_id")
            if not cid:
                return None
            
            question = raw.get("question", "")[:500]  # Truncate long questions
            
            # Extract token prices - handle both formats
            yes_price = 0.0
            no_price = 0.0
            token_id = None
            
            # Try Gamma format first (outcomePrices as JSON string)
            outcome_prices = raw.get("outcomePrices")
            outcomes = raw.get("outcomes")
            
            if outcome_prices and outcomes:
                try:
                    # Parse JSON strings
                    if isinstance(outcome_prices, str):
                        prices_list = json.loads(outcome_prices)
                    else:
                        prices_list = outcome_prices
                    
                    if isinstance(outcomes, str):
                        outcomes_list = json.loads(outcomes)
                    else:
                        outcomes_list = outcomes
                    
                    # Extract YES/NO prices
                    for i, outcome in enumerate(outcomes_list):
                        if i < len(prices_list):
                            price = float(prices_list[i])
                            if outcome.upper() == "YES":
                                yes_price = price
                            elif outcome.upper() == "NO":
                                no_price = price
                except (json.JSONDecodeError, ValueError, IndexError):
                    pass
            
            # Fallback to CLOB format (tokens array)
            if yes_price == 0:
                for token in raw.get("tokens", []):
                    outcome = str(token.get("outcome", "")).upper()
                    try:
                        price = float(token.get("price", 0) or 0)
                    except (ValueError, TypeError):
                        price = 0.0
                    
                    if outcome == "YES":
                        yes_price = price
                        token_id = token.get("token_id")
                    elif outcome == "NO":
                        no_price = price
            
            # Get token IDs from Gamma format
            if not token_id:
                clob_token_ids = raw.get("clobTokenIds")
                if clob_token_ids:
                    try:
                        if isinstance(clob_token_ids, str):
                            token_ids = json.loads(clob_token_ids)
                        else:
                            token_ids = clob_token_ids
                        if token_ids:
                            token_id = token_ids[0]  # First token is YES
                    except:
                        pass
            
            # Validate prices
            if yes_price < self.MIN_PRICE or yes_price > self.MAX_PRICE:
                return None
            
            # Calculate derived fields
            mid_price = (yes_price + no_price) / 2 if no_price > 0 else yes_price
            spread_bps = abs(yes_price - (1 - no_price)) * 10000 if no_price > 0 else 0
            
            # Parse end date (Gamma uses endDate or endDateIso)
            hours_to_expiry = None
            end_date = raw.get("endDate") or raw.get("end_date_iso") or raw.get("end_date")
            if end_date:
                try:
                    if isinstance(end_date, str):
                        # Handle various date formats
                        if "T" in end_date:
                            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        else:
                            end_dt = datetime.fromisoformat(end_date + "T23:59:59+00:00")
                        hours_to_expiry = max(0, (end_dt - datetime.now(end_dt.tzinfo)).total_seconds() / 3600)
                except:
                    pass
            
            # Get volume (handle string format)
            volume = 0.0
            try:
                vol_str = raw.get("volume") or raw.get("volumeNum") or "0"
                volume = float(vol_str)
            except:
                pass
            
            return MarketData(
                condition_id=cid,
                question=question,
                token_id=token_id,
                market_slug=raw.get("slug") or raw.get("market_slug", ""),
                yes_price=yes_price,
                no_price=no_price,
                best_bid=yes_price * 0.99,  # Estimate spread
                best_ask=yes_price * 1.01,
                mid_price=mid_price,
                spread_bps=spread_bps,
                volume_24h=volume,
                hours_to_expiry=hours_to_expiry,
                competitor_prices={},  # Fetched on-demand by ArbitrageStrategy
                raw_data=None  # Don't store raw data - saves RAM!
            )
            
        except Exception as e:
            logger.debug(f"Error parsing market: {e}")
            return None
    
    # Legacy method for backward compatibility
    async def _parse_market(self, raw: dict) -> Optional[MarketData]:
        """Async wrapper for backward compatibility."""
        return self._parse_market_sync(raw)

# =============================================================================
# SIGNAL RECORDER
# =============================================================================

class SignalRecorder:
    """
    Records signals to database and JSON backup.
    Thread-safe for async usage.
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
    
    async def record(self, signal: TradeSignal) -> str:
        """
        Record a signal to database and JSON (async-safe).
        
        Uses asyncio.to_thread() to run sync DB operations in a thread pool,
        avoiding greenlet/async conflicts.
        
        Returns:
            Trade ID
        """
        trade_id = f"{signal.strategy_id}-{int(datetime.utcnow().timestamp())}"
        
        # Save to database (run sync function in thread pool)
        if DB_AVAILABLE:
            try:
                # Run sync record_trade in a thread to avoid greenlet issues
                trade = await asyncio.to_thread(
                    record_trade,
                    strategy_id=signal.strategy_id,
                    condition_id=signal.condition_id,
                    outcome=signal.outcome,
                    entry_price=signal.entry_price,
                    stake=signal.stake,
                    snapshot_data=signal.snapshot_data or {},
                    signal_data=signal.signal_data or {},
                    paper_mode=True,
                    token_id=signal.token_id,
                    question=signal.question
                )
                trade_id = trade.trade_id
                logger.debug(f"Trade saved to DB: {trade_id}")
            except Exception as e:
                logger.error(f"DB record error: {e}")
        
        # Save to JSON backup (sync, but fast)
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
    2. ARB batch scan runs first (efficient cross-exchange matching)
    3. Other strategies process per-market
    4. Signals are recorded immediately
    5. Stats are updated
    6. ORACLE monitors esports independently
    """
    
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.scanner: Optional[MarketScanner] = None
        self.recorder = SignalRecorder()
        
        # Internal ARB strategy (replaces PredictBase ARB)
        self._internal_arb_strategy: Optional[InternalArbStrategy] = None
        
        # ORACLE strategy (independent from market scanning)
        self.oracle_strategy: Optional[EsportsOracleStrategy] = None
        self.oracle_task: Optional[asyncio.Task] = None
        
        # Runtime state
        self._is_running = False
        self._cycle_count = 0
        self._start_time = None
        
        # Stats
        self.stats = {
            "cycles": 0,
            "markets_scanned": 0,
            "signals_generated": 0,
            "arb_signals": 0,
            "errors": 0,
        }
    
    async def __aenter__(self):
        # Initialize scanner (no PredictBase dependency)
        self.scanner = MarketScanner()
        await self.scanner.__aenter__()
        
        # Register strategies
        self._register_strategies()
        
        # Initialize ORACLE strategy (runs independently)
        await self._init_oracle()
        
        self._start_time = datetime.utcnow()
        return self
    
    async def __aexit__(self, *args):
        # Stop ORACLE first
        if self.oracle_strategy:
            try:
                await self.oracle_strategy.stop()
            except Exception as e:
                logger.error(f"Error stopping ORACLE: {e}")
        
        if self.scanner:
            await self.scanner.__aexit__(*args)
    
    async def _init_oracle(self):
        """
        Initialize ORACLE esports strategy.
        
        ORACLE runs independently from the main market scanning loop.
        If Riot API key expires, it pauses gracefully without crashing.
        """
        if not RIOT_AVAILABLE:
            logger.warning("⚠️ ORACLE: Riot client not available, skipping")
            return
        
        try:
            logger.info("🎮 Initializing ORACLE Esports Strategy...")
            
            # Create Oracle strategy with signal callback
            self.oracle_strategy = EsportsOracleStrategy(
                db_callback=self._record_oracle_signal,
                order_callback=None,  # Paper mode for now
            )
            
            # Start Oracle (runs its own monitoring loop)
            success = await self.oracle_strategy.start()
            
            if success:
                logger.info("✅ ORACLE strategy started successfully")
            else:
                logger.warning("⚠️ ORACLE strategy started in PAUSED state (API key issue)")
                logger.warning("   Update RIOT_API_KEY in .env and call hot_reload")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize ORACLE: {e}")
            self.oracle_strategy = None
    
    async def _record_oracle_signal(self, oracle_signal):
        """
        Callback to record ORACLE signals to database.
        
        Converts OracleSignal to TradeSignal format for unified recording.
        """
        try:
            # Create a TradeSignal-like dict for recording
            signal_dict = {
                "trade_id": oracle_signal.signal_id,
                "strategy_id": "ORACLE",
                "timestamp": oracle_signal.api_timestamp.isoformat(),
                "condition_id": oracle_signal.market_condition_id,
                "question": oracle_signal.market_question,
                "outcome": oracle_signal.recommended_side,
                "entry_price": oracle_signal.current_price,
                "stake": oracle_signal.stake_usdc,
                "confidence": oracle_signal.confidence,
                "expected_value": oracle_signal.edge * oracle_signal.stake_usdc,
                "trigger_reason": f"{oracle_signal.event_type.value}: {oracle_signal.detected_winner}",
                "signal_data": {
                    "match": oracle_signal.match_description,
                    "event": oracle_signal.event_type.value,
                    "winner": oracle_signal.detected_winner,
                    "edge": oracle_signal.edge,
                    "window_seconds": oracle_signal.window_seconds,
                },
                "snapshot_data": {},
            }
            
            # Save to JSON backup
            self.recorder._signals_today.append(signal_dict)
            self.recorder._save_json()
            
            # Save to database if available
            if DB_AVAILABLE:
                try:
                    record_trade(
                        strategy_id="ORACLE",
                        condition_id=oracle_signal.market_condition_id,
                        outcome=oracle_signal.recommended_side,
                        entry_price=oracle_signal.current_price,
                        stake=oracle_signal.stake_usdc,
                        snapshot_data={},
                        signal_data=signal_dict["signal_data"],
                        paper_mode=self.paper_mode,
                        token_id=oracle_signal.token_id,
                        question=oracle_signal.market_question,
                    )
                except Exception as e:
                    logger.error(f"DB error recording ORACLE signal: {e}")
            
            self.stats["signals_generated"] += 1
            
            logger.info(f"🎯 ORACLE SIGNAL RECORDED: {oracle_signal.signal_id}")
            
        except Exception as e:
            logger.error(f"Error recording ORACLE signal: {e}")
    
    def _register_strategies(self):
        """Register all strategies."""
        if not STRATEGIES_AVAILABLE:
            logger.error("Strategies not available!")
            return
        
        # Clear existing
        strategy_registry._strategies.clear()
        
        # Create Internal ARB strategy (risk-free orderbook inefficiencies)
        self._internal_arb_strategy = InternalArbStrategy(
            paper_mode=self.paper_mode, 
            stake_size=50.0,
            max_cost=0.99,  # 1% minimum ROI
            min_cost=0.90,  # Avoid dead markets
        )
        
        # Register each strategy
        strategies = [
            self._internal_arb_strategy,
            SniperStrategy(paper_mode=self.paper_mode, stake_size=5.0),
            TailStrategy(paper_mode=self.paper_mode, stake_size=2.0),
        ]
        
        for s in strategies:
            strategy_registry.register(s)
            s._is_running = True
            logger.info(f"   📊 {s.strategy_id}: {s.get_config()}")
    
    async def _check_internal_arb(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Check a single market for internal arbitrage opportunity.
        
        Internal ARB: If YES + NO < 0.99, buying both guarantees profit.
        This is done per-market (fast, sync) instead of batch.
        """
        if not self._internal_arb_strategy:
            return None
        
        try:
            signal = await self._internal_arb_strategy.evaluate(market)
            if signal:
                self.stats["arb_signals"] += 1
            return signal
        except Exception as e:
            logger.debug(f"Internal ARB check error: {e}")
            return None
    
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
            
            # 2. Process each market through ALL strategies (including Internal ARB)
            for market in markets:
                try:
                    # All strategies process via registry (Internal ARB included)
                    signals = await strategy_registry.process_all(market)
                    
                    for signal in signals:
                        if signal and signal.signal_type == SignalType.BUY:
                            # Record signal (async to avoid greenlet issues)
                            trade_id = await self.recorder.record(signal)
                            
                            results["signals"].append({
                                "trade_id": trade_id,
                                "strategy": signal.strategy_id,
                                "question": signal.question[:50],
                                "price": signal.entry_price,
                                "stake": signal.stake,
                            })
                            
                            self.stats["signals_generated"] += 1
                            
                            # Special log for Internal ARB
                            if signal.strategy_id == "ARB_INTERNAL_V1":
                                roi_pct = signal.signal_data.get("roi_pct", 0) if signal.signal_data else 0
                                logger.info(
                                    f"🎯 INTERNAL ARB [{signal.strategy_id}] "
                                    f"Cost: ${signal.entry_price:.4f} | "
                                    f"ROI: {roi_pct:.2f}% | "
                                    f"{signal.question[:40]}..."
                                )
                            else:
                                logger.info(
                                    f"✅ SIGNAL [{signal.strategy_id}] "
                                    f"${signal.entry_price:.4f} | "
                                    f"EV: ${signal.expected_value:+.2f} | "
                                    f"{signal.question[:40]}..."
                                )
                    
                except Exception as e:
                    results["errors"].append(str(e))
                    logger.debug(f"Market processing error: {e}")
            
            # 4. Log cycle summary
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
        logger.info(f"   Internal ARB: {'✅' if self._internal_arb_strategy else '❌'}")
        logger.info(f"   ORACLE (Esports): {'✅' if self.oracle_strategy and self.oracle_strategy.state.value != 'disabled' else '❌'}")
        logger.info("=" * 60)
        
        # Setup signal handlers
        def handle_shutdown(signum, frame):
            logger.info("\n👋 Shutdown requested...")
            self._is_running = False
        
        def handle_reload(signum, frame):
            """Handle SIGHUP for hot-reload of API keys"""
            logger.info("\n🔄 Hot-reload requested (SIGHUP)...")
            if self.oracle_strategy:
                asyncio.create_task(self.oracle_strategy.hot_reload_api_key())
        
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        # SIGHUP for hot-reload (Unix only)
        try:
            signal.signal(signal.SIGHUP, handle_reload)
        except AttributeError:
            pass  # Windows doesn't have SIGHUP
        
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
        
        # ORACLE stats
        if self.oracle_strategy:
            oracle_status = self.oracle_strategy.get_status()
            logger.info(f"   ORACLE State: {oracle_status['state']}")
            logger.info(f"   ORACLE Signals: {oracle_status['stats']['signals_generated']}")
            logger.info(f"   ORACLE Events Detected: {oracle_status['stats']['events_detected']}")
        
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
