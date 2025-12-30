"""Dislocation detector for detecting sudden spread changes."""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PricePoint:
    """A single price observation."""

    timestamp: datetime
    up_price: float
    down_price: float
    spread: float = field(init=False)

    def __post_init__(self) -> None:
        self.spread = self.up_price + self.down_price


@dataclass
class DislocationEvent:
    """Represents a detected price dislocation."""

    token_id: str
    direction: str  # "widening" or "narrowing"
    old_spread: float
    new_spread: float
    spread_change: float
    spread_change_pct: float
    timestamp: datetime


class DislocationDetector:
    """
    Detects sudden price dislocations (spread changes) in markets.
    
    The Jane Street strategy waits for one leg to be filled, then monitors for
    a "dislocation" - a sudden widening of the spread that makes the second
    leg more profitable.
    """

    def __init__(
        self,
        window_size: int = 20,
        dislocation_threshold_pct: float = 2.0,
        min_spread_change: float = 0.01,
        lookback_seconds: float = 60.0,
    ) -> None:
        """
        Initialize dislocation detector.

        Args:
            window_size: Number of price points to keep in rolling window
            dislocation_threshold_pct: Percentage change to consider a dislocation
            min_spread_change: Minimum absolute spread change to trigger
            lookback_seconds: How far back to look for average spread
        """
        self.window_size = window_size
        self.dislocation_threshold_pct = dislocation_threshold_pct
        self.min_spread_change = min_spread_change
        self.lookback_seconds = lookback_seconds

        # Price history per market
        self._price_history: dict[str, deque[PricePoint]] = {}
        
        # Last dislocation timestamps (to avoid duplicate alerts)
        self._last_dislocation: dict[str, datetime] = {}

    def update_price(
        self,
        market_id: str,
        up_price: float,
        down_price: float,
    ) -> DislocationEvent | None:
        """
        Update price and check for dislocation.

        Args:
            market_id: Market identifier
            up_price: Current UP token price
            down_price: Current DOWN token price

        Returns:
            DislocationEvent if dislocation detected, None otherwise
        """
        now = datetime.now()
        point = PricePoint(timestamp=now, up_price=up_price, down_price=down_price)

        # Initialize history if needed
        if market_id not in self._price_history:
            self._price_history[market_id] = deque(maxlen=self.window_size)

        history = self._price_history[market_id]
        history.append(point)

        # Need at least 2 points to detect change
        if len(history) < 2:
            return None

        # Calculate average spread over lookback period
        cutoff = now - timedelta(seconds=self.lookback_seconds)
        recent_points = [p for p in history if p.timestamp >= cutoff]

        if len(recent_points) < 2:
            return None

        # Exclude the latest point from average
        avg_spread = sum(p.spread for p in recent_points[:-1]) / len(recent_points[:-1])
        current_spread = point.spread

        # Calculate change
        spread_change = current_spread - avg_spread
        spread_change_pct = (spread_change / avg_spread * 100) if avg_spread > 0 else 0

        # Check if this qualifies as a dislocation
        if abs(spread_change_pct) < self.dislocation_threshold_pct:
            return None

        if abs(spread_change) < self.min_spread_change:
            return None

        # Avoid duplicate alerts within 5 seconds
        last = self._last_dislocation.get(market_id)
        if last and (now - last).total_seconds() < 5:
            return None

        self._last_dislocation[market_id] = now

        direction = "widening" if spread_change > 0 else "narrowing"
        event = DislocationEvent(
            token_id=market_id,
            direction=direction,
            old_spread=avg_spread,
            new_spread=current_spread,
            spread_change=spread_change,
            spread_change_pct=spread_change_pct,
            timestamp=now,
        )

        logger.info(
            "Dislocation detected",
            market_id=market_id,
            direction=direction,
            old_spread=f"{avg_spread:.4f}",
            new_spread=f"{current_spread:.4f}",
            change_pct=f"{spread_change_pct:.2f}%",
        )

        return event

    def get_spread_stats(self, market_id: str) -> dict[str, Any]:
        """
        Get spread statistics for a market.

        Args:
            market_id: Market identifier

        Returns:
            Dictionary with spread statistics
        """
        history = self._price_history.get(market_id)
        if not history or len(history) == 0:
            return {"error": "No price history"}

        spreads = [p.spread for p in history]
        up_prices = [p.up_price for p in history]
        down_prices = [p.down_price for p in history]

        return {
            "count": len(spreads),
            "current_spread": spreads[-1] if spreads else 0,
            "avg_spread": sum(spreads) / len(spreads),
            "min_spread": min(spreads),
            "max_spread": max(spreads),
            "spread_range": max(spreads) - min(spreads),
            "current_up": up_prices[-1] if up_prices else 0,
            "current_down": down_prices[-1] if down_prices else 0,
            "oldest_timestamp": history[0].timestamp.isoformat(),
            "latest_timestamp": history[-1].timestamp.isoformat(),
        }

    def clear_history(self, market_id: str | None = None) -> None:
        """
        Clear price history.

        Args:
            market_id: Specific market to clear, or None for all
        """
        if market_id:
            self._price_history.pop(market_id, None)
            self._last_dislocation.pop(market_id, None)
        else:
            self._price_history.clear()
            self._last_dislocation.clear()

    def is_favorable_dislocation(
        self,
        event: DislocationEvent,
        holding_side: str,
    ) -> bool:
        """
        Check if a dislocation is favorable for entering the second leg.

        A spread widening is favorable when we already hold one side
        and the other side becomes cheaper.

        Args:
            event: The dislocation event
            holding_side: "UP" or "DOWN" - the side we already hold

        Returns:
            True if dislocation is favorable for entering the opposite side
        """
        # If spread is widening (total cost going up), it means prices are moving apart
        # This could be favorable if the side we don't hold got cheaper relative to before
        # A narrowing spread (total cost going down) is always potentially favorable
        # because it means we can now complete the arbitrage cheaper

        if event.direction == "narrowing":
            # Spread narrowing = total cost decreased = potentially good for second leg
            return event.new_spread < 1.0  # Still within profitable range

        # For widening, we'd need more price-level detail to determine which side moved
        # For now, we'll be conservative and not consider widening favorable
        return False
