"""
🚀 FLASH SNIPER STRATEGY - Production Version
==============================================
Ultra-high-frequency strategy for 15-minute crypto flash markets.

Based on reverse-engineering Account88888's trading patterns:
- 15,700 trades/hour
- 0.0s median interval
- 100% BUY orders (both UP and DOWN)
- 100% crypto focus

Core Logic:
Buy both UP and DOWN tokens when combined cost < $1.00 for guaranteed profit.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import logging

from .base_strategy import (
    BaseStrategy,
    MarketData,
    TradeSignal,
    SignalType,
)

logger = logging.getLogger(__name__)


class FlashSniperStrategy(BaseStrategy):
    """
    Flash Sniper Strategy - Ultra-HFT for crypto flash markets.
    
    Targets 15-minute crypto flash markets where UP + DOWN < 1.00.
    Executes immediately when spread is detected.
    """
    
    # Keywords to identify flash markets
    FLASH_KEYWORDS = ["15-min", "15 min", "up or down", "flash", "minute"]
    CRYPTO_KEYWORDS = ["btc", "bitcoin", "eth", "ethereum", "sol", "solana", "xrp"]
    
    def __init__(
        self,
        paper_mode: bool = True,
        stake_size: float = 100.0,  # $100 per leg
        min_spread: float = 0.002,  # 0.2% minimum profit
        max_combined_cost: float = 0.998,  # Must be < $0.998
        max_daily_trades: int = 500,  # High frequency
        **kwargs
    ):
        super().__init__(
            strategy_id="FLASH_SNIPER",
            paper_mode=paper_mode,
            stake_size=stake_size,
            max_daily_trades=max_daily_trades,
            **kwargs
        )
        
        self.min_spread = min_spread
        self.max_combined_cost = max_combined_cost
        
        # Flash-specific tracking
        self._paired_markets: Dict[str, str] = {}  # condition_id -> pair_id
        
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Evaluate market for flash arbitrage opportunity.
        
        Logic:
        1. Check if this is a 15-minute crypto flash market
        2. Calculate combined cost (YES + NO)
        3. If cost < max_combined_cost, generate BUY signal
        """
        
        # Filter for flash crypto markets
        if not self._is_flash_market(market):
            return None
        
        # Calculate combined cost
        combined_cost = market.yes_price + market.no_price
        spread = 1.0 - combined_cost
        
        # Check if profitable
        if combined_cost >= self.max_combined_cost:
            return None
        
        if spread < self.min_spread:
            return None
        
        # Calculate expected value
        # Guaranteed $1.00 payout - combined cost = profit
        expected_profit = spread * self.stake_size
        
        logger.info(
            f"🎯 FLASH opportunity: {market.question[:50]}... "
            f"Cost: ${combined_cost:.4f}, Spread: {spread:.4f}"
        )
        
        return TradeSignal(
            strategy_id=self.strategy_id,
            signal_type=SignalType.BUY,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            outcome="YES",  # We buy BOTH sides, but log as YES
            entry_price=market.yes_price,
            stake=self.stake_size * 2,  # Both legs
            confidence=min(0.95, 0.5 + spread * 10),  # Higher spread = higher confidence
            expected_value=expected_profit,
            trigger_reason=f"flash_arb: cost={combined_cost:.4f}, spread={spread:.4f}",
            signal_data={
                "combined_cost": combined_cost,
                "spread": spread,
                "yes_price": market.yes_price,
                "no_price": market.no_price,
                "type": "flash_sniper",
            }
        )
    
    def _is_flash_market(self, market: MarketData) -> bool:
        """Check if market is a 15-minute crypto flash market."""
        question_lower = market.question.lower()
        
        # Must be crypto-related
        is_crypto = any(kw in question_lower for kw in self.CRYPTO_KEYWORDS)
        if not is_crypto:
            return False
        
        # Must be flash/short-term
        is_flash = any(kw in question_lower for kw in self.FLASH_KEYWORDS)
        
        # Also check expiry (if available)
        if market.hours_to_expiry is not None:
            is_flash = is_flash or market.hours_to_expiry <= 0.5  # 30 min or less
        
        return is_flash
    
    def get_config(self) -> Dict[str, Any]:
        """Return strategy configuration."""
        return {
            "strategy_id": self.strategy_id,
            "type": "flash_sniper",
            "min_spread": self.min_spread,
            "max_combined_cost": self.max_combined_cost,
            "stake_size": self.stake_size,
            "max_daily_trades": self.max_daily_trades,
            "paper_mode": self.paper_mode,
        }
