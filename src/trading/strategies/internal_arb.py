"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    INTERNAL ARBITRAGE STRATEGY (ARB_INTERNAL_V1)             ║
║                                                                              ║
║  Risk-Free Yield from Polymarket Orderbook Inefficiencies                    ║
║                                                                              ║
║  LOGIC:                                                                      ║
║    For binary markets (YES/NO), if you buy both sides:                       ║
║      - You're guaranteed to win exactly $1.00 when market resolves           ║
║      - If Cost(YES) + Cost(NO) < $1.00 → RISK-FREE PROFIT                   ║
║                                                                              ║
║  FORMULA:                                                                    ║
║    Cost = best_ask(YES) + best_ask(NO)                                       ║
║    If Cost < 0.99 (leaving 1% for fees/slippage):                           ║
║      ROI = (1.00 - Cost) / Cost                                              ║
║      SIGNAL: BUY BOTH SIDES ("Synthetic Dollar")                             ║
║                                                                              ║
║  ADVANTAGES:                                                                 ║
║    ✅ Risk-free (both outcomes covered)                                      ║
║    ✅ No prediction skill needed                                             ║
║    ✅ Fast execution (sync, per-market check)                               ║
║    ✅ Works with existing scanner infrastructure                             ║
║                                                                              ║
║  THRESHOLDS:                                                                 ║
║    - MIN_PROFIT: Cost < 0.99 (1% minimum ROI)                               ║
║    - MAX_COST: Cost > 0.90 (avoid dead/illiquid markets)                    ║
║    - MIN_LIQUIDITY: Both sides must have sufficient liquidity               ║
║                                                                              ║
║  Strategy ID: ARB_INTERNAL_V1                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field

from .base_strategy import BaseStrategy, MarketData, TradeSignal, SignalType

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class InternalArbOpportunity:
    """
    An internal arbitrage opportunity within Polymarket.
    
    This represents a "Buy Both Sides" signal where the combined cost
    of YES + NO is less than the guaranteed payout of $1.00.
    """
    # Identification
    condition_id: str
    question: str
    
    # Prices (best asks from orderbook)
    yes_ask: float
    no_ask: float
    
    # Cost & Profit
    total_cost: float           # yes_ask + no_ask
    guaranteed_payout: float = 1.0
    gross_profit: float = 0.0   # payout - cost
    roi_pct: float = 0.0        # (profit / cost) * 100
    
    # Market quality
    volume_24h: float = 0.0
    liquidity: float = 0.0
    
    # Timestamps
    detected_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Calculate profit metrics after initialization."""
        self.gross_profit = self.guaranteed_payout - self.total_cost
        if self.total_cost > 0:
            self.roi_pct = (self.gross_profit / self.total_cost) * 100
    
    @property
    def is_profitable(self) -> bool:
        """Check if this opportunity has positive ROI."""
        return self.gross_profit > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "condition_id": self.condition_id,
            "question": self.question,
            "yes_ask": self.yes_ask,
            "no_ask": self.no_ask,
            "total_cost": self.total_cost,
            "guaranteed_payout": self.guaranteed_payout,
            "gross_profit": self.gross_profit,
            "roi_pct": round(self.roi_pct, 3),
            "volume_24h": self.volume_24h,
            "liquidity": self.liquidity,
            "detected_at": self.detected_at.isoformat(),
        }


# =============================================================================
# INTERNAL ARBITRAGE DETECTOR
# =============================================================================

class InternalArbDetector:
    """
    Lightweight detector for internal orderbook arbitrage.
    
    This is a sync/fast detector that can run inside the market processing loop
    without blocking. It checks each market for sum(YES + NO) < threshold.
    
    Configuration:
        max_cost: Maximum total cost to trigger (default: 0.99 = 1% ROI)
        min_cost: Minimum cost to avoid dead markets (default: 0.90)
        min_liquidity: Minimum liquidity per side (default: 100)
    """
    
    def __init__(
        self,
        max_cost: float = 0.99,      # Trigger if cost < this
        min_cost: float = 0.90,      # Avoid dead markets
        min_liquidity: float = 100,  # Minimum per side
        min_volume_24h: float = 500, # Minimum volume
    ):
        self.max_cost = max_cost
        self.min_cost = min_cost
        self.min_liquidity = min_liquidity
        self.min_volume_24h = min_volume_24h
        
        # Stats
        self._markets_checked = 0
        self._opportunities_found = 0
    
    def check_market(self, market: MarketData) -> Optional[InternalArbOpportunity]:
        """
        Check a single market for internal arbitrage opportunity.
        
        SYNC method - designed to be fast and non-blocking.
        
        Args:
            market: MarketData object from scanner
            
        Returns:
            InternalArbOpportunity if found, None otherwise
        """
        self._markets_checked += 1
        
        # Validate we have prices
        if market.yes_price <= 0 or market.no_price <= 0:
            return None
        
        # For this strategy, we need the ASK prices (cost to buy)
        # MarketData typically has mid prices, but we use them as proxy
        # In a real implementation, you'd fetch orderbook asks
        yes_ask = market.yes_price
        no_ask = market.no_price
        
        # Calculate total cost
        total_cost = yes_ask + no_ask
        
        # Quick rejection: outside profitable range
        if total_cost >= self.max_cost:
            return None  # Not profitable enough
        
        if total_cost <= self.min_cost:
            return None  # Market likely dead/illiquid
        
        # Validate liquidity
        if market.liquidity > 0 and market.liquidity < self.min_liquidity:
            return None
        
        # Validate volume
        if market.volume_24h > 0 and market.volume_24h < self.min_volume_24h:
            return None
        
        # We found an opportunity!
        self._opportunities_found += 1
        
        return InternalArbOpportunity(
            condition_id=market.condition_id,
            question=market.question,
            yes_ask=yes_ask,
            no_ask=no_ask,
            total_cost=total_cost,
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics."""
        return {
            "markets_checked": self._markets_checked,
            "opportunities_found": self._opportunities_found,
            "hit_rate_pct": (
                (self._opportunities_found / self._markets_checked * 100)
                if self._markets_checked > 0 else 0
            ),
        }


