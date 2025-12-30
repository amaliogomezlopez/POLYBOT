"""Post-trade analysis and validation reporting."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from src.models import Position, Trade
from src.monitoring.latency_logger import LatencyLogger, get_latency_logger

logger = structlog.get_logger(__name__)


@dataclass
class TradeAnalysis:
    """Analysis of a single trade execution."""
    
    trade_id: str
    position_id: str
    market_id: str
    outcome_type: str
    
    # Prices
    detected_price: float
    executed_price: float
    slippage: float
    slippage_pct: float
    
    # Timing
    detection_time: datetime
    execution_time: datetime
    latency_ms: float
    
    # Result
    size: float
    fee: float
    net_cost: float
    
    # Flags
    had_slippage: bool
    was_partial_fill: bool
    exceeded_latency_threshold: bool


@dataclass
class PositionAnalysis:
    """Analysis of a complete position (both legs)."""
    
    position_id: str
    market_id: str
    asset: str
    
    # Entry analysis
    up_trade: TradeAnalysis | None
    down_trade: TradeAnalysis | None
    
    # Combined metrics
    total_cost: float
    expected_profit: float
    actual_profit: float | None
    
    # Timing
    entry_start: datetime
    entry_complete: datetime
    entry_duration_ms: float
    settlement_time: datetime | None
    
    # Performance
    entry_slippage_total: float
    was_successful: bool
    exit_reason: str


@dataclass
class ValidationReport:
    """Comprehensive validation report for dry-run analysis."""
    
    # Report metadata
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    duration_hours: float
    
    # Summary stats
    total_positions: int
    successful_positions: int
    failed_positions: int
    partial_positions: int
    
    # Financial metrics
    total_invested: float
    total_fees: float
    realized_pnl: float
    unrealized_pnl: float
    net_pnl: float
    roi_pct: float
    
    # Win/Loss analysis
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    
    # Slippage analysis
    total_slippage: float
    avg_slippage_pct: float
    max_slippage_pct: float
    trades_with_slippage: int
    
    # Latency analysis
    avg_execution_latency_ms: float
    p95_execution_latency_ms: float
    max_execution_latency_ms: float
    latency_threshold_breaches: int
    
    # Position details
    positions: list[PositionAnalysis] = field(default_factory=list)
    
    # Alerts and warnings
    alerts: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class PostTradeAnalyzer:
    """
    Analyzes trade execution for validation before production.
    
    Key metrics:
    - Slippage (detected vs executed price)
    - Execution latency
    - Win/Loss ratio
    - Fee impact
    - Partial fill rates
    """
    
    def __init__(
        self,
        latency_logger: LatencyLogger | None = None,
        slippage_threshold_pct: float = 1.0,
        latency_threshold_ms: float = 500.0,
    ) -> None:
        """
        Initialize analyzer.
        
        Args:
            latency_logger: Latency logger instance
            slippage_threshold_pct: Alert if slippage exceeds this %
            latency_threshold_ms: Alert if latency exceeds this ms
        """
        self.latency_logger = latency_logger or get_latency_logger()
        self.slippage_threshold_pct = slippage_threshold_pct
        self.latency_threshold_ms = latency_threshold_ms
        
        # Internal storage
        self._trade_analyses: list[TradeAnalysis] = []
        self._position_analyses: list[PositionAnalysis] = []
        
        # Tracking detected prices for slippage calculation
        self._detected_prices: dict[str, float] = {}
        self._detection_times: dict[str, datetime] = {}
    
    def record_detected_price(
        self,
        token_id: str,
        price: float,
        timestamp: datetime | None = None,
    ) -> None:
        """Record a detected price before execution."""
        self._detected_prices[token_id] = price
        self._detection_times[token_id] = timestamp or datetime.now()
    
    def analyze_trade(
        self,
        trade: Trade,
        executed_price: float,
        execution_time: datetime | None = None,
        was_partial: bool = False,
    ) -> TradeAnalysis:
        """
        Analyze a single trade execution.
        
        Args:
            trade: The executed trade
            executed_price: Actual execution price
            execution_time: When execution completed
            was_partial: Whether this was a partial fill
            
        Returns:
            TradeAnalysis with detailed metrics
        """
        execution_time = execution_time or datetime.now()
        
        # Get detected price (or use executed if not tracked)
        detected_price = self._detected_prices.get(trade.token_id, executed_price)
        detection_time = self._detection_times.get(trade.token_id, execution_time)
        
        # Calculate slippage
        if detected_price > 0:
            slippage = executed_price - detected_price
            slippage_pct = (slippage / detected_price) * 100
        else:
            slippage = 0.0
            slippage_pct = 0.0
        
        # Calculate latency
        latency_ms = (execution_time - detection_time).total_seconds() * 1000
        
        analysis = TradeAnalysis(
            trade_id=trade.id,
            position_id=trade.position_id,
            market_id=trade.market_id,
            outcome_type=str(trade.outcome_type),
            detected_price=detected_price,
            executed_price=executed_price,
            slippage=slippage,
            slippage_pct=slippage_pct,
            detection_time=detection_time,
            execution_time=execution_time,
            latency_ms=latency_ms,
            size=trade.size,
            fee=trade.fee,
            net_cost=trade.size * executed_price + trade.fee,
            had_slippage=abs(slippage_pct) > 0.01,
            was_partial_fill=was_partial,
            exceeded_latency_threshold=latency_ms > self.latency_threshold_ms,
        )
        
        self._trade_analyses.append(analysis)
        
        # Log warnings
        if abs(slippage_pct) > self.slippage_threshold_pct:
            logger.warning(
                "High slippage detected",
                trade_id=trade.id,
                slippage_pct=round(slippage_pct, 2),
                detected=detected_price,
                executed=executed_price,
            )
        
        if latency_ms > self.latency_threshold_ms:
            logger.warning(
                "High execution latency",
                trade_id=trade.id,
                latency_ms=round(latency_ms, 2),
                threshold_ms=self.latency_threshold_ms,
            )
        
        return analysis
    
    def analyze_position(
        self,
        position: Position,
        up_trade: Trade | None = None,
        down_trade: Trade | None = None,
    ) -> PositionAnalysis:
        """
        Analyze a complete position (both legs).
        
        Args:
            position: The position to analyze
            up_trade: UP leg trade (if available)
            down_trade: DOWN leg trade (if available)
            
        Returns:
            PositionAnalysis with detailed metrics
        """
        up_analysis = None
        down_analysis = None
        
        if up_trade:
            up_analysis = next(
                (a for a in self._trade_analyses if a.trade_id == up_trade.id),
                None,
            )
        
        if down_trade:
            down_analysis = next(
                (a for a in self._trade_analyses if a.trade_id == down_trade.id),
                None,
            )
        
        # Calculate combined metrics
        entry_slippage = 0.0
        if up_analysis:
            entry_slippage += up_analysis.slippage
        if down_analysis:
            entry_slippage += down_analysis.slippage
        
        entry_start = position.created_at
        entry_complete = position.updated_at
        entry_duration = (entry_complete - entry_start).total_seconds() * 1000
        
        # Determine success
        is_successful = (
            position.up_contracts > 0
            and position.down_contracts > 0
            and abs(position.up_contracts - position.down_contracts) < 0.01
        )
        
        exit_reason = "settled" if position.realized_pnl is not None else "open"
        if not is_successful:
            exit_reason = "partial_fill" if position.up_contracts > 0 or position.down_contracts > 0 else "failed"
        
        analysis = PositionAnalysis(
            position_id=position.id,
            market_id=position.market_id,
            asset=position.market.asset if position.market else "unknown",
            up_trade=up_analysis,
            down_trade=down_analysis,
            total_cost=position.total_cost,
            expected_profit=position.expected_profit_per_contract * min(
                position.up_contracts, position.down_contracts
            ),
            actual_profit=position.realized_pnl,
            entry_start=entry_start,
            entry_complete=entry_complete,
            entry_duration_ms=entry_duration,
            settlement_time=position.settled_at,
            entry_slippage_total=entry_slippage,
            was_successful=is_successful,
            exit_reason=exit_reason,
        )
        
        self._position_analyses.append(analysis)
        return analysis
    
    def generate_validation_report(
        self,
        positions: list[Position],
        trades: list[Trade],
        period_hours: float = 48.0,
    ) -> ValidationReport:
        """
        Generate comprehensive validation report.
        
        Args:
            positions: All positions in the period
            trades: All trades in the period
            period_hours: Report period in hours
            
        Returns:
            ValidationReport with all metrics and recommendations
        """
        now = datetime.now()
        period_start = now - timedelta(hours=period_hours)
        
        # Filter to period
        period_positions = [
            p for p in positions
            if p.created_at >= period_start
        ]
        period_trades = [
            t for t in trades
            if t.created_at >= period_start
        ]
        
        # Analyze all positions
        position_analyses = []
        for pos in period_positions:
            pos_trades = [t for t in period_trades if t.position_id == pos.id]
            up_trade = next((t for t in pos_trades if t.outcome_type == "UP"), None)
            down_trade = next((t for t in pos_trades if t.outcome_type == "DOWN"), None)
            
            analysis = self.analyze_position(pos, up_trade, down_trade)
            position_analyses.append(analysis)
        
        # Calculate summary stats
        successful = [p for p in position_analyses if p.was_successful]
        failed = [p for p in position_analyses if p.exit_reason == "failed"]
        partial = [p for p in position_analyses if p.exit_reason == "partial_fill"]
        
        # Financial metrics
        total_invested = sum(p.total_cost for p in position_analyses)
        total_fees = sum(
            (p.up_trade.fee if p.up_trade else 0) + (p.down_trade.fee if p.down_trade else 0)
            for p in position_analyses
        )
        
        realized = sum(p.actual_profit or 0 for p in position_analyses if p.actual_profit is not None)
        unrealized = sum(p.expected_profit for p in position_analyses if p.actual_profit is None)
        net_pnl = realized + unrealized - total_fees
        
        # Win/Loss analysis
        winners = [p for p in position_analyses if (p.actual_profit or 0) > 0]
        losers = [p for p in position_analyses if (p.actual_profit or 0) < 0]
        
        avg_win = sum(p.actual_profit or 0 for p in winners) / len(winners) if winners else 0
        avg_loss = abs(sum(p.actual_profit or 0 for p in losers) / len(losers)) if losers else 0
        
        total_wins = sum(p.actual_profit or 0 for p in winners)
        total_losses = abs(sum(p.actual_profit or 0 for p in losers))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Slippage analysis
        all_trade_analyses = self._trade_analyses
        slippage_values = [abs(t.slippage_pct) for t in all_trade_analyses]
        trades_with_slippage = len([t for t in all_trade_analyses if t.had_slippage])
        
        # Latency analysis
        latencies = [t.latency_ms for t in all_trade_analyses]
        latency_breaches = len([t for t in all_trade_analyses if t.exceeded_latency_threshold])
        
        # Generate alerts
        alerts = []
        recommendations = []
        
        if len(failed) > len(period_positions) * 0.1:
            alerts.append({
                "severity": "high",
                "type": "high_failure_rate",
                "message": f"High position failure rate: {len(failed)}/{len(period_positions)}",
            })
            recommendations.append("Review order execution logic and API connectivity")
        
        if slippage_values and max(slippage_values) > 2.0:
            alerts.append({
                "severity": "medium",
                "type": "high_slippage",
                "message": f"Max slippage: {max(slippage_values):.2f}%",
            })
            recommendations.append("Consider using limit orders or reducing position size")
        
        if latency_breaches > len(all_trade_analyses) * 0.05:
            alerts.append({
                "severity": "medium",
                "type": "latency_issues",
                "message": f"Latency threshold breaches: {latency_breaches}",
            })
            recommendations.append("Deploy to lower-latency infrastructure (us-east-1)")
        
        win_rate = len(winners) / len(position_analyses) * 100 if position_analyses else 0
        
        if win_rate < 50:
            alerts.append({
                "severity": "high",
                "type": "low_win_rate",
                "message": f"Win rate below 50%: {win_rate:.1f}%",
            })
            recommendations.append("Review opportunity detection thresholds")
        
        # Build report
        report = ValidationReport(
            report_id=f"validation-{now.strftime('%Y%m%d-%H%M%S')}",
            generated_at=now,
            period_start=period_start,
            period_end=now,
            duration_hours=period_hours,
            total_positions=len(period_positions),
            successful_positions=len(successful),
            failed_positions=len(failed),
            partial_positions=len(partial),
            total_invested=round(total_invested, 2),
            total_fees=round(total_fees, 4),
            realized_pnl=round(realized, 4),
            unrealized_pnl=round(unrealized, 4),
            net_pnl=round(net_pnl, 4),
            roi_pct=round(net_pnl / total_invested * 100, 2) if total_invested > 0 else 0,
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate=round(win_rate, 2),
            avg_win=round(avg_win, 4),
            avg_loss=round(avg_loss, 4),
            profit_factor=round(profit_factor, 2) if profit_factor != float('inf') else 999.99,
            total_slippage=round(sum(slippage_values), 4) if slippage_values else 0,
            avg_slippage_pct=round(sum(slippage_values) / len(slippage_values), 4) if slippage_values else 0,
            max_slippage_pct=round(max(slippage_values), 4) if slippage_values else 0,
            trades_with_slippage=trades_with_slippage,
            avg_execution_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0,
            p95_execution_latency_ms=round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if latencies else 0,
            max_execution_latency_ms=round(max(latencies), 2) if latencies else 0,
            latency_threshold_breaches=latency_breaches,
            positions=position_analyses,
            alerts=alerts,
            recommendations=recommendations,
        )
        
        return report
    
    def export_report(
        self,
        report: ValidationReport,
        output_dir: str = "./reports",
        format: str = "json",
    ) -> Path:
        """
        Export validation report to file.
        
        Args:
            report: Report to export
            output_dir: Output directory
            format: Export format ('json' or 'md')
            
        Returns:
            Path to exported file
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{report.report_id}.{format}"
        filepath = output_path / filename
        
        if format == "json":
            self._export_json(report, filepath)
        else:
            self._export_markdown(report, filepath)
        
        logger.info("Report exported", path=str(filepath))
        return filepath
    
    def _export_json(self, report: ValidationReport, filepath: Path) -> None:
        """Export report as JSON."""
        def serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "__dataclass_fields__"):
                return {k: serialize(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, list):
                return [serialize(i) for i in obj]
            return obj
        
        with open(filepath, "w") as f:
            json.dump(serialize(report), f, indent=2, default=str)
    
    def _export_markdown(self, report: ValidationReport, filepath: Path) -> None:
        """Export report as Markdown."""
        md = f"""# Validation Report: {report.report_id}

Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}
Period: {report.period_start.strftime('%Y-%m-%d %H:%M')} to {report.period_end.strftime('%Y-%m-%d %H:%M')} ({report.duration_hours}h)

## Summary

| Metric | Value |
|--------|-------|
| Total Positions | {report.total_positions} |
| Successful | {report.successful_positions} |
| Failed | {report.failed_positions} |
| Partial | {report.partial_positions} |

## Financial Performance

| Metric | Value |
|--------|-------|
| Total Invested | ${report.total_invested:.2f} |
| Total Fees | ${report.total_fees:.4f} |
| Realized P&L | ${report.realized_pnl:.4f} |
| Unrealized P&L | ${report.unrealized_pnl:.4f} |
| **Net P&L** | **${report.net_pnl:.4f}** |
| **ROI** | **{report.roi_pct:.2f}%** |

## Win/Loss Analysis

| Metric | Value |
|--------|-------|
| Winning Trades | {report.winning_trades} |
| Losing Trades | {report.losing_trades} |
| Win Rate | {report.win_rate:.2f}% |
| Avg Win | ${report.avg_win:.4f} |
| Avg Loss | ${report.avg_loss:.4f} |
| Profit Factor | {report.profit_factor:.2f} |

## Execution Quality

### Slippage
| Metric | Value |
|--------|-------|
| Total Slippage | {report.total_slippage:.4f}% |
| Avg Slippage | {report.avg_slippage_pct:.4f}% |
| Max Slippage | {report.max_slippage_pct:.4f}% |
| Trades w/ Slippage | {report.trades_with_slippage} |

### Latency
| Metric | Value |
|--------|-------|
| Avg Latency | {report.avg_execution_latency_ms:.2f}ms |
| P95 Latency | {report.p95_execution_latency_ms:.2f}ms |
| Max Latency | {report.max_execution_latency_ms:.2f}ms |
| Threshold Breaches | {report.latency_threshold_breaches} |

## Alerts

"""
        for alert in report.alerts:
            severity_icon = "🔴" if alert["severity"] == "high" else "🟡"
            md += f"- {severity_icon} **{alert['type']}**: {alert['message']}\n"
        
        if not report.alerts:
            md += "✅ No alerts\n"
        
        md += "\n## Recommendations\n\n"
        for rec in report.recommendations:
            md += f"- {rec}\n"
        
        if not report.recommendations:
            md += "✅ No recommendations - system performing well\n"
        
        md += f"\n---\n*Report generated by Polybot Validation System*\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)


# Global analyzer instance
_analyzer: PostTradeAnalyzer | None = None


def get_analyzer() -> PostTradeAnalyzer:
    """Get global analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = PostTradeAnalyzer()
    return _analyzer
