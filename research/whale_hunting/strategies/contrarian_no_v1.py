"""
CONTRARIAN_NO_V1: "Nothing Ever Happens" Mean Reversion Strategy

This strategy exploits the Sensationalism Bias in prediction markets:
- 78% of markets resolve to NO
- Retail overbuys YES on fear/hope-driven viral events
- Smart money fades the hysteria

Thesis: Bet against low-probability viral events when the crowd panics.

Entry Triggers:
- Market contains sensational keywords (Nuclear, War, Crash, etc.)
- YES price spikes > 10% on volume surge
- Historical base rate for event type is < 5%

Exit Strategy:
- Mean reversion: Exit when YES price drops 30% from peak
- Time decay: Hold until market expiration if NO is winning
- Stop loss: Exit if YES > 50% (event becoming likely)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List
import asyncio
import re
import structlog

logger = structlog.get_logger(__name__)


class MarketCategory(Enum):
    """Categories of sensational markets to target."""
    APOCALYPTIC = "apocalyptic"      # Nuclear, War, Extinction
    FINANCIAL_DOOM = "financial"      # Crash, Collapse, Depression
    POLITICAL_DRAMA = "political"     # Resign, Impeach, Indicted
    TECH_HYPE = "tech"               # AGI, Singularity, Breakthrough
    CELEBRITY = "celebrity"           # Death, Scandal, Divorce
    CRYPTO = "crypto"                 # ATH, Flip, Moon


@dataclass
class ContrarianConfig:
    """Configuration for the Contrarian NO strategy."""
    
    # Keywords that trigger analysis (sensationalism indicators)
    sensational_keywords: List[str] = field(default_factory=lambda: [
        # Apocalyptic
        "nuclear", "war", "world war", "invasion", "attack", "bomb",
        "alien", "ufo", "disclosure", "extinction", "apocalypse",
        
        # Financial Doom
        "crash", "collapse", "depression", "recession", "bankrupt",
        "bank run", "default", "hyperinflation",
        
        # Political Drama  
        "resign", "impeach", "indicted", "arrested", "assassin",
        "coup", "martial law", "emergency",
        
        # Crypto/Tech Hype
        "new ath", "all-time high", "flip", "100k", "1 million",
        "agi", "singularity", "consciousness",
        
        # Celebrity
        "death", "dies", "dead", "divorce", "scandal",
    ])
    
    # Price thresholds
    min_yes_price: float = 0.05       # Don't touch if YES < 5% (already priced correctly)
    max_yes_price: float = 0.40       # Don't touch if YES > 40% (might be real)
    target_yes_price: float = 0.10    # Sweet spot: YES at 10-20%
    
    # Volume spike detection
    volume_spike_threshold: float = 3.0  # 3x normal volume = spike
    
    # Position sizing
    base_position_usdc: float = 100.0
    max_position_usdc: float = 1000.0
    kelly_fraction: float = 0.25      # Use 25% Kelly for safety
    
    # Risk management
    stop_loss_yes_price: float = 0.50  # Exit if YES goes above 50%
    take_profit_pct: float = 0.30      # Take profit if NO gains 30%
    max_holding_days: int = 30         # Force exit after 30 days
    
    # Portfolio limits
    max_open_positions: int = 10
    max_exposure_pct: float = 0.20     # Max 20% of portfolio in contrarian


@dataclass
class ContrarianOpportunity:
    """Represents a detected contrarian opportunity."""
    market_id: str
    title: str
    slug: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    volume_24h: float
    avg_volume: float
    category: MarketCategory
    keywords_matched: List[str]
    expires_at: datetime
    
    @property
    def volume_spike_ratio(self) -> float:
        if self.avg_volume == 0:
            return float('inf')
        return self.volume_24h / self.avg_volume
    
    @property
    def is_volume_spike(self) -> bool:
        return self.volume_spike_ratio > 3.0
    
    @property
    def expected_value(self) -> float:
        """
        Calculate expected value assuming 78% base rate for NO.
        EV = (Prob_NO * Payout_NO) - (Prob_YES * Loss)
        """
        prob_no = 0.78  # Historical base rate
        payout_no = 1.0 - self.no_price  # Profit if NO wins
        loss = self.no_price  # Loss if YES wins
        
        return (prob_no * payout_no) - ((1 - prob_no) * loss)


class ContrarianNoV1:
    """
    Contrarian NO Strategy v1.0
    
    "Nothing Ever Happens" - Fade the retail fear/greed.
    
    Core Logic:
    1. Scan for markets with sensational keywords
    2. Detect volume spikes (news-driven panic)
    3. Buy NO tokens when YES is overpriced (10-40%)
    4. Hold for mean reversion or expiration
    5. Stop loss if event starts looking real (YES > 50%)
    
    Edge Source:
    - Sensationalism Bias: Media amplifies unlikely events
    - Availability Heuristic: Recent news overweights probability
    - Mean Reversion: Panic spikes revert within 24-72h
    """
    
    def __init__(
        self,
        config: ContrarianConfig,
        order_executor,
        market_scanner,
        risk_manager,
    ):
        self.config = config
        self.executor = order_executor
        self.scanner = market_scanner
        self.risk = risk_manager
        
        self._running = False
        self._open_positions: dict[str, dict] = {}
        self._keyword_pattern = self._compile_keyword_pattern()
        
    def _compile_keyword_pattern(self) -> re.Pattern:
        """Compile regex pattern for keyword matching."""
        escaped = [re.escape(kw) for kw in self.config.sensational_keywords]
        pattern = r'\b(' + '|'.join(escaped) + r')\b'
        return re.compile(pattern, re.IGNORECASE)
    
    async def start(self):
        """Start the contrarian strategy loop."""
        logger.info("Starting Contrarian NO V1 - 'Nothing Ever Happens'")
        self._running = True
        
        while self._running:
            try:
                await self._scan_for_opportunities()
                await self._manage_positions()
                await asyncio.sleep(60)  # 1 minute polling (low frequency)
            except Exception as e:
                logger.error(f"Contrarian strategy error: {e}")
                await asyncio.sleep(300)  # 5 min backoff on error
    
    async def stop(self):
        """Stop the strategy gracefully."""
        self._running = False
        logger.info("Contrarian NO V1 stopped.")
    
    async def _scan_for_opportunities(self):
        """Scan for sensational markets with volume spikes."""
        
        # Get all active markets
        markets = await self.scanner.get_all_markets()
        
        for market in markets:
            # Check for keyword matches
            keywords_found = self._find_keywords(market.title)
            
            if not keywords_found:
                continue
            
            # Evaluate opportunity
            opp = await self._evaluate_market(market, keywords_found)
            
            if opp and self._is_valid_opportunity(opp):
                await self._execute_contrarian_bet(opp)
    
    def _find_keywords(self, title: str) -> List[str]:
        """Find sensational keywords in market title."""
        matches = self._keyword_pattern.findall(title)
        return list(set(match.lower() for match in matches))
    
    def _categorize_keywords(self, keywords: List[str]) -> MarketCategory:
        """Categorize the opportunity based on matched keywords."""
        apocalyptic = {"nuclear", "war", "invasion", "alien", "extinction"}
        financial = {"crash", "collapse", "depression", "bankrupt"}
        political = {"resign", "impeach", "indicted", "arrested"}
        
        matched_set = set(keywords)
        
        if matched_set & apocalyptic:
            return MarketCategory.APOCALYPTIC
        elif matched_set & financial:
            return MarketCategory.FINANCIAL_DOOM
        elif matched_set & political:
            return MarketCategory.POLITICAL_DRAMA
        else:
            return MarketCategory.CELEBRITY
    
    async def _evaluate_market(
        self, 
        market, 
        keywords: List[str]
    ) -> Optional[ContrarianOpportunity]:
        """Evaluate a market for contrarian opportunity."""
        
        # Get current prices
        yes_price = market.yes_price or 0.5
        no_price = 1.0 - yes_price
        
        # Get volume data (simplified - would need historical data)
        volume_24h = market.volume_24h or 0
        avg_volume = market.avg_daily_volume or volume_24h  # Fallback
        
        return ContrarianOpportunity(
            market_id=market.id,
            title=market.title,
            slug=market.slug,
            yes_token_id=market.yes_token_id,
            no_token_id=market.no_token_id,
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=volume_24h,
            avg_volume=avg_volume,
            category=self._categorize_keywords(keywords),
            keywords_matched=keywords,
            expires_at=market.expires_at,
        )
    
    def _is_valid_opportunity(self, opp: ContrarianOpportunity) -> bool:
        """Validate opportunity against strategy rules."""
        
        # Already have position in this market?
        if opp.market_id in self._open_positions:
            return False
        
        # Check price range
        if opp.yes_price < self.config.min_yes_price:
            logger.debug(f"Skipping {opp.slug}: YES too low ({opp.yes_price:.2%})")
            return False
        
        if opp.yes_price > self.config.max_yes_price:
            logger.debug(f"Skipping {opp.slug}: YES too high ({opp.yes_price:.2%})")
            return False
        
        # Check volume spike (optional but preferred)
        if not opp.is_volume_spike:
            logger.debug(f"Skipping {opp.slug}: No volume spike")
            # Still might be valid, just less ideal
            # return False  # Uncomment to require volume spike
        
        # Check expected value
        if opp.expected_value < 0:
            logger.debug(f"Skipping {opp.slug}: Negative EV")
            return False
        
        # Check position limits
        if len(self._open_positions) >= self.config.max_open_positions:
            return False
        
        # Check risk limits
        if not self.risk.can_open_position(self.config.base_position_usdc):
            return False
        
        return True
    
    async def _execute_contrarian_bet(self, opp: ContrarianOpportunity):
        """Execute a contrarian NO bet."""
        
        logger.info(
            "Executing contrarian bet",
            market=opp.title[:50],
            keywords=opp.keywords_matched,
            yes_price=f"{opp.yes_price:.2%}",
            category=opp.category.value,
            ev=f"{opp.expected_value:.4f}",
        )
        
        # Calculate position size using Kelly-inspired sizing
        position_size = self._calculate_position_size(opp)
        
        # Buy NO tokens
        result = await self.executor.place_market_order(
            token_id=opp.no_token_id,
            side="BUY",
            amount=position_size,
        )
        
        if result.success:
            self._open_positions[opp.market_id] = {
                "opportunity": opp,
                "entry_price": result.avg_price,
                "entry_time": datetime.utcnow(),
                "position_size": position_size,
                "tokens": result.filled_size,
            }
            logger.info(f"Opened contrarian position in {opp.slug}")
        else:
            logger.error(f"Failed to open position: {result}")
    
    def _calculate_position_size(self, opp: ContrarianOpportunity) -> float:
        """Calculate position size based on edge and Kelly criterion."""
        
        # Simplified Kelly: f* = (p*b - q) / b
        # where p = prob of winning, b = odds, q = prob of losing
        p = 0.78  # Base rate for NO
        b = (1.0 / opp.no_price) - 1  # Decimal odds - 1
        q = 1 - p
        
        kelly = (p * b - q) / b if b > 0 else 0
        kelly_adjusted = kelly * self.config.kelly_fraction
        
        # Convert to dollar amount
        bankroll = 10000  # TODO: Get actual bankroll
        kelly_size = bankroll * kelly_adjusted
        
        # Apply limits
        size = min(
            kelly_size,
            self.config.max_position_usdc,
            max(kelly_size, self.config.base_position_usdc)
        )
        
        return max(size, self.config.base_position_usdc)
    
    async def _manage_positions(self):
        """Monitor and manage open positions."""
        
        for market_id, position in list(self._open_positions.items()):
            opp = position["opportunity"]
            
            # Get current price
            current_yes_price = await self._get_current_yes_price(market_id)
            
            if current_yes_price is None:
                continue
            
            # Check stop loss
            if current_yes_price >= self.config.stop_loss_yes_price:
                logger.warning(
                    f"STOP LOSS triggered for {opp.slug}",
                    yes_price=f"{current_yes_price:.2%}",
                )
                await self._close_position(market_id, "stop_loss")
                continue
            
            # Check take profit (YES dropped significantly)
            entry_yes = opp.yes_price
            price_drop = (entry_yes - current_yes_price) / entry_yes
            
            if price_drop >= self.config.take_profit_pct:
                logger.info(
                    f"TAKE PROFIT triggered for {opp.slug}",
                    drop=f"{price_drop:.2%}",
                )
                await self._close_position(market_id, "take_profit")
                continue
            
            # Check time-based exit
            entry_time = position["entry_time"]
            days_held = (datetime.utcnow() - entry_time).days
            
            if days_held >= self.config.max_holding_days:
                logger.info(f"TIME EXIT for {opp.slug} after {days_held} days")
                await self._close_position(market_id, "time_exit")
    
    async def _get_current_yes_price(self, market_id: str) -> Optional[float]:
        """Get current YES price for a market."""
        # TODO: Implement actual price fetch
        return None
    
    async def _close_position(self, market_id: str, reason: str):
        """Close a position by selling NO tokens."""
        position = self._open_positions.get(market_id)
        
        if not position:
            return
        
        result = await self.executor.place_market_order(
            token_id=position["opportunity"].no_token_id,
            side="SELL",
            amount=position["tokens"],
        )
        
        if result.success:
            del self._open_positions[market_id]
            logger.info(f"Closed position {market_id}: {reason}")
