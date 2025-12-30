"""
AI-Powered Flash Market Strategy
Combines AI bias prediction with flash market trading.
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..ai.bias_analyzer import BiasAnalyzer, BiasDecision, MarketBias
from ..ai.cache import get_ai_cache
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class TradeAction(Enum):
    """Possible trade actions"""
    BUY_UP = "BUY_UP"       # Buy UP/Yes token
    BUY_DOWN = "BUY_DOWN"   # Buy DOWN/No token  
    HOLD = "HOLD"           # No action
    SKIP = "SKIP"           # Skip this market


@dataclass
class TradeSignal:
    """Complete trade signal with all decision data"""
    action: TradeAction
    asset: str                      # BTC, ETH
    market_id: Optional[str]        # Polymarket market ID
    token_id: Optional[str]         # Token to trade
    
    # Prices
    entry_price: float              # Price to buy at
    implied_prob: float             # Implied probability
    
    # Position sizing
    recommended_size_usdc: float    # Recommended position size
    max_size_usdc: float            # Maximum allowed size
    
    # AI Decision
    bias: MarketBias
    confidence: float
    ai_latency_ms: float
    
    # Risk metrics
    expected_value: float           # Expected profit/loss
    risk_reward_ratio: float        # Risk/reward ratio
    
    # Metadata
    timestamp: float = field(default_factory=time.time)
    reasoning: str = ""
    
    @property
    def is_actionable(self) -> bool:
        """Whether this signal should be acted upon"""
        return (
            self.action in (TradeAction.BUY_UP, TradeAction.BUY_DOWN) and
            self.confidence >= 0.6 and
            self.recommended_size_usdc > 0
        )


class AIFlashStrategy:
    """
    AI-powered flash market trading strategy.
    
    Strategy Logic:
    1. Every N minutes, fetch BTC/ETH price data
    2. Use AI to predict direction (UP/DOWN) for next 15 minutes
    3. If confidence is high enough, generate trade signal
    4. Apply position sizing based on confidence and risk parameters
    
    Key Parameters:
    - MIN_CONFIDENCE: Minimum AI confidence to trade (default: 0.6)
    - MAX_POSITION_USDC: Maximum position size per trade
    - BIAS_UPDATE_INTERVAL: How often to refresh AI bias (seconds)
    """
    
    # Strategy parameters
    MIN_CONFIDENCE = 0.6            # Minimum confidence to trade
    MAX_POSITION_USDC = 5.0         # Maximum per trade ($5 for validation)
    MIN_POSITION_USDC = 1.0         # Minimum meaningful trade
    BIAS_UPDATE_INTERVAL = 300      # 5 minutes between AI calls
    
    # Position sizing based on confidence
    CONFIDENCE_SIZING = {
        0.9: 1.0,    # 90%+ confidence = 100% of max size
        0.8: 0.75,   # 80%+ = 75%
        0.7: 0.5,    # 70%+ = 50%
        0.6: 0.25,   # 60%+ = 25%
    }
    
    def __init__(
        self,
        max_position_usdc: Optional[float] = None,
        min_confidence: Optional[float] = None,
        analyzer: Optional[BiasAnalyzer] = None
    ):
        """
        Initialize strategy.
        
        Args:
            max_position_usdc: Override max position size
            min_confidence: Override min confidence threshold
            analyzer: Custom bias analyzer
        """
        self._analyzer = analyzer or BiasAnalyzer()
        self._cache = get_ai_cache()
        
        # Load settings
        settings = get_settings()
        self._max_position = max_position_usdc or settings.max_position_size_usdc
        self._min_confidence = min_confidence or self.MIN_CONFIDENCE
        
        # Current state
        self._current_bias: Optional[BiasDecision] = None
        self._last_bias_update: float = 0
        
        # Stats
        self._signals_generated = 0
        self._trades_executed = 0
        self._total_pnl = 0.0
        
        logger.info(
            f"AIFlashStrategy initialized: "
            f"max_position=${self._max_position}, min_conf={self._min_confidence}"
        )
    
    async def get_trade_signal(
        self,
        market_data: Dict[str, Any],
        market_info: Optional[Dict[str, Any]] = None
    ) -> TradeSignal:
        """
        Generate trade signal based on market data and AI analysis.
        
        Args:
            market_data: Current market data (price_change, volume, trend)
            market_info: Optional Polymarket market info (market_id, prices, etc.)
            
        Returns:
            TradeSignal with complete trading decision
        """
        start_time = time.time()
        
        # Get AI bias prediction
        bias_decision = await self._get_bias(market_data)
        
        # Extract market info
        asset = market_data.get("asset", "BTC")
        market_id = market_info.get("market_id") if market_info else None
        
        # Get current prices if available
        up_price = market_info.get("up_price", 0.5) if market_info else 0.5
        down_price = market_info.get("down_price", 0.5) if market_info else 0.5
        
        # Determine action based on bias
        if bias_decision.bias == MarketBias.UP and bias_decision.confidence >= self._min_confidence:
            action = TradeAction.BUY_UP
            entry_price = up_price
            token_id = market_info.get("up_token_id") if market_info else None
        elif bias_decision.bias == MarketBias.DOWN and bias_decision.confidence >= self._min_confidence:
            action = TradeAction.BUY_DOWN
            entry_price = down_price
            token_id = market_info.get("down_token_id") if market_info else None
        else:
            action = TradeAction.HOLD
            entry_price = 0.5
            token_id = None
        
        # Calculate position size
        recommended_size = self._calculate_position_size(
            bias_decision.confidence,
            entry_price
        )
        
        # Calculate expected value
        # If we buy at price P and win, we get $1. If we lose, we get $0.
        # EV = confidence * (1 - P) - (1 - confidence) * P
        expected_value = (
            bias_decision.confidence * (1 - entry_price) - 
            (1 - bias_decision.confidence) * entry_price
        ) * recommended_size
        
        # Risk/reward ratio
        potential_profit = (1 - entry_price) * recommended_size
        potential_loss = entry_price * recommended_size
        risk_reward = potential_profit / potential_loss if potential_loss > 0 else 0
        
        signal = TradeSignal(
            action=action,
            asset=asset,
            market_id=market_id,
            token_id=token_id,
            entry_price=entry_price,
            implied_prob=entry_price,
            recommended_size_usdc=recommended_size,
            max_size_usdc=self._max_position,
            bias=bias_decision.bias,
            confidence=bias_decision.confidence,
            ai_latency_ms=bias_decision.latency_ms,
            expected_value=expected_value,
            risk_reward_ratio=risk_reward,
            reasoning=bias_decision.reasoning
        )
        
        self._signals_generated += 1
        
        logger.info(
            f"Trade signal: {action.value} {asset} @ ${entry_price:.2f} "
            f"(conf: {bias_decision.confidence:.2f}, size: ${recommended_size:.2f}, "
            f"EV: ${expected_value:.2f})"
        )
        
        return signal
    
    async def _get_bias(self, market_data: Dict[str, Any]) -> BiasDecision:
        """Get AI bias, using cache if available and fresh"""
        now = time.time()
        
        # Check if we need to refresh
        if (
            self._current_bias is None or
            now - self._last_bias_update > self.BIAS_UPDATE_INTERVAL
        ):
            # Get fresh bias from AI
            self._current_bias = self._analyzer.analyze(
                market_data,
                asset=market_data.get("asset", "BTC"),
                use_cache=True
            )
            self._last_bias_update = now
        
        return self._current_bias
    
    def _calculate_position_size(
        self,
        confidence: float,
        entry_price: float
    ) -> float:
        """
        Calculate position size based on confidence and Kelly criterion.
        
        Uses simplified Kelly: size = edge * bankroll / odds
        Capped by confidence-based scaling.
        """
        # Base size from confidence scaling
        size_multiplier = 0
        for conf_threshold, multiplier in sorted(
            self.CONFIDENCE_SIZING.items(),
            reverse=True
        ):
            if confidence >= conf_threshold:
                size_multiplier = multiplier
                break
        
        base_size = self._max_position * size_multiplier
        
        # Don't trade if below minimum
        if base_size < self.MIN_POSITION_USDC:
            return 0.0
        
        # Apply Kelly criterion adjustment
        # Edge = confidence - implied_prob
        edge = confidence - entry_price
        
        if edge <= 0:
            # No edge, reduce size significantly
            base_size *= 0.25
        elif edge > 0.1:
            # Good edge, can increase slightly
            base_size *= 1.1
        
        return min(base_size, self._max_position)
    
    def record_trade_result(self, profit_loss: float) -> None:
        """Record result of an executed trade"""
        self._trades_executed += 1
        self._total_pnl += profit_loss
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get strategy statistics"""
        return {
            "signals_generated": self._signals_generated,
            "trades_executed": self._trades_executed,
            "total_pnl": self._total_pnl,
            "avg_pnl_per_trade": (
                self._total_pnl / self._trades_executed 
                if self._trades_executed > 0 else 0
            ),
            "current_bias": (
                self._current_bias.bias.value 
                if self._current_bias else None
            ),
            "analyzer_stats": self._analyzer.stats
        }
    
    def reset_stats(self) -> None:
        """Reset strategy statistics"""
        self._signals_generated = 0
        self._trades_executed = 0
        self._total_pnl = 0.0


