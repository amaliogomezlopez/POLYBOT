"""
🎯 BASE STRATEGY - ABSTRACT CLASS
==================================
Strategy Pattern implementation for multi-strategy trading system.

All strategies must inherit from BaseStrategy and implement:
- process_market(): Evaluate market and return signal
- get_config(): Return strategy configuration

Features:
- Async-first design for non-blocking execution
- Built-in rate limiting
- Automatic trade recording
- Performance tracking
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# DATA CLASSES
# =============================================================================

class SignalType(Enum):
    """Type of trading signal."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass
class MarketData:
    """
    Standardized market data passed to strategies.
    All strategies receive the same data format.
    """
    # Identity
    condition_id: str
    question: str
    token_id: Optional[str] = None
    market_slug: Optional[str] = None
    
    # Current Prices
    yes_price: float = 0.0
    no_price: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    mid_price: float = 0.0
    spread_bps: float = 0.0
    
    # Volume
    volume_24h: float = 0.0
    volume_1h: float = 0.0
    
    # Orderbook (optional, for advanced strategies)
    bid_depth: Dict[str, float] = field(default_factory=dict)
    ask_depth: Dict[str, float] = field(default_factory=dict)
    
    # Time
    end_date: Optional[datetime] = None
    hours_to_expiry: Optional[float] = None
    
    # Cross-Exchange (for arbitrage)
    competitor_prices: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Historical (for sniper)
    price_history: List[float] = field(default_factory=list)
    volume_history: List[float] = field(default_factory=list)
    
    # Raw data for snapshot
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def multiplier(self) -> float:
        """Calculate potential multiplier for YES."""
        if self.yes_price > 0:
            return 1 / self.yes_price
        return 0
    
    def to_snapshot(self) -> Dict[str, Any]:
        """Convert to snapshot format for database storage."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "condition_id": self.condition_id,
            "yes_price": self.yes_price,
            "no_price": self.no_price,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "mid_price": self.mid_price,
            "spread_bps": self.spread_bps,
            "volume_24h": self.volume_24h,
            "volume_1h": self.volume_1h,
            "hours_to_expiry": self.hours_to_expiry,
            "competitor_prices": self.competitor_prices,
            "bid_depth_summary": sum(self.bid_depth.values()) if self.bid_depth else 0,
            "ask_depth_summary": sum(self.ask_depth.values()) if self.ask_depth else 0,
        }

@dataclass
class TradeSignal:
    """
    Trading signal returned by strategy.
    Contains all information needed to execute and record the trade.
    """
    # Signal Identity
    strategy_id: str
    signal_type: SignalType
    
    # Market
    condition_id: str
    token_id: Optional[str] = None
    question: str = ""
    
    # Trade Parameters
    outcome: str = "YES"  # "YES" or "NO"
    entry_price: float = 0.0
    stake: float = 2.0  # USD
    
    # Confidence
    confidence: float = 0.5  # 0-1
    expected_value: float = 0.0
    
    # Metadata (why signal was generated)
    trigger_reason: str = ""
    signal_data: Dict[str, Any] = field(default_factory=dict)
    
    # Market Snapshot (for ML retraining)
    snapshot_data: Dict[str, Any] = field(default_factory=dict)
    
    # Timestamps
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def potential_payout(self) -> float:
        """Calculate potential payout if win."""
        if self.entry_price > 0:
            return self.stake / self.entry_price
        return 0
    
    @property
    def multiplier(self) -> float:
        """Calculate multiplier."""
        if self.entry_price > 0:
            return 1 / self.entry_price
        return 0
    
    def __repr__(self):
        return (f"<Signal [{self.strategy_id}] {self.signal_type.value} "
                f"{self.outcome}@{self.entry_price:.4f} "
                f"(conf={self.confidence:.0%}, EV={self.expected_value:.2f})>")

# =============================================================================
# ABSTRACT BASE STRATEGY
# =============================================================================

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Subclasses must implement:
    - process_market(): Core logic to evaluate market and generate signals
    - get_config(): Return strategy configuration
    
    Optional overrides:
    - on_start(): Called when strategy starts
    - on_stop(): Called when strategy stops
    - on_trade_executed(): Called after trade is recorded
    """
    
    def __init__(
        self,
        strategy_id: str,
        paper_mode: bool = True,
        stake_size: float = 2.0,
        max_daily_trades: int = 50,
        **kwargs
    ):
        self.strategy_id = strategy_id
        self.paper_mode = paper_mode
        self.stake_size = stake_size
        self.max_daily_trades = max_daily_trades
        
        # Runtime state
        self._is_running = False
        self._trades_today = 0
        self._last_reset = datetime.utcnow().date()
        self._processed_markets: set = set()  # Avoid duplicate signals
        
        # Performance tracking
        self._signals_generated = 0
        self._signals_executed = 0
        
        # Rate limiting
        self._last_process_time = 0
        self._min_process_interval = 0.1  # seconds
        
        # Custom parameters from kwargs
        self.params = kwargs
        
        logger.info(f"Initialized strategy: {strategy_id} (paper={paper_mode})")
    
    # -------------------------------------------------------------------------
    # ABSTRACT METHODS (must implement)
    # -------------------------------------------------------------------------
    
    @abstractmethod
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Core strategy logic. Evaluate market and decide whether to trade.
        
        Args:
            market: Standardized market data
        
        Returns:
            TradeSignal if strategy wants to enter, None otherwise
        
        Example implementation:
            if market.yes_price < 0.04 and self.passes_filters(market):
                return TradeSignal(
                    strategy_id=self.strategy_id,
                    signal_type=SignalType.BUY,
                    condition_id=market.condition_id,
                    entry_price=market.yes_price,
                    stake=self.stake_size,
                    confidence=0.7,
                    trigger_reason="price_below_threshold"
                )
            return None
        """
        pass
    
    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """
        Return strategy configuration for logging/display.
        
        Returns:
            Dict with strategy parameters
        """
        pass
    
    # -------------------------------------------------------------------------
    # LIFECYCLE HOOKS (optional override)
    # -------------------------------------------------------------------------
    
    async def on_start(self):
        """Called when strategy starts. Override for initialization."""
        pass
    
    async def on_stop(self):
        """Called when strategy stops. Override for cleanup."""
        pass
    
    async def on_trade_executed(self, signal: TradeSignal, trade_id: str):
        """Called after trade is recorded. Override for post-trade logic."""
        pass
    
    # -------------------------------------------------------------------------
    # CORE PROCESSING (do not override)
    # -------------------------------------------------------------------------
    
    async def process(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Process market with rate limiting and deduplication.
        
        This is the main entry point called by the orchestrator.
        Do NOT override - override process_market() instead.
        """
        # Rate limiting
        now = asyncio.get_event_loop().time()
        if now - self._last_process_time < self._min_process_interval:
            return None
        self._last_process_time = now
        
        # Reset daily counter
        today = datetime.utcnow().date()
        if today != self._last_reset:
            self._trades_today = 0
            self._last_reset = today
            self._processed_markets.clear()
        
        # Check daily limit
        if self._trades_today >= self.max_daily_trades:
            return None
        
        # Deduplication (don't signal same market twice per day)
        if market.condition_id in self._processed_markets:
            return None
        
        try:
            signal = await self.process_market(market)
            
            if signal:
                self._signals_generated += 1
                self._processed_markets.add(market.condition_id)
                
                # Ensure signal has snapshot
                if not signal.snapshot_data:
                    signal.snapshot_data = market.to_snapshot()
                
                logger.info(f"📊 Signal: {signal}")
            
            return signal
            
        except Exception as e:
            logger.error(f"Strategy {self.strategy_id} error: {e}")
            return None
    
    # -------------------------------------------------------------------------
    # UTILITY METHODS
    # -------------------------------------------------------------------------
    
    def should_skip(self, market: MarketData) -> bool:
        """Check if market should be skipped (common filters)."""
        # Already processed
        if market.condition_id in self._processed_markets:
            return True
        
        # Daily limit reached
        if self._trades_today >= self.max_daily_trades:
            return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get strategy runtime statistics."""
        return {
            "strategy_id": self.strategy_id,
            "is_running": self._is_running,
            "paper_mode": self.paper_mode,
            "trades_today": self._trades_today,
            "signals_generated": self._signals_generated,
            "signals_executed": self._signals_executed,
            "processed_markets": len(self._processed_markets),
        }
    
    def reset_daily(self):
        """Reset daily counters."""
        self._trades_today = 0
        self._processed_markets.clear()
        self._last_reset = datetime.utcnow().date()
    
    def increment_trade_count(self):
        """Increment trade counter (called after successful execution)."""
        self._trades_today += 1
        self._signals_executed += 1

# =============================================================================
# STRATEGY REGISTRY
# =============================================================================

class StrategyRegistry:
    """
    Registry for managing multiple strategies.
    Provides centralized access to all active strategies.
    """
    
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}
    
    def register(self, strategy: BaseStrategy):
        """Register a strategy."""
        self._strategies[strategy.strategy_id] = strategy
        logger.info(f"Registered strategy: {strategy.strategy_id}")
    
    def unregister(self, strategy_id: str):
        """Unregister a strategy."""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            logger.info(f"Unregistered strategy: {strategy_id}")
    
    def get(self, strategy_id: str) -> Optional[BaseStrategy]:
        """Get a strategy by ID."""
        return self._strategies.get(strategy_id)
    
    def get_all(self) -> List[BaseStrategy]:
        """Get all registered strategies."""
        return list(self._strategies.values())
    
    def get_active(self) -> List[BaseStrategy]:
        """Get all active strategies."""
        return [s for s in self._strategies.values() if s._is_running]
    
    async def process_all(self, market: MarketData) -> List[TradeSignal]:
        """
        Process market through all strategies in parallel.
        
        Returns:
            List of signals from all strategies
        """
        tasks = [s.process(market) for s in self._strategies.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        signals = []
        for result in results:
            if isinstance(result, TradeSignal):
                signals.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Strategy error: {result}")
        
        return signals
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get stats from all strategies."""
        return {sid: s.get_stats() for sid, s in self._strategies.items()}


# Global registry instance
strategy_registry = StrategyRegistry()
