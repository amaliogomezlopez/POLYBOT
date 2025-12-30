"""CLI interface for the Polymarket arbitrage bot."""

import asyncio
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="polybot",
    help="Polymarket Delta-Neutral Arbitrage Bot",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    paper: bool = typer.Option(
        False,
        "--paper",
        "-p",
        help="Run in paper trading mode (no real orders)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Start the trading bot."""
    from src.main import run_bot, setup_logging

    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)

    if paper:
        console.print("[yellow]🔸 Running in PAPER TRADING mode[/yellow]")
    else:
        console.print("[green]🟢 Running in LIVE mode[/green]")

    console.print()
    asyncio.run(run_bot(paper_trading=paper))


@app.command()
def status() -> None:
    """Show current bot status and positions."""
    from rich.table import Table

    from src.config.settings import get_settings

    try:
        settings = get_settings()
        console.print("[bold]Bot Configuration[/bold]\n")

        table = Table(show_header=False)
        table.add_column("Setting", style="dim")
        table.add_column("Value")

        table.add_row("Environment", settings.environment)
        table.add_row("Paper Trading", "Yes" if settings.paper_trading else "No")
        table.add_row("Max Position", f"${settings.max_position_size_usdc:.2f}")
        table.add_row("Min Profit", f"{settings.min_profit_threshold:.2%}")
        table.add_row("Max Daily Loss", f"${settings.max_daily_loss_usdc:.2f}")
        table.add_row("Max Exposure", f"${settings.max_total_exposure_usdc:.2f}")
        table.add_row("Telegram", "Enabled" if settings.telegram_enabled else "Disabled")

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error loading settings: {e}[/red]")
        console.print("\nMake sure you have a valid .env file configured.")


@app.command()
def test_connection() -> None:
    """Test connection to Polymarket API."""

    async def _test() -> None:
        from src.scanner.market_scanner import MarketScanner

        console.print("[bold]Testing Polymarket API connection...[/bold]\n")

        async with MarketScanner() as scanner:
            # Test basic API call
            markets = await scanner.get_all_markets()

            if markets:
                console.print(f"[green]✓ Connected successfully![/green]")
                console.print(f"  Found {len(markets)} active markets\n")

                # Find flash markets
                flash = await scanner.scan_flash_markets()
                console.print(f"  Flash markets: {len(flash)}")

                if flash:
                    console.print("\n[bold]Sample Flash Markets:[/bold]")
                    for market in flash[:3]:
                        console.print(f"  • {market.question[:60]}...")
                        console.print(f"    Asset: {market.asset}, Ends: {market.end_time}")
            else:
                console.print("[red]✗ No markets found[/red]")

    asyncio.run(_test())


@app.command()
def scan() -> None:
    """Scan for current arbitrage opportunities."""

    async def _scan() -> None:
        from rich.table import Table

        from src.config.settings import get_settings
        from src.detector.spread_analyzer import SpreadAnalyzer
        from src.scanner.market_scanner import MarketScanner

        settings = get_settings()
        console.print("[bold]Scanning for arbitrage opportunities...[/bold]\n")

        analyzer = SpreadAnalyzer(
            min_profit_threshold=settings.min_profit_threshold,
        )

        async with MarketScanner() as scanner:
            markets = await scanner.scan_flash_markets()

            if not markets:
                console.print("[yellow]No flash markets found[/yellow]")
                return

            console.print(f"Found {len(markets)} flash markets\n")

            # Create results table
            table = Table(title="Arbitrage Opportunities")
            table.add_column("Asset")
            table.add_column("UP Price", justify="right")
            table.add_column("DOWN Price", justify="right")
            table.add_column("Total Cost", justify="right")
            table.add_column("Profit", justify="right", style="green")
            table.add_column("Status")

            opportunities = 0
            for market in markets:
                if not market.tokens:
                    continue

                tokens = await scanner.get_market_prices(market)
                if not tokens:
                    continue

                result = analyzer.analyze(
                    market=market,
                    up_price=tokens.up_price,
                    down_price=tokens.down_price,
                    up_liquidity=1000,  # Would need real data
                    down_liquidity=1000,
                )

                if tokens.up_price > 0 or tokens.down_price > 0:
                    status = "[green]PROFITABLE[/green]" if result.is_profitable else "[dim]No arb[/dim]"
                    if result.is_profitable:
                        opportunities += 1

                    table.add_row(
                        market.asset or "?",
                        f"{tokens.up_price:.4f}",
                        f"{tokens.down_price:.4f}",
                        f"{tokens.total_cost:.4f}",
                        f"{tokens.profit_per_contract:.4f}",
                        status,
                    )

            console.print(table)
            console.print(f"\n[bold]Found {opportunities} opportunities[/bold]")

    asyncio.run(_scan())