class AIStrategyRunner:
    """
    Runner for executing AI strategy in a loop.
    Handles the full trading cycle.
    """
    
    def __init__(
        self,
        strategy: Optional[AIFlashStrategy] = None,
        dry_run: bool = True
    ):
        """
        Initialize runner.
        
        Args:
            strategy: Strategy instance
            dry_run: If True, don't execute real trades
        """
        self._strategy = strategy or AIFlashStrategy()
        self._dry_run = dry_run
        self._running = False
        
        logger.info(f"AIStrategyRunner initialized (dry_run={dry_run})")
    
    async def run_once(
        self,
        market_data: Dict[str, Any],
        market_info: Optional[Dict[str, Any]] = None
    ) -> TradeSignal:
        """
        Run one iteration of the strategy.
        
        Args:
            market_data: Current market data
            market_info: Optional market info from Polymarket
            
        Returns:
            Generated trade signal
        """
        signal = await self._strategy.get_trade_signal(market_data, market_info)
        
        if signal.is_actionable and not self._dry_run:
            # TODO: Execute trade via order executor
            logger.info(f"Would execute: {signal.action.value} ${signal.recommended_size_usdc:.2f}")
        elif signal.is_actionable:
            logger.info(f"[DRY RUN] Signal: {signal.action.value} ${signal.recommended_size_usdc:.2f}")
        else:
            logger.debug(f"Signal not actionable: {signal.action.value}")
        
        return signal
    
    async def run_loop(
        self,
        interval_seconds: int = 60,
        max_iterations: Optional[int] = None
    ) -> None:
        """
        Run strategy in a loop.
        
        Args:
            interval_seconds: Time between iterations
            max_iterations: Stop after N iterations (None = infinite)
        """
        self._running = True
        iteration = 0
        
        logger.info(f"Starting strategy loop (interval={interval_seconds}s)")
        
        while self._running:
            if max_iterations and iteration >= max_iterations:
                break
            
            try:
                # TODO: Fetch real market data from price feeds
                # For now, use placeholder
                market_data = await self._fetch_market_data()
                
                signal = await self.run_once(market_data)
                
                iteration += 1
                
            except Exception as e:
                logger.error(f"Error in strategy loop: {e}")
            
            if self._running:
                await asyncio.sleep(interval_seconds)
        
        logger.info(f"Strategy loop stopped after {iteration} iterations")
    
    async def _fetch_market_data(self) -> Dict[str, Any]:
        """
        Fetch current market data.
        TODO: Implement real data fetching from price feeds.
        """
        # Placeholder - in production, fetch from:
        # - Binance/Coinbase API for BTC price
        # - Calculate 15-min change
        # - Determine volume and trend
        return {
            "asset": "BTC",
            "price_change": "+0.5%",
            "volume": "normal",
            "trend": "neutral"
        }
    
    def stop(self) -> None:
        """Stop the running loop"""
        self._running = False
        logger.info("Strategy runner stopping...")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get runner and strategy stats"""
        return {
            "dry_run": self._dry_run,
            "running": self._running,
            "strategy_stats": self._strategy.stats
        }
