"""
🎯 POLYMARKET TAIL BETTING - TERMINAL UI
=========================================
Beautiful terminal dashboard with Rich library.
Shows positions, market analysis, transactions, and P&L.

Style: Cyberpunk/Trading terminal with green/red colors
"""

import asyncio
import json
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
import random

# Rich imports for beautiful terminal UI
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn
from rich.style import Style
from rich import box

console = Console()

# =============================================================================
# STYLES
# =============================================================================

STYLES = {
    'up': Style(color="green", bold=True),
    'down': Style(color="red", bold=True),
    'profit': Style(color="bright_green", bold=True),
    'loss': Style(color="bright_red", bold=True),
    'neutral': Style(color="cyan"),
    'header': Style(color="cyan", bold=True),
    'value': Style(color="white", bold=True),
    'muted': Style(color="bright_black"),
    'highlight': Style(color="yellow", bold=True),
}

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Position:
    side: str  # "UP" or "DOWN"
    size: int
    cost: float
    avg_price: float
    current_price: float
    pnl: float

@dataclass
class Transaction:
    time: str
    side: str
    price: float
    size: int
    btc_price: float
    tx_hash: str

@dataclass
class MarketData:
    up_price: float = 0.0
    down_price: float = 0.0
    combined: float = 0.0
    spread: float = 0.0
    pairs: int = 0
    delta: int = 0
    total_pnl: float = 0.0

@dataclass
class DashboardState:
    positions: list = field(default_factory=list)
    transactions: list = field(default_factory=list)
    market: MarketData = field(default_factory=MarketData)
    trades_count: int = 0
    volume: float = 0.0
    wallet: str = ""
    last_update: str = ""

# =============================================================================
# DASHBOARD UI
# =============================================================================

