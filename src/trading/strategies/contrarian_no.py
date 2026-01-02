"""
🔮 CONTRARIAN NO STRATEGY - Production Version
===============================================
"Nothing Ever Happens" - Exploit sensationalism bias.

Based on reverse-engineering tsybka's trading patterns:
- 5.48 trades/hour (low frequency, high conviction)
- 88% delta-neutral ratio
- Mixed crypto/politics focus
- Only 4 open positions (concentrated)

Core Logic:
Buy NO tokens on sensational markets where retail overbuys YES on fear/hope.
78% of markets resolve to NO - fade the hysteria.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

from .base_strategy import (
    BaseStrategy,
    MarketData,
    TradeSignal,
    SignalType,
)

logger = logging.getLogger(__name__)


class ContrarianNoStrategy(BaseStrategy):
    """
    Contrarian NO Strategy - Fade the sensationalism.
    
    Targets markets with viral/fear-driven titles where:
    - YES price is 10-40% (overpriced by retail panic)
    - Historical base rate is much lower
    - Expected resolution is NO
    """
    
    # Keywords indicating sensationalism (fear/hope-driven)
    SENSATIONAL_KEYWORDS = [
        # Apocalyptic
        "nuclear", "war", "invasion", "attack", "bomb",
        "alien", "ufo", "disclosure", "extinction",
        
        # Financial Doom
        "crash", "collapse", "depression", "bankrupt",
        "bank run", "default", "hyperinflation",
        
        # Political Drama
        "resign", "impeach", "indicted", "arrested",
        "assassin", "coup", "martial law",
        
        # Crypto/Tech Hype
        "new ath", "all-time high", "100k", "1 million",
        "agi", "singularity",
        
        # Celebrity Drama
        "dies", "dead", "divorce", "scandal",
    ]
    
    def __init__(
        self,
        paper_mode: bool = True,
        stake_size: float = 200.0,  # $200 base bet (larger positions)
        min_yes_price: float = 0.08,  # YES must be > 8%
        max_yes_price: float = 0.40,  # YES must be < 40%
        min_volume: float = 5000.0,  # Minimum 24h volume
        max_daily_trades: int = 10,  # Low frequency (tsybka style)
        **kwargs
    ):
        super().__init__(
            strategy_id="CONTRARIAN_NO",
            paper_mode=paper_mode,
            stake_size=stake_size,
            max_daily_trades=max_daily_trades,
            **kwargs
        )
        
        self.min_yes_price = min_yes_price
        self.max_yes_price = max_yes_price
        self.min_volume = min_volume
        
        # Compile keyword pattern
        escaped = [re.escape(kw) for kw in self.SENSATIONAL_KEYWORDS]
        self._keyword_pattern = re.compile(
            r'\b(' + '|'.join(escaped) + r')\b',
            re.IGNORECASE
        )
    
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Evaluate market for contrarian NO opportunity.
        
        Logic:
        1. Check for sensational keywords in title
        2. Verify YES price is in target range (10-40%)
        3. Calculate expected value based on 78% NO base rate
        4. Generate signal if EV positive
        """
        
        # Find sensational keywords
        keywords_found = self._find_keywords(market.question)
        if not keywords_found:
            return None
        
        # Check volume threshold
        if market.volume_24h < self.min_volume:
            return None
        
        # Check YES price range
        yes_price = market.yes_price
        
        if yes_price < self.min_yes_price:
            # YES already too low - no edge
            return None
        
        if yes_price > self.max_yes_price:
            # YES too high - might actually happen
            return None
        
        # Calculate expected value
        # Base rate: 78% of sensational markets resolve NO
        prob_no = 0.78
        no_price = 1.0 - yes_price
        
        # EV = P(win) * payout - P(lose) * stake
        payout_if_win = 1.0 - no_price  # Profit per dollar
        ev = (prob_no * payout_if_win) - ((1 - prob_no) * no_price)
        
        if ev <= 0:
            return None
        
        # Calculate confidence based on price dislocation
        # Lower YES price = higher confidence (market correctly skeptical)
        # Higher YES price = lower confidence (need more edge)
        confidence = 0.5 + (0.4 - yes_price)  # 0.5 to 0.82
        
        logger.info(
            f"🔮 CONTRARIAN opportunity: {market.question[:50]}... "
            f"Keywords: {keywords_found}, YES: {yes_price:.2%}, EV: {ev:.4f}"
        )
        
        return TradeSignal(
            strategy_id=self.strategy_id,
            signal_type=SignalType.BUY,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            outcome="NO",  # Always buy NO
            entry_price=no_price,
            stake=self.stake_size,
            confidence=min(0.85, max(0.55, confidence)),
            expected_value=ev * self.stake_size,
            trigger_reason=f"contrarian_no: keywords={keywords_found}, yes={yes_price:.2%}",
            signal_data={
                "keywords": keywords_found,
                "yes_price": yes_price,
                "no_price": no_price,
                "expected_value": ev,
                "base_rate_no": prob_no,
                "type": "contrarian_no",
            }
        )
    
    def _find_keywords(self, text: str) -> List[str]:
        """Find sensational keywords in text."""
        matches = self._keyword_pattern.findall(text)
        return list(set(match.lower() for match in matches))
    
    def get_config(self) -> Dict[str, Any]:
        """Return strategy configuration."""
        return {
            "strategy_id": self.strategy_id,
            "type": "contrarian_no",
            "min_yes_price": self.min_yes_price,
            "max_yes_price": self.max_yes_price,
            "min_volume": self.min_volume,
            "stake_size": self.stake_size,
            "max_daily_trades": self.max_daily_trades,
            "paper_mode": self.paper_mode,
            "keyword_count": len(self.SENSATIONAL_KEYWORDS),
        }
