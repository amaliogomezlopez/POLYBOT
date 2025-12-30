"""Trading constants and configuration values."""

from dataclasses import dataclass
from enum import Enum


# Polymarket API Configuration
CHAIN_ID = 137  # Polygon Mainnet
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API_HOST = "https://gamma-api.polymarket.com"

# Market Configuration
MARKET_DURATION_MINUTES = 15
MARKET_CLOSE_BUFFER_SECONDS = 30  # Don't enter positions within 30s of close

# Target Assets for Flash Markets
TARGET_ASSETS = ["BTC", "ETH", "SOL"]

# Flash Market Keywords (for filtering)
FLASH_MARKET_KEYWORDS = [
    "15 minute",
    "15-minute",
    "15min",
    "flash",
    "up or down",
    "higher or lower",
]


class MarketType(str, Enum):
    """Types of markets we trade."""

    FLASH_15MIN = "flash_15min"
    DAILY = "daily"
    CUSTOM = "custom"


class Side(str, Enum):
    """Trading side."""

    BUY = "BUY"
    SELL = "SELL"


class OutcomeType(str, Enum):
    """Outcome type for binary markets."""

    UP = "UP"
    DOWN = "DOWN"
    YES = "YES"
    NO = "NO"


@dataclass(frozen=True)
class TradingLimits:
    """Default trading limits."""

    MIN_ORDER_SIZE_USDC: float = 1.0
    MAX_ORDER_SIZE_USDC: float = 10000.0
    MIN_PROFIT_CENTS: float = 0.01
    MAX_SLIPPAGE_PERCENT: float = 0.5


# Order Types
class OrderType(str, Enum):
    """Order types supported by Polymarket CLOB."""

    GTC = "GTC"  # Good Till Cancelled
    GTD = "GTD"  # Good Till Date
    FOK = "FOK"  # Fill Or Kill
    FAK = "FAK"  # Fill And Kill (partial fill allowed, rest cancelled)


# Position States
class PositionState(str, Enum):
    """Position lifecycle states."""

    PENDING_ENTRY = "pending_entry"  # Waiting for first leg
    PARTIAL = "partial"  # First leg filled, waiting for second
    COMPLETE = "complete"  # Both legs filled
    PENDING_EXIT = "pending_exit"  # Waiting for market settlement
    SETTLED = "settled"  # Market resolved, position closed


# Alert Types
class AlertType(str, Enum):
    """Types of alerts to send."""

    TRADE_EXECUTED = "trade_executed"
    OPPORTUNITY_FOUND = "opportunity_found"
    POSITION_SETTLED = "position_settled"
    ERROR = "error"
    WARNING = "warning"
    DAILY_SUMMARY = "daily_summary"


# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0
RETRY_BACKOFF_MULTIPLIER = 2.0

# WebSocket Configuration
WS_RECONNECT_DELAY_SECONDS = 5.0
WS_PING_INTERVAL_SECONDS = 30.0
WS_PING_TIMEOUT_SECONDS = 10.0

# Logging
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