class TradingDashboard:
    """
    Beautiful terminal trading dashboard.
    """
    
    def __init__(self):
        self.state = DashboardState()
        self.bets_file = Path("data/tail_bot/bets.json")
        self.resolved_file = Path("data/tail_bot/resolved.json")
        self.client: Optional[httpx.AsyncClient] = None
        
    def load_data(self):
        """Load bet data from files."""
        bets = []
        resolved = []
        
        if self.bets_file.exists():
            bets = json.loads(self.bets_file.read_text())
        if self.resolved_file.exists():
            resolved = json.loads(self.resolved_file.read_text())
        
        return bets, resolved
    
    def calculate_stats(self, bets: list, resolved: list) -> dict:
        """Calculate portfolio statistics."""
        total_bets = len(bets)
        total_invested = sum(b.get('stake', 2) for b in bets)
        pending = len([b for b in bets if b.get('status') == 'pending'])
        
        won = [r for r in resolved if r.get('status') == 'won']
        lost = [r for r in resolved if r.get('status') == 'lost']
        
        total_pnl = sum(r.get('profit', 0) for r in resolved)
        
        # Calculate multipliers
        multipliers = []
        for b in bets:
            mult = b.get('potential_multiplier')
            if not mult:
                price = b.get('entry_price') or b.get('price', 0.02)
                mult = round(1/price, 1) if price > 0 else 50
            multipliers.append(mult)
        
        avg_mult = sum(multipliers) / max(len(multipliers), 1)
        
        return {
            'total_bets': total_bets,
            'total_invested': total_invested,
            'pending': pending,
            'won': len(won),
            'lost': len(lost),
            'total_pnl': total_pnl,
            'avg_mult': avg_mult,
            'hit_rate': len(won) / len(resolved) * 100 if resolved else 0
        }
    
    # -------------------------------------------------------------------------
    # UI COMPONENTS
    # -------------------------------------------------------------------------
    
    def create_header(self) -> Panel:
        """Create header panel."""
        title = Text()
        title.append("🎯 ", style="bold")
        title.append("POLYMARKET TAIL BETTING TERMINAL", style=STYLES['header'])
        title.append(" 🎯", style="bold")
        
        subtitle = Text()
        subtitle.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style=STYLES['muted'])
        subtitle.append("  |  ", style=STYLES['muted'])
        subtitle.append("PAPER MODE", style=Style(color="yellow", bold=True))
        
        content = Text.assemble(title, "\n", subtitle)
        
        return Panel(
            content,
            box=box.DOUBLE,
            style="cyan",
            padding=(0, 2)
        )
    
    def create_positions_panel(self, stats: dict, bets: list) -> Panel:
        """Create positions panel."""
        content = Text()
        
        # Calculate position-like stats from bets
        total_invested = stats['total_invested']
        pending = stats['pending']
        avg_mult = stats['avg_mult']
        
        # UP-like (potential wins)
        potential_return = total_invested * avg_mult
        
        # Simulate position bars
        content.append("▲ ", style=STYLES['up'])
        content.append("TAIL BETS", style=STYLES['up'])
        
        # Progress bar simulation
        bar_width = 30
        filled = int(bar_width * 0.7)
        bar = "█" * filled + "░" * (bar_width - filled)
        content.append(f"\n  {bar}  ", style="green")
        content.append(f"{pending:,}", style=STYLES['value'])
        content.append(f"  @avg ", style=STYLES['muted'])
        content.append(f"{avg_mult:.0f}x", style=STYLES['value'])
        
        content.append(f"\n  Cost: ", style=STYLES['muted'])
        content.append(f"${total_invested:,.2f}", style=STYLES['value'])
        content.append(f"  |  Potential: ", style=STYLES['muted'])
        content.append(f"${potential_return:,.0f}", style=STYLES['profit'])
        
        content.append("\n\n")
        
        # DOWN-like (resolved)
        resolved_count = stats['won'] + stats['lost']
        content.append("▼ ", style=STYLES['down'])
        content.append("RESOLVED", style=STYLES['down'])
        
        if resolved_count > 0:
            win_pct = stats['won'] / resolved_count
            filled = int(bar_width * win_pct)
            bar = "█" * filled + "░" * (bar_width - filled)
            content.append(f"\n  {bar}  ", style="red")
        else:
            content.append(f"\n  {'░' * bar_width}  ", style="bright_black")
        
        content.append(f"{resolved_count}", style=STYLES['value'])
        
        pnl_style = STYLES['profit'] if stats['total_pnl'] >= 0 else STYLES['loss']
        content.append(f"\n  Won: ", style=STYLES['muted'])
        content.append(f"{stats['won']}", style=STYLES['profit'])
        content.append(f"  |  Lost: ", style=STYLES['muted'])
        content.append(f"{stats['lost']}", style=STYLES['loss'])
        content.append(f"  |  P&L: ", style=STYLES['muted'])
        content.append(f"${stats['total_pnl']:+,.2f}", style=pnl_style)
        
        return Panel(
            content,
            title="[bold cyan]📊 POSITIONS[/]",
            box=box.ROUNDED,
            style="cyan",
            padding=(1, 2)
        )
    
    def create_market_panel(self, stats: dict) -> Panel:
        """Create market analysis panel."""
        content = Text()
        
        # Required hit rate
        required = 1 / stats['avg_mult'] * 100 if stats['avg_mult'] > 0 else 2
        
        content.append("Avg Multiplier: ", style=STYLES['muted'])
        content.append(f"{stats['avg_mult']:.1f}x", style=STYLES['profit'])
        content.append("    |    ", style=STYLES['muted'])
        content.append("Required Hit: ", style=STYLES['muted'])
        content.append(f"{required:.2f}%", style=STYLES['highlight'])
        
        content.append("\n\n")
        
        # Progress bar for breakeven
        bar_width = 40
        current_hit = stats['hit_rate']
        target_hit = required
        
        if current_hit > 0:
            progress = min(current_hit / target_hit, 2.0)  # Cap at 200%
            filled = int(bar_width * progress / 2)
            bar = "█" * filled + "▓" * 5 + "░" * max(0, bar_width - filled - 5)
            bar_style = "green" if progress >= 1.0 else "yellow"
            content.append(f"  {bar}", style=bar_style)
        else:
            content.append(f"  {'░' * bar_width}", style="bright_black")
        
        content.append("\n\n")
        
        # Stats row
        content.append("Bets: ", style=STYLES['muted'])
        content.append(f"{stats['total_bets']:,}", style=STYLES['value'])
        content.append("    |    ", style=STYLES['muted'])
        content.append("Pending: ", style=STYLES['muted'])
        content.append(f"{stats['pending']}", style=STYLES['highlight'])
        content.append("    |    ", style=STYLES['muted'])
        content.append("Hit Rate: ", style=STYLES['muted'])
        
        if stats['hit_rate'] > 0:
            hr_style = STYLES['profit'] if stats['hit_rate'] >= required else STYLES['loss']
            content.append(f"{stats['hit_rate']:.1f}%", style=hr_style)
        else:
            content.append("--", style=STYLES['muted'])
        
        return Panel(
            content,
            title="[bold cyan]═══ MARKET ANALYSIS ═══[/]",
            box=box.ROUNDED,
            style="cyan",
            padding=(1, 2)
        )
    
    def create_bets_table(self, bets: list) -> Panel:
        """Create recent bets table."""
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold cyan",
            padding=(0, 1)
        )
        
        table.add_column("TIME", style="bright_black", width=12)
        table.add_column("TYPE", width=8)
        table.add_column("PRICE", style="white", width=10)
        table.add_column("MULT", style="yellow", width=8)
        table.add_column("ML", style="cyan", width=6)
        table.add_column("QUESTION", style="white", width=40)
        
        # Get recent bets
        recent = sorted(bets, key=lambda x: x.get('timestamp', 0), reverse=True)[:8]
        
        for bet in recent:
            ts = bet.get('timestamp', 0)
            time_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S') if ts else '--:--:--'
            
            price = bet.get('entry_price') or bet.get('price', 0)
            mult = bet.get('potential_multiplier') or (round(1/price, 0) if price > 0 else 0)
            ml_score = bet.get('ml_score', 0.5)
            question = bet.get('question', '')[:38]
            status = bet.get('status', 'pending')
            
            # Status styling
            if status == 'won':
                type_text = Text("🎉 WON", style="bold green")
            elif status == 'lost':
                type_text = Text("❌ LOST", style="bold red")
            else:
                type_text = Text("⏳ TAIL", style="bold yellow")
            
            table.add_row(
                time_str,
                type_text,
                f"${price:.3f}",
                f"{mult:.0f}x",
                f"{ml_score:.0%}",
                question + "..."
            )
        
        return Panel(
            table,
            title="[bold cyan]🔄 RECENT BETS[/]",
            box=box.ROUNDED,
            style="cyan"
        )
    
    def create_projections_panel(self, stats: dict) -> Panel:
        """Create profit projections panel."""
        content = Text()
        
        invested = stats['total_invested']
        avg_mult = stats['avg_mult']
        total_bets = stats['total_bets']
        
        content.append("💰 PROFIT PROJECTIONS\n\n", style=STYLES['header'])
        
        projections = [
            (0.5, "Conservative"),
            (1.0, "Expected"),
            (2.0, "Optimistic"),
            (5.0, "Best Case"),
        ]
        
        for hit_rate, label in projections:
            expected_wins = total_bets * (hit_rate / 100)
            expected_payout = expected_wins * 2 * avg_mult
            expected_profit = expected_payout - invested
            
            emoji = "📈" if expected_profit > 0 else "📉"
            style = STYLES['profit'] if expected_profit > 0 else STYLES['loss']
            
            content.append(f"  {hit_rate}% ", style=STYLES['highlight'])
            content.append(f"({label}): ", style=STYLES['muted'])
            content.append(f"${expected_profit:+,.0f} {emoji}\n", style=style)
        
        return Panel(
            content,
            box=box.ROUNDED,
            style="cyan",
            padding=(1, 2)
        )
    
    def create_footer(self, stats: dict) -> Panel:
        """Create footer panel."""
        content = Text()
        
        content.append("Bets: ", style=STYLES['muted'])
        content.append(f"{stats['total_bets']}", style=STYLES['value'])
        content.append("    |    ", style=STYLES['muted'])
        content.append("Invested: ", style=STYLES['muted'])
        content.append(f"${stats['total_invested']:,.2f}", style=STYLES['value'])
        content.append("    |    ", style=STYLES['muted'])
        content.append("Status: ", style=STYLES['muted'])
        content.append("PAPER TRADING", style=Style(color="yellow", bold=True))
        
        return Panel(
            content,
            box=box.ROUNDED,
            style="cyan",
            padding=(0, 2)
        )
    
    # -------------------------------------------------------------------------
    # MAIN LAYOUT
    # -------------------------------------------------------------------------
    
    def create_layout(self) -> Layout:
        """Create the main dashboard layout."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1)
        )
        
        layout["left"].split_column(
            Layout(name="positions", ratio=1),
            Layout(name="market", ratio=1)
        )
        
        layout["right"].split_column(
            Layout(name="bets", ratio=2),
            Layout(name="projections", ratio=1)
        )
        
        return layout
    
    def update_layout(self, layout: Layout, stats: dict, bets: list):
        """Update layout with current data."""
        layout["header"].update(self.create_header())
        layout["positions"].update(self.create_positions_panel(stats, bets))
        layout["market"].update(self.create_market_panel(stats))
        layout["bets"].update(self.create_bets_table(bets))
        layout["projections"].update(self.create_projections_panel(stats))
        layout["footer"].update(self.create_footer(stats))
    
    # -------------------------------------------------------------------------
    # RUN
    # -------------------------------------------------------------------------
    
    def run_static(self):
        """Run dashboard once (static view)."""
        bets, resolved = self.load_data()
        stats = self.calculate_stats(bets, resolved)
        
        layout = self.create_layout()
        self.update_layout(layout, stats, bets)
        
        console.print(layout)
    
    async def run_live(self, refresh_seconds: int = 30):
        """Run dashboard with live updates."""
        layout = self.create_layout()
        
        with Live(layout, console=console, refresh_per_second=1, screen=True) as live:
            while True:
                try:
                    bets, resolved = self.load_data()
                    stats = self.calculate_stats(bets, resolved)
                    self.update_layout(layout, stats, bets)
                    
                    await asyncio.sleep(refresh_seconds)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/]")
                    await asyncio.sleep(5)

# =============================================================================
# MAIN
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Polymarket Trading Terminal UI")
    parser.add_argument("--live", "-l", action="store_true", help="Run with live updates")
    parser.add_argument("--refresh", "-r", type=int, default=30, help="Refresh interval (seconds)")
    
    args = parser.parse_args()
    
    dashboard = TradingDashboard()
    
    if args.live:
        console.print("[cyan]Starting live dashboard... Press Ctrl+C to exit[/]")
        asyncio.run(dashboard.run_live(args.refresh))
    else:
        dashboard.run_static()

if __name__ == "__main__":
    main()
