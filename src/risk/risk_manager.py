"""Risk manager for position and exposure limits."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

from src.config.settings import Settings
from src.models import ArbitrageOpportunity, Position

logger = structlog.get_logger(__name__)


@dataclass
class RiskLimits:
    """Current risk limits configuration."""

    max_position_size_usdc: float = 1000.0
    max_total_exposure_usdc: float = 5000.0
    max_daily_loss_usdc: float = 500.0
    max_positions_per_market: int = 1
    max_total_positions: int = 10
    min_profit_threshold: float = 0.04
    position_timeout_seconds: float = 900.0  # 15 minutes


@dataclass
class RiskMetrics:
    """Current risk metrics."""

    total_exposure: float = 0.0
    daily_pnl: float = 0.0
    open_positions: int = 0
    positions_per_market: dict[str, int] = field(default_factory=dict)
    daily_trades: int = 0
    is_trading_halted: bool = False
    halt_reason: str = ""


class RiskManager:
    """
    Manages trading risk and enforces limits.
    
    Monitors exposure, P&L, and position limits to protect capital.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize risk manager.

        Args:
            settings: Application settings
        """
        self.limits = RiskLimits(
            max_position_size_usdc=settings.max_position_size_usdc,
            max_total_exposure_usdc=settings.max_total_exposure_usdc,
            max_daily_loss_usdc=settings.max_daily_loss_usdc,
            min_profit_threshold=settings.min_profit_threshold,
        )

        self._metrics = RiskMetrics()
        self._daily_pnl_start: datetime = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self._trade_log: list[dict[str, Any]] = []

    @property
    def metrics(self) -> RiskMetrics:
        """Get current risk metrics."""
        return self._metrics

    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed."""
        return not self._metrics.is_trading_halted

    def update_exposure(self, positions: list[Position]) -> None:
        """
        Update exposure metrics from current positions.

        Args:
            positions: List of current open positions
        """
        self._metrics.total_exposure = sum(p.total_cost for p in positions)
        self._metrics.open_positions = len(positions)

        # Count positions per market
        market_counts: dict[str, int] = {}
        for p in positions:
            market_counts[p.market_id] = market_counts.get(p.market_id, 0) + 1
        self._metrics.positions_per_market = market_counts

    def update_daily_pnl(self, realized_pnl: float) -> None:
        """
        Update daily P&L.

        Args:
            realized_pnl: Total realized P&L for today
        """
        # Reset if new day
        now = datetime.now()
        if now.date() > self._daily_pnl_start.date():
            self._daily_pnl_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._metrics.daily_pnl = 0.0
            self._metrics.daily_trades = 0
            self._trade_log.clear()

            # Resume trading if halted for daily loss
            if self._metrics.halt_reason == "daily_loss_limit":
                self._metrics.is_trading_halted = False
                self._metrics.halt_reason = ""

        self._metrics.daily_pnl = realized_pnl

        # Check daily loss limit
        if self._metrics.daily_pnl < -self.limits.max_daily_loss_usdc:
            self.halt_trading("daily_loss_limit")

    def can_open_position(
        self,
        opportunity: ArbitrageOpportunity,
        proposed_size: float,
    ) -> tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            opportunity: The opportunity to trade
            proposed_size: Proposed position size in USDC

        Returns:
            Tuple of (allowed, reason)
        """
        # Check if trading is halted
        if self._metrics.is_trading_halted:
            return False, f"Trading halted: {self._metrics.halt_reason}"

        # Check total exposure
        new_exposure = self._metrics.total_exposure + proposed_size
        if new_exposure > self.limits.max_total_exposure_usdc:
            return False, (
                f"Would exceed exposure limit: {new_exposure:.2f} > "
                f"{self.limits.max_total_exposure_usdc:.2f}"
            )

        # Check position size limit
        if proposed_size > self.limits.max_position_size_usdc:
            return False, (
                f"Position size exceeds limit: {proposed_size:.2f} > "
                f"{self.limits.max_position_size_usdc:.2f}"
            )

        # Check positions per market
        market_id = opportunity.market.id
        current_market_positions = self._metrics.positions_per_market.get(market_id, 0)
        if current_market_positions >= self.limits.max_positions_per_market:
            return False, f"Max positions reached for market {market_id}"

        # Check total positions
        if self._metrics.open_positions >= self.limits.max_total_positions:
            return False, f"Max total positions reached: {self.limits.max_total_positions}"

        # Check profit threshold
        if opportunity.profit_per_contract < self.limits.min_profit_threshold:
            return False, (
                f"Profit below threshold: {opportunity.profit_per_contract:.4f} < "
                f"{self.limits.min_profit_threshold:.4f}"
            )

        return True, "OK"

    def calculate_position_size(
        self,
        opportunity: ArbitrageOpportunity,
    ) -> float:
        """
        Calculate optimal position size for an opportunity.

        Args:
            opportunity: The opportunity to size

        Returns:
            Recommended position size in USDC
        """
        # Available exposure
        remaining_exposure = max(
            0,
            self.limits.max_total_exposure_usdc - self._metrics.total_exposure,
        )

        # Max by configuration
        config_max = self.limits.max_position_size_usdc

        # Max by liquidity
        liquidity_max = opportunity.max_contracts * opportunity.total_cost

        # Take minimum of all constraints
        size = min(remaining_exposure, config_max, liquidity_max)

        # Apply a safety factor based on profit margin
        # Higher profit = more confidence = larger size
        profit_factor = min(1.0, opportunity.profit_per_contract / 0.10)
        size *= profit_factor

        return max(0, size)

    def record_trade(self, trade_info: dict[str, Any]) -> None:
        """Record a trade for tracking."""
        trade_info["timestamp"] = datetime.now().isoformat()
        self._trade_log.append(trade_info)
        self._metrics.daily_trades += 1

    def halt_trading(self, reason: str) -> None:
        """Halt all trading."""
        self._metrics.is_trading_halted = True
        self._metrics.halt_reason = reason
        logger.warning("Trading halted", reason=reason)

    def resume_trading(self) -> None:
        """Resume trading after halt."""
        self._metrics.is_trading_halted = False
        self._metrics.halt_reason = ""
        logger.info("Trading resumed")

    def check_position_timeout(self, positions: list[Position]) -> list[Position]:
        """
        Check for positions that have timed out.

        Args:
            positions: List of positions to check

        Returns:
            List of timed-out positions
        """
        now = datetime.now()
        timeout = timedelta(seconds=self.limits.position_timeout_seconds)
        timed_out = []

        for position in positions:
            age = now - position.created_at
            if age > timeout:
                timed_out.append(position)
                logger.warning(
                    "Position timed out",
                    position_id=position.id,
                    age_seconds=age.total_seconds(),
                )

        return timed_out

    def get_risk_summary(self) -> dict[str, Any]:
        """Get a summary of current risk state."""
        return {
            "is_trading_allowed": self.is_trading_allowed,
            "halt_reason": self._metrics.halt_reason,
            "total_exposure": self._metrics.total_exposure,
            "exposure_utilization": (
                self._metrics.total_exposure / self.limits.max_total_exposure_usdc * 100
                if self.limits.max_total_exposure_usdc > 0 else 0
            ),
            "daily_pnl": self._metrics.daily_pnl,
            "daily_loss_limit": self.limits.max_daily_loss_usdc,
            "open_positions": self._metrics.open_positions,
            "max_positions": self.limits.max_total_positions,
            "daily_trades": self._metrics.daily_trades,
        }
