"""
🎯 STRATEGY B: MICROSTRUCTURE SNIPER (DUAL MODE)
=================================================
Captures profits from irrational price movements using two complementary modes:

MODE 1: CRASH DETECTOR (Reactive)
---------------------------------
Captures rebounds after panic selling drops.
- Trigger: Price drops > 15% in 5 minutes
- Confirm: Volume spike > 2x average
- Action: Aggressive limit order 1% above best bid

MODE 2: STINK BID (Proactive)  
-----------------------------
Places "trap" orders at ridiculously low prices waiting for flash crashes.
- Setup: Place limit orders at $0.02-$0.05 on high-volume markets
- Fill: When best_ask touches our price during panic
- Exit: Immediate sell at rebounded price for massive ROI

Inspired by @gabagool22's approach and liquidity trap strategies.

Features:
- Dual mode operation (reactive + proactive)
- Rolling price buffer for crash detection
- Active stink bid management with 30-min rotation
- ROI calculation for filled traps
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import uuid

from .base_strategy import BaseStrategy, MarketData, TradeSignal, SignalType

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class SniperMode(Enum):
    """Sniper operation modes."""
    CRASH_DETECTOR = "CRASH_DETECTOR"
    STINK_BID = "STINK_BID"


@dataclass
class PriceBuffer:
    """Rolling buffer for price history with configurable window."""
    prices: deque = field(default_factory=lambda: deque(maxlen=30))  # 5 min at 10s intervals
    volumes: deque = field(default_factory=lambda: deque(maxlen=30))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=30))
    
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
    def max_price(self) -> float:
        return max(self.prices) if self.prices else 0
    
    @property
    def min_price(self) -> float:
        return min(self.prices) if self.prices else 0
    
    @property
    def mean_volume(self) -> float:
        if not self.volumes:
            return 0
        return sum(self.volumes) / len(self.volumes)
    
    def recent_volume(self, minutes: int = 2) -> float:
        """Get volume in last N minutes."""
        if not self.volumes or not self.timestamps:
            return 0
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        total = 0
        for vol, ts in zip(reversed(list(self.volumes)), reversed(list(self.timestamps))):
            if ts >= cutoff:
                total += vol
            else:
                break
        return total
    
    def price_change_pct(self, minutes: int = 5) -> float:
        """Calculate price change over last N minutes."""
        if len(self.prices) < 2:
            return 0
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        old_prices = []
        
        for price, ts in zip(self.prices, self.timestamps):
            if ts <= cutoff:
                old_prices.append(price)
        
        if not old_prices:
            old_price = self.prices[0]
        else:
            old_price = sum(old_prices) / len(old_prices)
        
        current_price = self.prices[-1]
        
        if old_price == 0:
            return 0
        
        return (current_price - old_price) / old_price


@dataclass
class StinkBid:
    """
    Represents a proactive low-price limit order waiting for fill.
    
    A "stink bid" is a limit order placed at an unreasonably low price,
    waiting for a flash crash or panic sell to fill it.
    """
    bid_id: str
    condition_id: str
    token_id: Optional[str]
    question: str
    
    # Order details
    bid_price: float          # Our low bid price ($0.02-$0.05)
    target_exit: float        # Expected exit price after rebound
    stake: float              # USD allocated
    size: float               # Shares we'd get if filled
    
    # State
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = None
    status: str = "ACTIVE"    # ACTIVE, FILLED, EXPIRED, CANCELLED
    
    # Fill tracking
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    
    # Market context at creation
    market_price_at_creation: float = 0.0
    volume_24h: float = 0.0
    hours_to_expiry: float = 0.0
    
    def __post_init__(self):
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(minutes=30)
    
    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at
    
    @property
    def potential_roi(self) -> float:
        """Calculate potential ROI if filled and exited at target."""
        if self.bid_price == 0:
            return 0
        return (self.target_exit - self.bid_price) / self.bid_price
    
    @property
    def age_minutes(self) -> float:
        return (datetime.utcnow() - self.created_at).total_seconds() / 60


# =============================================================================
# SNIPER STRATEGY (DUAL MODE)
# =============================================================================

class SniperStrategy(BaseStrategy):
    """
    Microstructure sniper with dual operation modes.
    
    MODE 1: CRASH DETECTOR (Reactive)
    - Monitors price buffers for sudden drops
    - Triggers on 15% drop + volume spike
    - Places aggressive limit order for rebound
    
    MODE 2: STINK BID (Proactive)
    - Places trap orders at $0.02-$0.05 on high-volume markets
    - Monitors for fills when best_ask touches bid price
    - Captures massive ROI on flash crash fills
    
    Parameters:
        # Crash Detector params
        price_drop_threshold: Min drop to trigger (default: 15%)
        volume_spike_multiplier: Volume must be Nx average (default: 2x)
        lookback_minutes: Window for price analysis (default: 5)
        
        # Stink Bid params
        stink_bid_min_price: Minimum stink bid price (default: $0.02)
        stink_bid_max_price: Maximum stink bid price (default: $0.05)
        stink_bid_min_volume: Minimum 24h volume for stink bids (default: $50k)
        stink_bid_ttl_minutes: Time before rotating bid (default: 30)
        max_active_stink_bids: Maximum concurrent stink bids (default: 10)
        
        # Common params
        max_expiry_hours: Only markets expiring within N hours (default: 24)
        min_volume_24h: Minimum 24h volume (default: $10k)
    """
    
    STRATEGY_ID = "SNIPER_MICRO_V1"
    
    def __init__(
        self,
        paper_mode: bool = True,
        stake_size: float = 5.0,
        # Crash Detector params
        price_drop_threshold: float = 0.15,
        volume_spike_multiplier: float = 2.0,
        lookback_minutes: int = 5,
        bid_offset_pct: float = 0.01,
        # Stink Bid params
        stink_bid_min_price: float = 0.02,
        stink_bid_max_price: float = 0.05,
        stink_bid_min_volume: float = 50000,
        stink_bid_ttl_minutes: int = 30,
        max_active_stink_bids: int = 10,
        stink_bid_stake: float = 10.0,
        # Common params
        max_expiry_hours: float = 24,
        min_volume_24h: float = 10000,
        **kwargs
    ):
        super().__init__(
            strategy_id=self.STRATEGY_ID,
            paper_mode=paper_mode,
            stake_size=stake_size,
            max_daily_trades=50,
            **kwargs
        )
        
        # Crash Detector config
        self.price_drop_threshold = price_drop_threshold
        self.volume_spike_multiplier = volume_spike_multiplier
        self.lookback_minutes = lookback_minutes
        self.bid_offset_pct = bid_offset_pct
        
        # Stink Bid config
        self.stink_bid_min_price = stink_bid_min_price
        self.stink_bid_max_price = stink_bid_max_price
        self.stink_bid_min_volume = stink_bid_min_volume
        self.stink_bid_ttl_minutes = stink_bid_ttl_minutes
        self.max_active_stink_bids = max_active_stink_bids
        self.stink_bid_stake = stink_bid_stake
        
        # Common config
        self.max_expiry_hours = max_expiry_hours
        self.min_volume_24h = min_volume_24h
        
        # =====================================================================
        # STATE MANAGEMENT
        # =====================================================================
        
        # Crash Detector state
        self._price_buffers: Dict[str, PriceBuffer] = {}
        self._crash_cooldowns: Dict[str, datetime] = {}
        self._crash_cooldown_minutes = 30
        
        # Stink Bid state
        self._active_stink_bids: Dict[str, StinkBid] = {}  # bid_id -> StinkBid
        self._stink_bid_by_market: Dict[str, str] = {}     # condition_id -> bid_id
        self._filled_stink_bids: List[StinkBid] = []
        self._markets_considered: Set[str] = set()         # Markets we've evaluated
        
        # Statistics
        self._stats = {
            "crash_signals": 0,
            "stink_bids_placed": 0,
            "stink_bids_filled": 0,
            "stink_bids_expired": 0,
            "total_stink_profit": 0.0,
        }
    
    def get_config(self) -> Dict:
        return {
            "strategy_id": self.STRATEGY_ID,
            "type": "SNIPER_DUAL_MODE",
            "modes": ["CRASH_DETECTOR", "STINK_BID"],
            
            # Crash Detector
            "crash_drop_threshold": f"{self.price_drop_threshold:.0%}",
            "crash_volume_spike": f"{self.volume_spike_multiplier}x",
            "crash_lookback_minutes": self.lookback_minutes,
            
            # Stink Bid
            "stink_bid_range": f"${self.stink_bid_min_price:.2f}-${self.stink_bid_max_price:.2f}",
            "stink_bid_min_volume": f"${self.stink_bid_min_volume:,.0f}",
            "stink_bid_ttl": f"{self.stink_bid_ttl_minutes}min",
            "max_stink_bids": self.max_active_stink_bids,
            
            # Common
            "max_expiry_hours": self.max_expiry_hours,
            "paper_mode": self.paper_mode,
            
            # Current state
            "active_stink_bids": len(self._active_stink_bids),
        }
    
    # =========================================================================
    # MAIN PROCESSING
    # =========================================================================
    
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Process market through both modes.
        
        Priority:
        1. Check if any stink bid was filled (highest ROI)
        2. Check for crash detector signal
        3. Consider placing new stink bid
        """
        # Maintenance: Clean expired stink bids
        self._cleanup_expired_stink_bids()
        
        # =====================================================================
        # MODE 2: STINK BID - Check for fills first (highest priority)
        # =====================================================================
        stink_signal = await self._check_stink_bid_fill(market)
        if stink_signal:
            return stink_signal
        
        # =====================================================================
        # COMMON FILTERS
        # =====================================================================
        
        # Expiry check
        if market.hours_to_expiry is not None:
            if market.hours_to_expiry > self.max_expiry_hours:
                return None
            if market.hours_to_expiry < 0.5:  # Too close
                return None
        
        # Volume check (minimum for crash detector)
        if market.volume_24h < self.min_volume_24h:
            return None
        
        # =====================================================================
        # MODE 1: CRASH DETECTOR
        # =====================================================================
        crash_signal = await self._process_crash_detector(market)
        if crash_signal:
            return crash_signal
        
        # =====================================================================
        # MODE 2: STINK BID - Consider placing new bid
        # =====================================================================
        await self._consider_stink_bid(market)
        
        return None
    
    # =========================================================================
    # MODE 1: CRASH DETECTOR
    # =========================================================================
    
    async def _process_crash_detector(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Reactive mode: Detect sudden price crashes and buy the dip.
        """
        # Check cooldown
        if self._is_on_crash_cooldown(market.condition_id):
            return None
        
        # Get or create price buffer
        buffer = self._get_price_buffer(market.condition_id)
        
        # Update buffer
        recent_vol = market.volume_1h if market.volume_1h else market.volume_24h / 24
        buffer.add(market.yes_price, recent_vol)
        
        # Need enough data (at least 30 seconds)
        if len(buffer.prices) < 3:
            return None
        
        # Calculate price change over lookback window
        price_change = buffer.price_change_pct(minutes=self.lookback_minutes)
        
        # We want negative change (drop)
        if price_change > -self.price_drop_threshold:
            return None
        
        price_drop = abs(price_change)
        
        # Check volume spike (confirms panic selling)
        recent_volume = buffer.recent_volume(minutes=2)
        avg_volume = buffer.mean_volume
        volume_multiple = recent_volume / avg_volume if avg_volume > 0 else 0
        
        if volume_multiple < self.volume_spike_multiplier:
            return None
        
        # 🚨 CRASH DETECTED - Generate signal
        
        # Calculate entry price (aggressive limit above bid)
        best_bid = market.best_bid or market.yes_price * 0.98
        entry_price = best_bid * (1 + self.bid_offset_pct)
        
        # Expected rebound to mean
        expected_rebound = buffer.mean_price
        expected_profit_pct = (expected_rebound - entry_price) / entry_price if entry_price > 0 else 0
        
        # Set cooldown
        self._set_crash_cooldown(market.condition_id)
        
        self._stats["crash_signals"] += 1
        
        signal = TradeSignal(
            strategy_id=self.strategy_id,
            signal_type=SignalType.BUY,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            outcome="YES",
            entry_price=entry_price,
            stake=self.stake_size,
            confidence=min(0.85, price_drop * 2 + volume_multiple * 0.1),
            expected_value=self.stake_size * expected_profit_pct,
            trigger_reason=f"crash_drop_{price_drop:.0%}_vol_{volume_multiple:.1f}x",
            signal_data={
                "mode": SniperMode.CRASH_DETECTOR.value,
                "price_drop_pct": price_drop,
                "mean_price_5min": buffer.mean_price,
                "current_price": market.yes_price,
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
            f"🚨 CRASH: {price_drop:.0%} drop, {volume_multiple:.1f}x vol | "
            f"Entry: ${entry_price:.3f} → Target: ${expected_rebound:.3f} | "
            f"{market.question[:40]}..."
        )
        
        return signal
    
    # =========================================================================
    # MODE 2: STINK BID
    # =========================================================================
    
    async def _consider_stink_bid(self, market: MarketData) -> None:
        """
        Proactive mode: Consider placing a stink bid on this market.
        
        Criteria:
        - High volume (> $50k)
        - Expiring soon (< 24h)
        - No existing stink bid on this market
        - Haven't hit max concurrent bids
        """
        # Already have a stink bid on this market
        if market.condition_id in self._stink_bid_by_market:
            return
        
        # Already evaluated this market this session
        if market.condition_id in self._markets_considered:
            return
        
        self._markets_considered.add(market.condition_id)
        
        # Check if we can place more bids
        if len(self._active_stink_bids) >= self.max_active_stink_bids:
            return
        
        # Volume requirement (higher than crash detector)
        if market.volume_24h < self.stink_bid_min_volume:
            return
        
        # Must have expiry data
        if market.hours_to_expiry is None or market.hours_to_expiry > self.max_expiry_hours:
            return
        
        # Don't place stink bids on markets that are already very cheap
        if market.yes_price < self.stink_bid_max_price:
            return
        
        # ✅ Market qualifies - Place stink bid
        await self._place_stink_bid(market)
    
    async def _place_stink_bid(self, market: MarketData) -> None:
        """
        Place a stink bid (simulated limit order at low price).
        
        The bid price is calculated based on:
        - Distance from current price (more distance = lower probability but higher ROI)
        - Market volatility (more volatile = higher bid price)
        """
        # Calculate optimal stink bid price
        # Closer to stink_bid_max_price for more liquid markets
        liquidity_factor = min(1.0, market.volume_24h / 200000)  # Normalize to 200k
        
        bid_price = self.stink_bid_min_price + (
            (self.stink_bid_max_price - self.stink_bid_min_price) * liquidity_factor
        )
        bid_price = round(bid_price, 3)
        
        # Target exit is the market's average price (assume it rebounds)
        target_exit = market.yes_price * 0.9  # Slightly below current (conservative)
        
        # Calculate position size
        size = self.stink_bid_stake / bid_price
        
        # Create stink bid
        bid_id = f"STINK-{int(datetime.utcnow().timestamp())}-{uuid.uuid4().hex[:6]}"
        
        stink_bid = StinkBid(
            bid_id=bid_id,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            bid_price=bid_price,
            target_exit=target_exit,
            stake=self.stink_bid_stake,
            size=size,
            market_price_at_creation=market.yes_price,
            volume_24h=market.volume_24h,
            hours_to_expiry=market.hours_to_expiry or 0,
        )
        
        # Register
        self._active_stink_bids[bid_id] = stink_bid
        self._stink_bid_by_market[market.condition_id] = bid_id
        self._stats["stink_bids_placed"] += 1
        
        logger.info(
            f"🪤 STINK BID: ${bid_price:.3f} on {market.question[:40]}... | "
            f"Current: ${market.yes_price:.3f} | ROI if filled: {stink_bid.potential_roi:.0%}"
        )
    
    async def _check_stink_bid_fill(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Check if any stink bid was filled by market price action.
        
        Fill condition: best_ask <= our bid_price
        (In a real scenario, our limit order would execute)
        """
        bid_id = self._stink_bid_by_market.get(market.condition_id)
        if not bid_id:
            return None
        
        stink_bid = self._active_stink_bids.get(bid_id)
        if not stink_bid or stink_bid.status != "ACTIVE":
            return None
        
        # Check if market price touched our bid
        # Use best_ask for sell pressure, or yes_price as fallback
        market_ask = market.best_ask or market.yes_price
        
        if market_ask > stink_bid.bid_price:
            return None
        
        # 🎉 STINK BID FILLED!
        
        # Update stink bid state
        stink_bid.status = "FILLED"
        stink_bid.filled_at = datetime.utcnow()
        stink_bid.fill_price = market_ask  # Actual fill price (might be better than our bid)
        
        # Move to filled list
        self._filled_stink_bids.append(stink_bid)
        del self._active_stink_bids[bid_id]
        del self._stink_bid_by_market[market.condition_id]
        
        self._stats["stink_bids_filled"] += 1
        
        # Calculate profit (immediate exit simulation)
        # We buy at fill_price, sell at current rebound price
        actual_fill = stink_bid.fill_price
        exit_price = market.yes_price  # Current price after the flash crash recovery
        
        # If price hasn't rebounded yet, use a conservative estimate
        if exit_price <= actual_fill * 1.1:
            exit_price = stink_bid.target_exit
        
        actual_size = stink_bid.stake / actual_fill
        revenue = actual_size * exit_price
        profit = revenue - stink_bid.stake
        roi = profit / stink_bid.stake
        
        self._stats["total_stink_profit"] += profit
        
        # Generate signal (represents the completed stink bid trade)
        signal = TradeSignal(
            strategy_id=self.strategy_id,
            signal_type=SignalType.BUY,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            outcome="YES",
            entry_price=actual_fill,
            stake=stink_bid.stake,
            confidence=0.95,  # High confidence - it's already filled!
            expected_value=profit,
            trigger_reason=f"stink_bid_filled_roi_{roi:.0%}",
            signal_data={
                "mode": SniperMode.STINK_BID.value,
                "bid_id": bid_id,
                "bid_price": stink_bid.bid_price,
                "fill_price": actual_fill,
                "exit_price": exit_price,
                "size": actual_size,
                "profit": profit,
                "roi": roi,
                "time_to_fill_minutes": stink_bid.age_minutes,
                "market_price_at_creation": stink_bid.market_price_at_creation,
                "flash_crash_depth": (stink_bid.market_price_at_creation - actual_fill) / stink_bid.market_price_at_creation,
                "order_type": "LIMIT_FILLED",
            },
            snapshot_data=market.to_snapshot()
        )
        
        logger.info(
            f"🎉 STINK FILLED: ${actual_fill:.3f} → ${exit_price:.3f} | "
            f"Profit: ${profit:+.2f} ({roi:.0%} ROI) | "
            f"Time: {stink_bid.age_minutes:.1f}min | "
            f"{market.question[:35]}..."
        )
        
        return signal
    
    def _cleanup_expired_stink_bids(self) -> None:
        """Remove expired stink bids and rotate capital."""
        expired = []
        
        for bid_id, stink_bid in list(self._active_stink_bids.items()):
            if stink_bid.is_expired:
                expired.append(bid_id)
                stink_bid.status = "EXPIRED"
                
                # Remove from tracking
                if stink_bid.condition_id in self._stink_bid_by_market:
                    del self._stink_bid_by_market[stink_bid.condition_id]
                
                del self._active_stink_bids[bid_id]
                self._stats["stink_bids_expired"] += 1
                
                logger.debug(
                    f"⏰ STINK EXPIRED: {stink_bid.question[:40]}... | "
                    f"Age: {stink_bid.age_minutes:.0f}min"
                )
        
        # Allow re-evaluation of markets with expired bids
        for bid_id in expired:
            # Markets can be reconsidered after bid expires
            pass
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def _get_price_buffer(self, condition_id: str) -> PriceBuffer:
        """Get or create price buffer for market."""
        if condition_id not in self._price_buffers:
            self._price_buffers[condition_id] = PriceBuffer()
        return self._price_buffers[condition_id]
    
    def _is_on_crash_cooldown(self, condition_id: str) -> bool:
        """Check if market is on crash detector cooldown."""
        if condition_id not in self._crash_cooldowns:
            return False
        return datetime.utcnow() < self._crash_cooldowns[condition_id]
    
    def _set_crash_cooldown(self, condition_id: str):
        """Set cooldown for crash detector on market."""
        self._crash_cooldowns[condition_id] = (
            datetime.utcnow() + timedelta(minutes=self._crash_cooldown_minutes)
        )
    
    def get_stink_bid_summary(self) -> Dict:
        """Get summary of stink bid activity."""
        return {
            "active_bids": len(self._active_stink_bids),
            "filled_bids": len(self._filled_stink_bids),
            "expired_bids": self._stats["stink_bids_expired"],
            "total_profit": self._stats["total_stink_profit"],
            "fill_rate": (
                self._stats["stink_bids_filled"] / 
                max(1, self._stats["stink_bids_placed"])
            ) * 100,
            "active_details": [
                {
                    "bid_id": bid.bid_id,
                    "question": bid.question[:50],
                    "bid_price": bid.bid_price,
                    "market_price": bid.market_price_at_creation,
                    "age_minutes": bid.age_minutes,
                    "potential_roi": bid.potential_roi,
                }
                for bid in self._active_stink_bids.values()
            ]
        }
    
    def get_stats(self) -> Dict:
        """Override to include sniper-specific stats."""
        base_stats = super().get_stats()
        base_stats.update({
            "crash_signals": self._stats["crash_signals"],
            "stink_bids_placed": self._stats["stink_bids_placed"],
            "stink_bids_filled": self._stats["stink_bids_filled"],
            "stink_bids_expired": self._stats["stink_bids_expired"],
            "stink_total_profit": self._stats["total_stink_profit"],
            "active_stink_bids": len(self._active_stink_bids),
        })
        return base_stats
    
    def cleanup_old_buffers(self, max_age_hours: int = 24):
        """Remove stale price buffers to free memory."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for cid, buffer in self._price_buffers.items():
            if buffer.timestamps and buffer.timestamps[-1] < cutoff:
                to_remove.append(cid)
        
        for cid in to_remove:
            del self._price_buffers[cid]
            if cid in self._crash_cooldowns:
                del self._crash_cooldowns[cid]
        
        if to_remove:
            logger.debug(f"🧹 Cleaned {len(to_remove)} old price buffers")
    
    def reset_daily(self):
        """Reset daily counters and clear evaluated markets."""
        super().reset_daily()
        self._markets_considered.clear()
        # Note: Active stink bids persist across days until filled/expired
