"""
🎯 STRATEGY B: MICROSTRUCTURE SNIPER
=====================================
Captures rebotes after irrational price drops in short-term markets.

Inspired by @gabagool22's approach - aggressive market making after panic sells.

Logic:
1. Filter: Markets expiring < 24h with > $10k volume
2. Detect: Price drops > 15% in 10 minutes
3. Confirm: Volume spike > 2x average (panic selling)
4. Action: Limit order 1% above best bid

Features:
- Rolling price buffer (deque) for 10-min window
- Volume spike detection
- Market making with aggressive limit orders
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

from .base_strategy import BaseStrategy, MarketData, TradeSignal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class PriceBuffer:
    """Rolling buffer for price history."""
    prices: deque = field(default_factory=lambda: deque(maxlen=60))  # 10 min at 10s intervals
    volumes: deque = field(default_factory=lambda: deque(maxlen=60))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=60))
    
    def add(self, price: float, volume: float, timestamp: datetime = None):
        self.prices.append(price)
        self.volumes.append(volume)
        self.timestamps.append(timestamp or datetime.utcnow())
    
    @property
    def mean_price(self) -> float:
        if not self.prices:
            return 0
        return sum(self.prices) / len(self.prices)
    
    @property
    def mean_volume(self) -> float:
        if not self.volumes:
            return 0
        return sum(self.volumes) / len(self.volumes)
    
    @property
    def max_price(self) -> float:
        return max(self.prices) if self.prices else 0
    
    @property
    def min_price(self) -> float:
        return min(self.prices) if self.prices else 0
    
    def recent_volume(self, minutes: int = 2) -> float:
        """Get volume in last N minutes."""
        if not self.volumes or not self.timestamps:
            return 0
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        total = 0
        for vol, ts in zip(reversed(self.volumes), reversed(self.timestamps)):
            if ts >= cutoff:
                total += vol
            else:
                break
        return total


class SniperStrategy(BaseStrategy):
    """
    Microstructure sniper - captures panic selling rebounds.
    
    Parameters:
        price_drop_threshold: Min drop to trigger (default: 15%)
        volume_spike_multiplier: Volume must be Nx average (default: 2x)
        lookback_minutes: Window for price analysis (default: 10)
        max_expiry_hours: Only markets expiring within N hours (default: 24)
        min_volume_24h: Minimum 24h volume to consider (default: $10k)
        bid_offset_pct: How much above best bid to place order (default: 1%)
    """
    
    STRATEGY_ID = "SNIPER_MICRO_V1"
    
    def __init__(
        self,
        paper_mode: bool = True,
        stake_size: float = 5.0,
        price_drop_threshold: float = 0.15,  # 15%
        volume_spike_multiplier: float = 2.0,
        lookback_minutes: int = 10,
        max_expiry_hours: float = 24,
        min_volume_24h: float = 10000,
        bid_offset_pct: float = 0.01,  # 1%
        **kwargs
    ):
        super().__init__(
            strategy_id=self.STRATEGY_ID,
            paper_mode=paper_mode,
            stake_size=stake_size,
            max_daily_trades=30,
            **kwargs
        )
        
        self.price_drop_threshold = price_drop_threshold
        self.volume_spike_multiplier = volume_spike_multiplier
        self.lookback_minutes = lookback_minutes
        self.max_expiry_hours = max_expiry_hours
        self.min_volume_24h = min_volume_24h
        self.bid_offset_pct = bid_offset_pct
        
        # Price buffers per market
        self._buffers: Dict[str, PriceBuffer] = {}
        
        # Cooldown to avoid multiple signals on same event
        self._cooldowns: Dict[str, datetime] = {}
        self._cooldown_minutes = 30
    
    def get_config(self) -> Dict:
        return {
            "strategy_id": self.STRATEGY_ID,
            "type": "SNIPER",
            "price_drop_threshold": f"{self.price_drop_threshold:.0%}",
            "volume_spike_multiplier": f"{self.volume_spike_multiplier}x",
            "lookback_minutes": self.lookback_minutes,
            "max_expiry_hours": self.max_expiry_hours,
            "min_volume_24h": f"${self.min_volume_24h:,.0f}",
            "stake_size": self.stake_size,
            "paper_mode": self.paper_mode,
        }
    
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Check for sniper opportunity.
        
        Steps:
        1. Filter by expiry and volume
        2. Update price buffer
        3. Detect price drop anomaly
        4. Confirm volume spike
        5. Generate limit order signal
        """
        # Filter: Expiry check
        if market.hours_to_expiry is not None:
            if market.hours_to_expiry > self.max_expiry_hours:
                return None
            if market.hours_to_expiry < 0.5:  # Too close to expiry
                return None
        
        # Filter: Volume check
        if market.volume_24h < self.min_volume_24h:
            return None
        
        # Check cooldown
        if self._is_on_cooldown(market.condition_id):
            return None
        
        # Get or create buffer
        buffer = self._get_buffer(market.condition_id)
        
        # Update buffer with current data
        # Estimate recent volume from price history length
        recent_vol = market.volume_1h if hasattr(market, 'volume_1h') else market.volume_24h / 24
        buffer.add(market.yes_price, recent_vol)
        
        # Need enough data
        if len(buffer.prices) < 6:  # At least 1 minute of data
            return None
        
        # Detect price drop
        mean_price = buffer.mean_price
        current_price = market.yes_price
        
        if mean_price == 0:
            return None
        
        price_drop = (mean_price - current_price) / mean_price
        
        # Not a significant drop
        if price_drop < self.price_drop_threshold:
            return None
        
        # Check volume spike
        recent_volume = buffer.recent_volume(minutes=2)
        avg_volume = buffer.mean_volume
        
        volume_multiple = recent_volume / avg_volume if avg_volume > 0 else 0
        
        if volume_multiple < self.volume_spike_multiplier:
            # Price dropped but no panic selling volume
            return None
        
        # 🎯 ANOMALY DETECTED - Generate signal
        
        # Calculate entry price (1% above best bid for aggressive fill)
        best_bid = market.best_bid or current_price * 0.98
        entry_price = best_bid * (1 + self.bid_offset_pct)
        
        # Calculate expected rebound
        expected_rebound = mean_price  # Target return to mean
        expected_profit_pct = (expected_rebound - entry_price) / entry_price
        
        # Set cooldown
        self._set_cooldown(market.condition_id)
        
        signal = TradeSignal(
            strategy_id=self.strategy_id,
            signal_type=SignalType.BUY,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            outcome="YES",  # Betting on rebound
            entry_price=entry_price,
            stake=self.stake_size,
            confidence=min(0.85, price_drop * 2 + volume_multiple * 0.1),
            expected_value=self.stake_size * expected_profit_pct,
            trigger_reason=f"panic_drop_{price_drop:.0%}_vol_{volume_multiple:.1f}x",
            signal_data={
                "price_drop_pct": price_drop,
                "mean_price_10min": mean_price,
                "current_price": current_price,
                "best_bid": best_bid,
                "volume_spike": volume_multiple,
                "recent_volume_2min": recent_volume,
                "avg_volume": avg_volume,
                "expected_rebound": expected_rebound,
                "expected_profit_pct": expected_profit_pct,
                "hours_to_expiry": market.hours_to_expiry,
                "order_type": "LIMIT",
                "limit_price": entry_price,
            },
            snapshot_data=market.to_snapshot()
        )
        
        logger.info(
            f"🎯 SNIPER: {price_drop:.0%} drop, {volume_multiple:.1f}x volume | "
            f"Entry: ${entry_price:.3f} | Target: ${expected_rebound:.3f} | "
            f"Market: {market.question[:40]}..."
        )
        
        return signal
    
    def _get_buffer(self, condition_id: str) -> PriceBuffer:
        """Get or create price buffer for market."""
        if condition_id not in self._buffers:
            self._buffers[condition_id] = PriceBuffer()
        return self._buffers[condition_id]
    
    def _is_on_cooldown(self, condition_id: str) -> bool:
        """Check if market is on cooldown."""
        if condition_id not in self._cooldowns:
            return False
        
        cooldown_until = self._cooldowns[condition_id]
        return datetime.utcnow() < cooldown_until
    
    def _set_cooldown(self, condition_id: str):
        """Set cooldown for market."""
        self._cooldowns[condition_id] = datetime.utcnow() + timedelta(minutes=self._cooldown_minutes)
    
    def cleanup_old_buffers(self, max_age_hours: int = 24):
        """Remove buffers for expired/inactive markets."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for cid, buffer in self._buffers.items():
            if buffer.timestamps and buffer.timestamps[-1] < cutoff:
                to_remove.append(cid)
        
        for cid in to_remove:
            del self._buffers[cid]
            if cid in self._cooldowns:
                del self._cooldowns[cid]
        
        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old price buffers")