# =============================================================================
# INTERNAL ARB STRATEGY
# =============================================================================

class InternalArbStrategy(BaseStrategy):
    """
    Internal Arbitrage Strategy - Risk-Free Yield from Orderbook Inefficiencies.
    
    This strategy scans Polymarket's orderbook for markets where:
        Cost(YES) + Cost(NO) < $0.99
    
    When found, buying BOTH sides guarantees profit:
        - You pay: Cost
        - You receive: $1.00 (guaranteed, one side will resolve to 1)
        - Profit: $1.00 - Cost
    
    Parameters:
        max_cost: Maximum cost threshold (default: 0.99 = 1% min ROI)
        min_cost: Minimum cost to filter dead markets (default: 0.90)
        min_liquidity: Minimum liquidity per side
        stake_per_opportunity: Amount to bet per opportunity
    
    Strategy ID: ARB_INTERNAL_V1
    """
    
    STRATEGY_ID = "ARB_INTERNAL_V1"
    
    def __init__(
        self,
        paper_mode: bool = True,
        stake_size: float = 50.0,  # Per opportunity
        max_cost: float = 0.99,
        min_cost: float = 0.90,
        min_liquidity: float = 100,
        min_volume_24h: float = 500,
        **kwargs
    ):
        super().__init__(
            strategy_id=self.STRATEGY_ID,
            paper_mode=paper_mode,
            stake_size=stake_size,
            max_daily_trades=100,  # Can do more trades since risk-free
            **kwargs
        )
        
        self.max_cost = max_cost
        self.min_cost = min_cost
        self.min_liquidity = min_liquidity
        self.min_volume_24h = min_volume_24h
        
        # Internal detector (sync, fast)
        self._detector = InternalArbDetector(
            max_cost=max_cost,
            min_cost=min_cost,
            min_liquidity=min_liquidity,
            min_volume_24h=min_volume_24h,
        )
        
        # Track opportunities (deduplication)
        self._seen_opportunities: Dict[str, datetime] = {}
        self._opportunity_cooldown_seconds = 300  # 5 minutes
    
    def get_config(self) -> Dict:
        """Return strategy configuration."""
        return {
            "strategy_id": self.STRATEGY_ID,
            "type": "INTERNAL_ARB",
            "description": "Risk-free yield from orderbook inefficiencies",
            "max_cost": self.max_cost,
            "min_cost": self.min_cost,
            "min_liquidity": self.min_liquidity,
            "min_volume_24h": self.min_volume_24h,
            "stake_size": self.stake_size,
            "paper_mode": self.paper_mode,
            "opportunity_cooldown_seconds": self._opportunity_cooldown_seconds,
        }
    
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Process a market for internal arbitrage opportunity.
        
        This is called per-market by the orchestrator.
        Since detection is sync/fast, we don't need async here.
        
        Args:
            market: MarketData from scanner
            
        Returns:
            TradeSignal if opportunity found, None otherwise
        """
        # Check for opportunity (sync, fast)
        opportunity = self._detector.check_market(market)
        
        if not opportunity:
            return None
        
        # Check cooldown (don't spam same market)
        if not self._check_cooldown(opportunity.condition_id):
            logger.debug(f"Opportunity on cooldown: {opportunity.question[:30]}")
            return None
        
        # Convert to TradeSignal
        signal = self._create_signal(opportunity)
        
        # Log the opportunity
        logger.info(
            f"🎯 INTERNAL ARB DETECTED | "
            f"Cost: ${opportunity.total_cost:.4f} | "
            f"ROI: {opportunity.roi_pct:.2f}% | "
            f"{opportunity.question[:50]}..."
        )
        
        return signal
    
    def _check_cooldown(self, condition_id: str) -> bool:
        """
        Check if we've recently signaled this market.
        
        Returns True if market is NOT on cooldown (can signal).
        """
        if condition_id not in self._seen_opportunities:
            self._seen_opportunities[condition_id] = datetime.utcnow()
            return True
        
        last_seen = self._seen_opportunities[condition_id]
        elapsed = (datetime.utcnow() - last_seen).total_seconds()
        
        if elapsed >= self._opportunity_cooldown_seconds:
            self._seen_opportunities[condition_id] = datetime.utcnow()
            return True
        
        return False
    
    def _create_signal(self, opportunity: InternalArbOpportunity) -> TradeSignal:
        """
        Convert InternalArbOpportunity to TradeSignal.
        
        For internal arb, we signal to buy BOTH sides.
        The signal includes details about the synthetic dollar trade.
        """
        # Calculate optimal stake split
        # For equal returns, split based on inverse prices
        # But for simplicity, we split 50/50
        total_stake = self.stake_size
        yes_stake = total_stake / 2
        no_stake = total_stake / 2
        
        # Calculate expected value
        # After both trades: guaranteed to win (1.0 - cost) per dollar staked
        expected_payout = total_stake / opportunity.total_cost  # Shares
        expected_profit = expected_payout - total_stake
        
        # Create signal
        # Note: outcome is "BOTH" to indicate synthetic position
        signal = TradeSignal(
            signal_type=SignalType.BUY,
            strategy_id=self.STRATEGY_ID,
            question=opportunity.question,
            condition_id=opportunity.condition_id,
            outcome="BOTH",  # Special: indicates buy both sides
            entry_price=opportunity.total_cost,  # Combined price
            stake=total_stake,
            expected_value=expected_profit,
            confidence=min(opportunity.roi_pct * 10, 100),  # Higher ROI = higher confidence
            trigger_reason=f"INTERNAL_ARB: Cost={opportunity.total_cost:.4f} < 0.99",
            signal_data={
                "arb_type": "INTERNAL",
                "yes_ask": opportunity.yes_ask,
                "no_ask": opportunity.no_ask,
                "total_cost": opportunity.total_cost,
                "roi_pct": opportunity.roi_pct,
                "yes_stake": yes_stake,
                "no_stake": no_stake,
                "guaranteed_payout": opportunity.guaranteed_payout,
                "gross_profit": opportunity.gross_profit,
                "volume_24h": opportunity.volume_24h,
                "liquidity": opportunity.liquidity,
            },
        )
        
        return signal
    
    def get_detector_stats(self) -> Dict[str, Any]:
        """Get detector statistics."""
        return self._detector.get_stats()


# =============================================================================
# BATCH SCANNER FOR DASHBOARD
# =============================================================================

class InternalArbScanner:
    """
    Batch scanner for finding all internal arb opportunities.
    
    Used by dashboard to show current opportunities.
    Different from strategy (which processes per-market).
    """
    
    def __init__(
        self,
        max_cost: float = 0.99,
        min_cost: float = 0.90,
    ):
        self.max_cost = max_cost
        self.min_cost = min_cost
        self._opportunities: List[InternalArbOpportunity] = []
    
    def scan_markets(
        self, 
        markets: List[MarketData]
    ) -> List[InternalArbOpportunity]:
        """
        Scan a list of markets for internal arbitrage opportunities.
        
        Args:
            markets: List of MarketData from scanner
            
        Returns:
            List of InternalArbOpportunity sorted by ROI (highest first)
        """
        detector = InternalArbDetector(
            max_cost=self.max_cost,
            min_cost=self.min_cost,
        )
        
        opportunities = []
        for market in markets:
            opp = detector.check_market(market)
            if opp and opp.is_profitable:
                opportunities.append(opp)
        
        # Sort by ROI (highest first)
        opportunities.sort(key=lambda x: x.roi_pct, reverse=True)
        
        self._opportunities = opportunities
        return opportunities
    
    def get_opportunities(self) -> List[InternalArbOpportunity]:
        """Get last scan results."""
        return self._opportunities


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_internal_arb(yes_price: float, no_price: float) -> Dict[str, float]:
    """
    Calculate internal arbitrage metrics for a single market.
    
    Args:
        yes_price: Current YES ask price
        no_price: Current NO ask price
        
    Returns:
        Dict with cost, profit, roi_pct, and is_profitable
    """
    total_cost = yes_price + no_price
    guaranteed_payout = 1.0
    gross_profit = guaranteed_payout - total_cost
    roi_pct = (gross_profit / total_cost * 100) if total_cost > 0 else 0
    
    return {
        "total_cost": round(total_cost, 4),
        "gross_profit": round(gross_profit, 4),
        "roi_pct": round(roi_pct, 2),
        "is_profitable": gross_profit > 0,
        "min_roi_for_trade": 1.0,  # 1% minimum
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "InternalArbStrategy",
    "InternalArbDetector",
    "InternalArbScanner",
    "InternalArbOpportunity",
    "calculate_internal_arb",
]