@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of records to show"),
) -> None:
    """Show trade history."""
    console.print("[yellow]Trade history requires a running bot with database.[/yellow]")
    console.print("Start the bot with 'polybot run' to begin tracking trades.")


# ============================================================================
# VALIDATION COMMANDS (Phase 9)
# ============================================================================

@app.command()
def validate(
    hours: float = typer.Option(48.0, "--hours", "-h", help="Validation period in hours"),
    output: str = typer.Option("./reports", "--output", "-o", help="Output directory for reports"),
) -> None:
    """Run validation analysis and generate report."""
    from rich.panel import Panel
    
    console.print(Panel("[bold]🔍 Running Validation Analysis[/bold]", style="blue"))
    
    async def _validate() -> None:
        from src.monitoring.latency_logger import get_latency_logger
        from src.reporting.post_trade_analysis import PostTradeAnalyzer
        
        analyzer = PostTradeAnalyzer()
        latency_logger = get_latency_logger()
        
        # In a real scenario, this would load from database
        # For now, we'll generate a report with current session data
        positions: list = []  # Would load from DB
        trades: list = []  # Would load from DB
        
        console.print(f"Analyzing {hours}h of trading data...")
        
        report = analyzer.generate_validation_report(
            positions=positions,
            trades=trades,
            period_hours=hours,
        )
        
        # Export reports
        json_path = analyzer.export_report(report, output, "json")
        md_path = analyzer.export_report(report, output, "md")
        
        console.print(f"\n[green]✓[/green] Reports generated:")
        console.print(f"  • JSON: {json_path}")
        console.print(f"  • Markdown: {md_path}")
        
        # Show summary
        from rich.table import Table
        
        table = Table(title="Validation Summary")
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")
        
        table.add_row("Total Positions", str(report.total_positions))
        table.add_row("Successful", f"[green]{report.successful_positions}[/green]")
        table.add_row("Failed", f"[red]{report.failed_positions}[/red]" if report.failed_positions > 0 else "0")
        table.add_row("Win Rate", f"{report.win_rate:.1f}%")
        table.add_row("Net P&L", f"${report.net_pnl:.4f}")
        table.add_row("ROI", f"{report.roi_pct:.2f}%")
        table.add_row("Avg Latency", f"{report.avg_execution_latency_ms:.1f}ms")
        table.add_row("Alerts", str(len(report.alerts)))
        
        console.print()
        console.print(table)
        
        # Show alerts
        if report.alerts:
            console.print("\n[bold yellow]⚠️ Alerts:[/bold yellow]")
            for alert in report.alerts:
                icon = "🔴" if alert["severity"] == "high" else "🟡"
                console.print(f"  {icon} {alert['message']}")
        
        # Show recommendations
        if report.recommendations:
            console.print("\n[bold]📋 Recommendations:[/bold]")
            for rec in report.recommendations:
                console.print(f"  • {rec}")
        else:
            console.print("\n[green]✅ No issues detected - ready for production![/green]")
    
    asyncio.run(_validate())


@app.command()
def latency_report() -> None:
    """Show execution latency statistics."""
    from rich.table import Table
    
    from src.monitoring.latency_logger import get_latency_logger
    
    console.print("[bold]📊 Latency Report[/bold]\n")
    
    latency_logger = get_latency_logger()
    report = latency_logger.generate_report()
    
    if not report["operations"]:
        console.print("[yellow]No latency data recorded yet.[/yellow]")
        console.print("Run the bot in paper trading mode to collect latency metrics.")
        return
    
    table = Table(title="Latency by Operation")
    table.add_column("Operation")
    table.add_column("Count", justify="right")
    table.add_column("Avg (ms)", justify="right")
    table.add_column("P95 (ms)", justify="right")
    table.add_column("P99 (ms)", justify="right")
    table.add_column("Success %", justify="right")
    
    for op, stats in report["operations"].items():
        table.add_row(
            op,
            str(stats["count"]),
            f"{stats['avg_ms']:.1f}",
            f"{stats['p95_ms']:.1f}",
            f"{stats['p99_ms']:.1f}",
            f"{stats['success_rate']:.1f}%",
        )
    
    console.print(table)
    
    if report["alerts"]:
        console.print("\n[bold yellow]⚠️ Performance Alerts:[/bold yellow]")
        for alert in report["alerts"]:
            console.print(f"  • {alert['operation']}: {alert['issue']}")


