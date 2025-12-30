"""Rich console dashboard for real-time monitoring."""

from datetime import datetime
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models import Position
from src.monitoring.pnl_tracker import PnLTracker
from src.risk.risk_manager import RiskManager


class Dashboard:
    """
    Rich console dashboard for monitoring bot status.
    
    Displays positions, P&L, opportunities, and system health.
    """

    def __init__(
        self,
        pnl_tracker: PnLTracker | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        """
        Initialize dashboard.

        Args:
            pnl_tracker: P&L tracker for performance data
            risk_manager: Risk manager for limit data
        """
        self.console = Console()
        self.pnl_tracker = pnl_tracker
        self.risk_manager = risk_manager

    def create_layout(self) -> Layout:
        """Create the dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        layout["left"].split_column(
            Layout(name="positions"),
            Layout(name="opportunities"),
        )
        layout["right"].split_column(
            Layout(name="pnl"),
            Layout(name="risk"),
        )
        return layout

    def render_header(self) -> Panel:
        """Render the header panel."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = Text()
        text.append("🤖 Polymarket Arbitrage Bot", style="bold magenta")
        text.append(f"  |  {now}", style="dim")
        return Panel(text, style="bold white on dark_blue")

    def render_footer(self, status: str = "Running") -> Panel:
        """Render the footer panel."""
        text = Text()
        text.append(f"Status: {status}", style="green" if status == "Running" else "yellow")
        text.append("  |  Press Ctrl+C to stop", style="dim")
        return Panel(text)

    def render_positions_table(self, positions: list[Position]) -> Panel:
        """Render the positions table."""
        table = Table(title="Open Positions", expand=True)
        table.add_column("Market", style="cyan", no_wrap=True)
        table.add_column("Asset", style="magenta")
        table.add_column("UP", justify="right")
        table.add_column("DOWN", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Cost", justify="right")
        table.add_column("Exp. P&L", justify="right")
        table.add_column("State", style="yellow")

        for pos in positions[:10]:  # Limit to 10 rows
            delta = pos.delta
            delta_style = "green" if abs(delta) < 10 else "red"
            pnl = pos.unrealized_pnl
            pnl_style = "green" if pnl >= 0 else "red"

            table.add_row(
                pos.market_id[:12] + "...",
                pos.market.asset if pos.market else "?",
                f"{pos.up_contracts:.1f}",
                f"{pos.down_contracts:.1f}",
                Text(f"{delta:+.1f}", style=delta_style),
                f"${pos.total_cost:.2f}",
                Text(f"${pnl:+.2f}", style=pnl_style),
                pos.state.value[:8],
            )

        if not positions:
            table.add_row("No open positions", "", "", "", "", "", "", "")

        return Panel(table, border_style="green")

    def render_opportunities_table(
        self,
        opportunities: list[dict[str, Any]],
    ) -> Panel:
        """Render pending opportunities."""
        table = Table(title="Pending Opportunities", expand=True)
        table.add_column("Asset", style="cyan")
        table.add_column("UP", justify="right")
        table.add_column("DOWN", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Profit", justify="right", style="green")
        table.add_column("Score", justify="right")

        for opp in opportunities[:5]:
            table.add_row(
                opp.get("asset", "?"),
                f"{opp.get('up_price', 0):.4f}",
                f"{opp.get('down_price', 0):.4f}",
                f"{opp.get('total_cost', 0):.4f}",
                f"{opp.get('profit', 0):.4f}",
                f"{opp.get('score', 0):.1f}",
            )

        if not opportunities:
            table.add_row("No opportunities", "", "", "", "", "")

        return Panel(table, border_style="yellow")

    def render_pnl_panel(self, positions: list[Position]) -> Panel:
        """Render P&L summary panel."""
        if self.pnl_tracker:
            pnl_data = self.pnl_tracker.get_current_pnl(positions)
            perf = self.pnl_tracker.get_performance_summary()
        else:
            pnl_data = {"unrealized_pnl": 0, "realized_pnl": 0, "total_pnl": 0}
            perf = {"total_trades": 0, "win_rate": 0}

        table = Table(title="P&L Summary", expand=True, show_header=False)
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")

        unrealized = pnl_data.get("unrealized_pnl", 0)
        realized = pnl_data.get("realized_pnl", 0)
        total = pnl_data.get("total_pnl", 0)

        table.add_row(
            "Unrealized P&L",
            Text(f"${unrealized:+.2f}", style="green" if unrealized >= 0 else "red"),
        )
        table.add_row(
            "Realized P&L",
            Text(f"${realized:+.2f}", style="green" if realized >= 0 else "red"),
        )
        table.add_row(
            "Total P&L",
            Text(f"${total:+.2f}", style="bold green" if total >= 0 else "bold red"),
        )
        table.add_row("", "")
        table.add_row("Total Trades", str(perf.get("total_trades", 0)))
        table.add_row("Win Rate", f"{perf.get('win_rate', 0)*100:.1f}%")

        return Panel(table, border_style="blue")

    def render_risk_panel(self) -> Panel:
        """Render risk metrics panel."""
        if self.risk_manager:
            risk_data = self.risk_manager.get_risk_summary()
        else:
            risk_data = {
                "total_exposure": 0,
                "exposure_utilization": 0,
                "daily_pnl": 0,
                "is_trading_allowed": True,
            }

        table = Table(title="Risk Metrics", expand=True, show_header=False)
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")

        exposure = risk_data.get("total_exposure", 0)
        util = risk_data.get("exposure_utilization", 0)
        util_style = "green" if util < 50 else ("yellow" if util < 80 else "red")

        table.add_row("Exposure", f"${exposure:.2f}")
        table.add_row("Utilization", Text(f"{util:.1f}%", style=util_style))
        table.add_row(
            "Daily P&L",
            Text(
                f"${risk_data.get('daily_pnl', 0):+.2f}",
                style="green" if risk_data.get("daily_pnl", 0) >= 0 else "red",
            ),
        )
        table.add_row("", "")
        table.add_row(
            "Trading Status",
            Text(
                "✅ Active" if risk_data.get("is_trading_allowed") else "🛑 Halted",
                style="green" if risk_data.get("is_trading_allowed") else "red",
            ),
        )

        return Panel(table, border_style="magenta")

    def render(
        self,
        positions: list[Position],
        opportunities: list[dict[str, Any]] | None = None,
        status: str = "Running",
    ) -> Layout:
        """
        Render the complete dashboard.

        Args:
            positions: Current open positions
            opportunities: Pending opportunities
            status: Bot status string

        Returns:
            Rendered Layout
        """
        layout = self.create_layout()

        layout["header"].update(self.render_header())
        layout["footer"].update(self.render_footer(status))
        layout["positions"].update(self.render_positions_table(positions))
        layout["opportunities"].update(
            self.render_opportunities_table(opportunities or [])
        )
        layout["pnl"].update(self.render_pnl_panel(positions))
        layout["risk"].update(self.render_risk_panel())

        return layout

    def print_status(
        self,
        positions: list[Position],
        opportunities: list[dict[str, Any]] | None = None,
    ) -> None:
        """Print a one-time status update."""
        self.console.print(self.render(positions, opportunities))

    def run_live(
        self,
        get_data_callback: Any,
        refresh_rate: float = 1.0,
    ) -> None:
        """
        Run live updating dashboard.

        Args:
            get_data_callback: Callback that returns (positions, opportunities, status)
            refresh_rate: Refresh rate in seconds
        """
        with Live(
            self.render([], []),
            console=self.console,
            refresh_per_second=1 / refresh_rate,
        ) as live:
            while True:
                try:
                    positions, opportunities, status = get_data_callback()
                    live.update(self.render(positions, opportunities, status))
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.console.print(f"[red]Dashboard error: {e}[/red]")
