"""P&L tracker for real-time performance monitoring."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog

from src.models import PnLSnapshot, Position, Trade

logger = structlog.get_logger(__name__)


@dataclass
class DailyStats:
    """Daily trading statistics."""

    date: str
    trades: int = 0
    positions_opened: int = 0
    positions_closed: int = 0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    volume: float = 0.0
    avg_profit_per_trade: float = 0.0
    win_rate: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0


class PnLTracker:
    """
    Tracks P&L and performance metrics in real-time.
    
    Provides snapshots, daily aggregates, and historical data.
    """

    def __init__(self) -> None:
        """Initialize P&L tracker."""
        self._snapshots: list[PnLSnapshot] = []
        self._daily_stats: dict[str, DailyStats] = {}
        self._trade_pnl: list[float] = []  # P&L per completed trade
        self._last_snapshot: datetime | None = None
        self._snapshot_interval = timedelta(minutes=1)

    def record_snapshot(
        self,
        positions: list[Position],
        trades: list[Trade],
    ) -> PnLSnapshot | None:
        """
        Record a P&L snapshot.

        Args:
            positions: Current open positions
            trades: Recent trades

        Returns:
            PnLSnapshot if recorded, None if too soon
        """
        now = datetime.now()

        # Rate limit snapshots
        if self._last_snapshot:
            if now - self._last_snapshot < self._snapshot_interval:
                return None

        # Calculate metrics
        unrealized = sum(p.unrealized_pnl for p in positions if p.realized_pnl is None)
        realized = sum(p.realized_pnl or 0 for p in positions)
        total_exposure = sum(p.total_cost for p in positions if p.realized_pnl is None)

        snapshot = PnLSnapshot(
            timestamp=now,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
            total_pnl=unrealized + realized,
            open_positions=len([p for p in positions if p.realized_pnl is None]),
            total_exposure=total_exposure,
            daily_trades=len(trades),
        )

        self._snapshots.append(snapshot)
        self._last_snapshot = now

        # Keep only last 24 hours of snapshots
        cutoff = now - timedelta(hours=24)
        self._snapshots = [s for s in self._snapshots if s.timestamp > cutoff]

        return snapshot

    def record_trade_pnl(self, pnl: float) -> None:
        """Record P&L from a completed trade."""
        self._trade_pnl.append(pnl)
        self._update_daily_stats(pnl)

    def _update_daily_stats(self, pnl: float) -> None:
        """Update daily statistics with a new trade."""
        today = datetime.now().strftime("%Y-%m-%d")

        if today not in self._daily_stats:
            self._daily_stats[today] = DailyStats(date=today)

        stats = self._daily_stats[today]
        stats.trades += 1
        stats.realized_pnl += pnl

        if pnl >= 0:
            stats.winning_trades += 1
        else:
            stats.losing_trades += 1

        total_trades = stats.winning_trades + stats.losing_trades
        stats.win_rate = stats.winning_trades / total_trades if total_trades > 0 else 0
        stats.avg_profit_per_trade = stats.realized_pnl / stats.trades if stats.trades > 0 else 0

    def get_current_pnl(self, positions: list[Position]) -> dict[str, float]:
        """
        Get current P&L summary.

        Args:
            positions: Current positions

        Returns:
            Dictionary with P&L breakdown
        """
        open_positions = [p for p in positions if p.realized_pnl is None]
        closed_positions = [p for p in positions if p.realized_pnl is not None]

        unrealized = sum(p.unrealized_pnl for p in open_positions)
        realized = sum(p.realized_pnl or 0 for p in closed_positions)

        return {
            "unrealized_pnl": unrealized,
            "realized_pnl": realized,
            "total_pnl": unrealized + realized,
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
        }

    def get_daily_stats(self, date: str | None = None) -> DailyStats | None:
        """
        Get daily statistics.

        Args:
            date: Date string (YYYY-MM-DD). Defaults to today.

        Returns:
            DailyStats or None if not found
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return self._daily_stats.get(date)

    def get_performance_summary(self) -> dict[str, Any]:
        """Get overall performance summary."""
        if not self._trade_pnl:
            return {
                "total_trades": 0,
                "total_pnl": 0.0,
                "avg_pnl_per_trade": 0.0,
                "win_rate": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "sharpe_ratio": 0.0,
            }

        total_pnl = sum(self._trade_pnl)
        avg_pnl = total_pnl / len(self._trade_pnl)
        wins = [p for p in self._trade_pnl if p >= 0]
        losses = [p for p in self._trade_pnl if p < 0]

        # Simple Sharpe-like ratio (avg / std)
        import statistics
        try:
            std_dev = statistics.stdev(self._trade_pnl) if len(self._trade_pnl) > 1 else 1
            sharpe = avg_pnl / std_dev if std_dev > 0 else 0
        except statistics.StatisticsError:
            sharpe = 0

        return {
            "total_trades": len(self._trade_pnl),
            "total_pnl": total_pnl,
            "avg_pnl_per_trade": avg_pnl,
            "win_rate": len(wins) / len(self._trade_pnl) if self._trade_pnl else 0,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "best_trade": max(self._trade_pnl) if self._trade_pnl else 0,
            "worst_trade": min(self._trade_pnl) if self._trade_pnl else 0,
            "avg_win": sum(wins) / len(wins) if wins else 0,
            "avg_loss": sum(losses) / len(losses) if losses else 0,
            "sharpe_ratio": sharpe,
        }

    def get_recent_snapshots(self, hours: int = 1) -> list[PnLSnapshot]:
        """Get snapshots from the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [s for s in self._snapshots if s.timestamp > cutoff]

    def get_pnl_timeseries(
        self,
        hours: int = 24,
    ) -> list[tuple[datetime, float]]:
        """
        Get P&L timeseries for charting.

        Args:
            hours: Hours of history to include

        Returns:
            List of (timestamp, total_pnl) tuples
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            (s.timestamp, s.total_pnl)
            for s in self._snapshots
            if s.timestamp > cutoff
        ]

    def export_to_dict(self) -> dict[str, Any]:
        """Export all data to dictionary for persistence."""
        return {
            "snapshots": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "unrealized_pnl": s.unrealized_pnl,
                    "realized_pnl": s.realized_pnl,
                    "total_pnl": s.total_pnl,
                    "open_positions": s.open_positions,
                    "total_exposure": s.total_exposure,
                }
                for s in self._snapshots
            ],
            "daily_stats": {
                date: {
                    "trades": stats.trades,
                    "realized_pnl": stats.realized_pnl,
                    "win_rate": stats.win_rate,
                }
                for date, stats in self._daily_stats.items()
            },
            "trade_pnl": self._trade_pnl,
            "performance": self.get_performance_summary(),
        }
