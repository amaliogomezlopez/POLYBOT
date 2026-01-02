"""
FLASH_SNIPER_V1: Aggressive Flash Market Strategy

This strategy is based on reverse-engineering Account88888's trading patterns.
Key findings:
- Ultra-high frequency (15,000+ trades/hour)
- 100% BUY orders (both UP and DOWN tokens)
- Sub-second execution intervals
- 100% Crypto flash market focus

The strategy targets 15-minute crypto flash markets and accumulates
both outcome tokens when the combined cost is below $1.00.

Unlike our defensive Internal Arb strategy, this is AGGRESSIVE:
- No waiting for perfect spreads
- High volume, small margins
- Rapid fire execution
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import asyncio
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FlashSniperConfig:
    """Configuration for the Flash Sniper strategy."""
    
    # Minimum profit threshold (0.002 = 0.2%)
    min_spread: float = 0.002
    
    # Maximum acceptable combined cost (UP + DOWN)
    max_combined_cost: float = 0.998
    
    # Position sizing
    base_position_usdc: float = 50.0
    max_position_usdc: float = 500.0
    
    # Frequency controls
    min_interval_seconds: float = 0.1  # 100ms minimum between trades
    max_trades_per_minute: int = 100
    
    # Market filters
    allowed_assets: list[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL", "XRP"])
    max_time_to_expiry_minutes: int = 15
    min_time_to_expiry_minutes: int = 2
    
    # Risk limits
    max_daily_loss_usdc: float = 500.0
    max_open_positions: int = 20
    
    # Execution mode
    use_fok_orders: bool = True  # Fill-or-Kill for atomic execution


@dataclass 
class MarketOpportunity:
    """Represents a detected flash market opportunity."""
    market_id: str
    event_slug: str
    up_token_id: str
    down_token_id: str
    up_ask: float
    down_ask: float
    up_liquidity: float
    down_liquidity: float
    expires_at: datetime
    
    @property
    def combined_cost(self) -> float:
        return self.up_ask + self.down_ask
    
    @property
    def spread(self) -> float:
        return 1.0 - self.combined_cost
    
    @property
    def is_profitable(self) -> bool:
        return self.spread > 0
    
    @property
    def min_liquidity(self) -> float:
        return min(self.up_liquidity, self.down_liquidity)


class FlashSniperV1:
    """
    Flash Sniper Strategy v1.0
    
    Replicates Account88888's aggressive flash market accumulation strategy.
    
    Core Logic:
    1. Monitor 15-min crypto flash markets
    2. When UP_ask + DOWN_ask < 0.998, execute immediately
    3. Buy equal amounts of both tokens
    4. Hold until market resolution (guaranteed $1.00 payout)
    
    Key Differences from Internal Arb:
    - Lower profit threshold (0.2% vs 1%)
    - Higher frequency (100 trades/min vs 10)
    - Aggressive execution (no waiting for confirmation)
    """
    
    def __init__(
        self,
        config: FlashSniperConfig,
        order_executor,  # OrderExecutor instance
        market_scanner,  # MarketScanner instance
        risk_manager,    # RiskManager instance
    ):
        self.config = config
        self.executor = order_executor
        self.scanner = market_scanner
        self.risk = risk_manager
        
        self._running = False
        self._trades_this_minute = 0
        self._last_trade_time = 0.0
        self._daily_pnl = 0.0
        
    async def start(self):
        """Start the flash sniper strategy loop."""
        logger.info("Starting Flash Sniper V1...")
        self._running = True
        
        while self._running:
            try:
                await self._scan_and_snipe()
                await asyncio.sleep(0.05)  # 50ms polling
            except Exception as e:
                logger.error(f"Flash sniper error: {e}")
                await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the strategy gracefully."""
        self._running = False
        logger.info("Flash Sniper V1 stopped.")
    
    async def _scan_and_snipe(self):
        """Main loop: scan for opportunities and execute."""
        
        # Check rate limits
        if not self._can_trade():
            return
        
        # Get active flash markets
        markets = await self.scanner.get_flash_markets(
            asset_filter=self.config.allowed_assets,
            min_time_remaining=self.config.min_time_to_expiry_minutes,
            max_time_remaining=self.config.max_time_to_expiry_minutes,
        )
        
        for market in markets:
            opportunity = await self._evaluate_market(market)
            
            if opportunity and self._is_valid_opportunity(opportunity):
                await self._execute_snipe(opportunity)
    
    async def _evaluate_market(self, market) -> Optional[MarketOpportunity]:
        """Evaluate a market for snipe opportunity."""
        # Fetch real-time order book for both tokens
        up_book = await self.executor.get_order_book(market.up_token_id)
        down_book = await self.executor.get_order_book(market.down_token_id)
        
        if not up_book or not down_book:
            return None
        
        # Get best ask prices
        up_ask = up_book.best_ask_price
        down_ask = down_book.best_ask_price
        
        if up_ask is None or down_ask is None:
            return None
        
        return MarketOpportunity(
            market_id=market.id,
            event_slug=market.slug,
            up_token_id=market.up_token_id,
            down_token_id=market.down_token_id,
            up_ask=up_ask,
            down_ask=down_ask,
            up_liquidity=up_book.best_ask_size,
            down_liquidity=down_book.best_ask_size,
            expires_at=market.expires_at,
        )
    
    def _is_valid_opportunity(self, opp: MarketOpportunity) -> bool:
        """Validate opportunity against config constraints."""
        
        # Check profitability
        if opp.combined_cost > self.config.max_combined_cost:
            return False
        
        if opp.spread < self.config.min_spread:
            return False
        
        # Check liquidity (need enough for base position)
        required_per_side = self.config.base_position_usdc
        if opp.up_liquidity < required_per_side or opp.down_liquidity < required_per_side:
            return False
        
        # Check risk limits
        if not self.risk.can_open_position(required_per_side * 2):
            return False
        
        return True
    
    async def _execute_snipe(self, opp: MarketOpportunity):
        """Execute a simultaneous buy of UP and DOWN tokens."""
        import time
        
        logger.info(
            "Executing snipe",
            market=opp.event_slug,
            spread=f"{opp.spread:.4f}",
            cost=f"{opp.combined_cost:.4f}",
        )
        
        position_size = self._calculate_position_size(opp)
        
        # Calculate token amounts
        up_amount = position_size / opp.up_ask
        down_amount = position_size / opp.down_ask
        
        # Execute both orders simultaneously (parallel)
        up_task = self.executor.place_market_order(
            token_id=opp.up_token_id,
            side="BUY",
            amount=position_size,
            order_type="FOK" if self.config.use_fok_orders else "GTC",
        )
        
        down_task = self.executor.place_market_order(
            token_id=opp.down_token_id,
            side="BUY", 
            amount=position_size,
            order_type="FOK" if self.config.use_fok_orders else "GTC",
        )
        
        # Wait for both
        results = await asyncio.gather(up_task, down_task, return_exceptions=True)
        
        up_result, down_result = results
        
        # Log results
        if isinstance(up_result, Exception) or isinstance(down_result, Exception):
            logger.error(f"Snipe failed: UP={up_result}, DOWN={down_result}")
        else:
            total_cost = (up_result.avg_price * up_result.filled_size + 
                         down_result.avg_price * down_result.filled_size)
            expected_payout = min(up_result.filled_size, down_result.filled_size)
            
            logger.info(
                "Snipe executed",
                total_cost=total_cost,
                expected_payout=expected_payout,
                expected_profit=expected_payout - total_cost,
            )
        
        self._last_trade_time = time.time()
        self._trades_this_minute += 1
    
    def _calculate_position_size(self, opp: MarketOpportunity) -> float:
        """Calculate optimal position size based on liquidity and config."""
        
        # Start with base position
        size = self.config.base_position_usdc
        
        # Scale up if spread is good
        if opp.spread > 0.01:  # 1%+ spread
            size = min(size * 2, self.config.max_position_usdc)
        
        # Limit by available liquidity
        max_by_liquidity = opp.min_liquidity * 0.5  # Only take 50% of book
        size = min(size, max_by_liquidity)
        
        return size
    
    def _can_trade(self) -> bool:
        """Check if we can execute another trade."""
        import time
        
        # Check daily loss limit
        if self._daily_pnl < -self.config.max_daily_loss_usdc:
            return False
        
        # Check rate limit
        if self._trades_this_minute >= self.config.max_trades_per_minute:
            return False
        
        # Check minimum interval
        elapsed = time.time() - self._last_trade_time
        if elapsed < self.config.min_interval_seconds:
            return False
        
        return True