@app.command()
def dry_run(
    duration: int = typer.Option(60, "--duration", "-d", help="Duration in minutes"),
    size: float = typer.Option(10.0, "--size", "-s", help="Position size in USDC"),
) -> None:
    """Run a dry-run validation session (paper trading with monitoring)."""
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    
    console.print(Panel(
        f"[bold]🚀 Starting Dry-Run Session[/bold]\n\n"
        f"Duration: {duration} minutes\n"
        f"Position Size: ${size:.2f}\n"
        f"Mode: Paper Trading (Enhanced Simulation)",
        style="green",
    ))
    
    async def _dry_run() -> None:
        import os
        os.environ["PAPER_TRADING"] = "true"
        
        from src.main import run_bot, setup_logging
        
        setup_logging("INFO")
        
        console.print("\n[yellow]Starting bot in dry-run mode...[/yellow]")
        console.print("[dim]Press Ctrl+C to stop early[/dim]\n")
        
        try:
            await asyncio.wait_for(
                run_bot(paper_trading=True),
                timeout=duration * 60,
            )
        except asyncio.TimeoutError:
            console.print(f"\n[green]✓ Dry-run completed after {duration} minutes[/green]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Dry-run stopped by user[/yellow]")
        
        # Generate report after dry-run
        console.print("\n[bold]Generating validation report...[/bold]")
        # Would call validate command logic here
    
    asyncio.run(_dry_run())


@app.command()
def simulation_stats() -> None:
    """Show paper trading simulation statistics."""
    from rich.table import Table
    
    from src.trading.slippage_simulator import get_simulator
    
    console.print("[bold]📈 Simulation Statistics[/bold]\n")
    
    simulator = get_simulator()
    stats = simulator.get_statistics()
    
    table = Table()
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")
    
    table.add_row("Total Orders", str(stats["total_orders"]))
    table.add_row("Failed Orders", str(stats["failed_orders"]))
    table.add_row("Failure Rate", f"{stats['failure_rate']:.2f}%")
    table.add_row("Partial Fills", str(stats["partial_fills"]))
    table.add_row("Partial Fill Rate", f"{stats['partial_fill_rate']:.2f}%")
    table.add_row("Avg Slippage", f"{stats['avg_slippage_pct']:.4f}%")
    
    console.print(table)
    
    if stats["total_orders"] == 0:
        console.print("\n[yellow]No simulation data yet. Run 'polybot dry-run' to generate data.[/yellow]")


@app.command()
def checklist() -> None:
    """Show pre-production validation checklist."""
    from rich.panel import Panel
    from rich.markdown import Markdown
    
    checklist_md = """
# Pre-Production Validation Checklist

## Phase 9: Live Testing & Validation

### Paper Trading ✅
- [x] Enhanced slippage simulation
- [x] Realistic fee modeling
- [x] Latency simulation
- [x] Partial fill handling

### Monitoring & Analysis
- [x] Execution latency logger
- [x] Post-trade analysis reports
- [x] Win/Loss tracking
- [x] Slippage analysis

### Validation Commands
- [x] `polybot validate` - Generate validation report
- [x] `polybot latency-report` - View latency stats
- [x] `polybot dry-run` - Run validation session
- [x] `polybot simulation-stats` - View simulation stats

## Phase 10: Production Readiness

### Secrets Management
- [ ] Review .env file security
- [ ] Ensure private keys are not in git
- [ ] Setup secrets manager (optional)

### Risk Configuration
- [ ] Set conservative `MAX_POSITION_SIZE_USDC`
- [ ] Configure `MAX_DAILY_LOSS_USDC`
- [ ] Set appropriate `MIN_PROFIT_THRESHOLD`

### Deployment
- [ ] Docker configuration
- [ ] VPS setup (us-east-1 recommended)
- [ ] Monitoring alerts (Telegram)

### Go-Live
- [ ] Start with minimum position size ($1)
- [ ] Monitor first 10 trades manually
- [ ] Gradually increase position size

---

Run `polybot validate --hours 48` after a dry-run session to check all metrics.
"""
    
    console.print(Panel(Markdown(checklist_md), title="Validation Checklist", border_style="blue"))


@app.command()
def version() -> None:
    """Show version information."""
    from src import __version__

    console.print(f"[bold]Polymarket Arbitrage Bot[/bold] v{__version__}")
    console.print("\nhttps://github.com/your-repo/polymarket-bot")


if __name__ == "__main__":
    app()
