"""Data models for the trading system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.config.constants import MarketType, OutcomeType, PositionState


@dataclass
class TokenPair:
    """Represents a UP/DOWN token pair for a market."""

    up_token_id: str
    down_token_id: str
    up_price: float = 0.0
    down_price: float = 0.0
    up_liquidity: float = 0.0
    down_liquidity: float = 0.0

    @property
    def total_cost(self) -> float:
        """Total cost to buy both sides."""
        return self.up_price + self.down_price

    @property
    def profit_per_contract(self) -> float:
        """Profit per contract if both sides bought at current prices."""
        return 1.0 - self.total_cost

    @property
    def is_profitable(self) -> bool:
        """Check if arbitrage is profitable (total cost < $1)."""
        return self.total_cost < 1.0


@dataclass
class Market:
    """Represents a Polymarket market."""

    id: str
    condition_id: str
    question: str
    slug: str
    market_type: MarketType
    asset: str | None  # BTC, ETH, SOL for crypto markets
    tokens: TokenPair | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    volume: float = 0.0
    is_active: bool = True
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def time_to_close_seconds(self) -> float | None:
        """Seconds until market closes."""
        if not self.end_time:
            return None
        delta = self.end_time - datetime.now()
        return max(0, delta.total_seconds())

    @property
    def is_closed(self) -> bool:
        """Check if market is closed."""
        if not self.end_time:
            return False
        return datetime.now() >= self.end_time


@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity."""

    market: Market
    up_price: float
    down_price: float
    total_cost: float
    profit_per_contract: float
    up_liquidity: float
    down_liquidity: float
    max_contracts: float  # Limited by minimum liquidity
    timestamp: datetime = field(default_factory=datetime.now)
    score: float = 0.0  # Opportunity quality score

    @property
    def expected_profit(self) -> float:
        """Expected profit if max contracts are filled."""
        return self.profit_per_contract * self.max_contracts

    def calculate_score(self) -> float:
        """
        Calculate opportunity quality score (0-100).
        
        Factors:
        - Profit margin (higher = better)
        - Liquidity (higher = better)
        - Time to close (more time = better)
        """
        # Profit component (0-40 points)
        profit_score = min(40, self.profit_per_contract * 400)

        # Liquidity component (0-30 points)
        min_liquidity = min(self.up_liquidity, self.down_liquidity)
        liquidity_score = min(30, min_liquidity / 100)

        # Time component (0-30 points)
        time_to_close = self.market.time_to_close_seconds or 0
        time_score = min(30, time_to_close / 30)  # 30 points for 15+ minutes

        self.score = profit_score + liquidity_score + time_score
        return self.score


@dataclass
class Order:
    """Represents an order."""

    id: str | None = None
    market_id: str = ""
    token_id: str = ""
    side: str = "BUY"
    price: float = 0.0
    size: float = 0.0
    filled_size: float = 0.0
    status: str = "pending"
    order_type: str = "GTC"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    """Represents a trading position (both legs of an arbitrage)."""

    id: str
    market_id: str
    market: Market | None = None
    state: PositionState = PositionState.PENDING_ENTRY

    # UP leg
    up_token_id: str = ""
    up_contracts: float = 0.0
    up_avg_price: float = 0.0
    up_order_id: str | None = None

    # DOWN leg
    down_token_id: str = ""
    down_contracts: float = 0.0
    down_avg_price: float = 0.0
    down_order_id: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    settled_at: datetime | None = None

    # P&L
    total_cost: float = 0.0
    settlement_value: float | None = None
    realized_pnl: float | None = None

    @property
    def delta(self) -> float:
        """Position delta (UP contracts - DOWN contracts)."""
        return self.up_contracts - self.down_contracts

    @property
    def is_delta_neutral(self) -> bool:
        """Check if position is approximately delta neutral."""
        return abs(self.delta) < 0.01 * max(self.up_contracts, self.down_contracts, 1)

    @property
    def combined_avg_price(self) -> float:
        """Combined average price per contract pair."""
        return self.up_avg_price + self.down_avg_price

    @property
    def expected_profit_per_contract(self) -> float:
        """Expected profit per contract at settlement."""
        return 1.0 - self.combined_avg_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized P&L (assuming market settles at $1)."""
        min_contracts = min(self.up_contracts, self.down_contracts)
        return min_contracts * self.expected_profit_per_contract


@dataclass
class Trade:
    """Represents a filled trade."""

    id: str
    position_id: str
    order_id: str
    market_id: str
    token_id: str
    outcome_type: OutcomeType
    side: str
    price: float
    size: float
    fee: float
    executed_at: datetime = field(default_factory=datetime.now)


@dataclass
class PnLSnapshot:
    """Point-in-time P&L snapshot."""

    timestamp: datetime
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    open_positions: int
    total_exposure: float
    daily_trades: int
