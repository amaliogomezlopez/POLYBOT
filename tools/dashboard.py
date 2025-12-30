"""
Tail Bot Dashboard - Real-time monitoring and status
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional


class TailBotDashboard:
    """
    Consolidated dashboard for tail betting strategy monitoring
    """
    
    def __init__(self):
        self.data_dir = Path("data/tail_bot")
        self.analysis_dir = Path("analysis/spon")
    
    def load_json(self, filepath: Path) -> dict | list:
        """Safely load JSON file"""
        if filepath.exists():
            return json.loads(filepath.read_text())
        return {}
    
    def get_bets_summary(self) -> dict:
        """Get summary of all bets"""
        bets = self.load_json(self.data_dir / "bets.json")
        if not bets:
            return {"total": 0}
        
        # Normalize status
        status_counts = {"pending": 0, "won": 0, "lost": 0, "cancelled": 0}
        total_invested = 0
        total_returned = 0
        potential_returns = []
        
        for bet in bets:
            status = bet.get("status", "OPEN").lower()
            if status == "open":
                status = "pending"
            
            status_counts[status] = status_counts.get(status, 0) + 1
            total_invested += bet.get("stake", 2.0)
            
            if status == "won":
                total_returned += bet.get("actual_return", bet.get("size", 0))
            
            potential_returns.append(bet.get("potential_return", 0))
        
        return {
            "total": len(bets),
            "status": status_counts,
            "total_invested": total_invested,
            "total_returned": total_returned,
            "potential_returns": {
                "min": min(potential_returns) if potential_returns else 0,
                "max": max(potential_returns) if potential_returns else 0,
                "avg": sum(potential_returns) / len(potential_returns) if potential_returns else 0
            }
        }
    
    def get_tail_markets_summary(self) -> dict:
        """Get summary of discovered tail markets"""
        markets = self.load_json(self.analysis_dir / "tail_markets_found.json")
        if not markets:
            return {"total": 0}
        
        categories = {}
        price_buckets = {"0.01": 0, "0.02": 0, "0.03": 0, "0.04": 0, "0.05+": 0}
        
        for market in markets:
            # Price buckets
            price = market.get("yes_price", 0)
            if price <= 0.01:
                price_buckets["0.01"] += 1
            elif price <= 0.02:
                price_buckets["0.02"] += 1
            elif price <= 0.03:
                price_buckets["0.03"] += 1
            elif price <= 0.04:
                price_buckets["0.04"] += 1
            else:
                price_buckets["0.05+"] += 1
            
            # Categories
            question = market.get("question", "").lower()
            if any(w in question for w in ["trump", "biden", "election"]):
                cat = "political"
            elif any(w in question for w in ["bitcoin", "ethereum", "crypto"]):
                cat = "crypto"
            elif any(w in question for w in ["game", "nfl", "nba"]):
                cat = "sports"
            else:
                cat = "other"
            
            categories[cat] = categories.get(cat, 0) + 1
        
        return {
            "total": len(markets),
            "price_buckets": price_buckets,
            "categories": categories
        }
    
    def get_stats(self) -> dict:
        """Get overall statistics"""
        return self.load_json(self.data_dir / "stats.json")
    
    def get_state(self) -> dict:
        """Get bot state"""
        return self.load_json(self.data_dir / "state.json")
    
    def print_dashboard(self):
        """Print formatted dashboard"""
        bets = self.get_bets_summary()
        markets = self.get_tail_markets_summary()
        stats = self.get_stats()
        state = self.get_state()
        
        print("")
        print("╔" + "═" * 68 + "╗")
        print("║" + " 🎲 TAIL BETTING BOT DASHBOARD ".center(68) + "║")
        print("║" + f" @Spon Strategy Implementation ".center(68) + "║")
        print("╠" + "═" * 68 + "╣")
        
        # Bot Status
        print("║" + " 🤖 BOT STATUS ".ljust(68) + "║")
        print("║" + "─" * 68 + "║")
        
        if state:
            running = "🟢 RUNNING" if state.get("running", False) else "🔴 STOPPED"
            cycles = state.get("cycles_completed", 0)
            last_scan = state.get("last_scan_time", "Never")
            print(f"║   Status:       {running:<50}║")
            print(f"║   Cycles:       {cycles:<50}║")
            print(f"║   Last Scan:    {str(last_scan)[:40]:<50}║")
        else:
            print("║   Status:       🔴 NOT STARTED" + " " * 38 + "║")
        
        print("╠" + "═" * 68 + "╣")
        
        # Bets Summary
        print("║" + " 📊 BETS SUMMARY ".ljust(68) + "║")
        print("║" + "─" * 68 + "║")
        
        if bets["total"] > 0:
            status = bets.get("status", {})
            print(f"║   Total Bets:      {bets['total']:<48}║")
            print(f"║   ├─ Pending:      {status.get('pending', 0):<48}║")
            print(f"║   ├─ Won:          {status.get('won', 0)} ✅{'':<44}║")
            print(f"║   ├─ Lost:         {status.get('lost', 0)} ❌{'':<44}║")
            print(f"║   └─ Cancelled:    {status.get('cancelled', 0):<48}║")
            print("║" + " " * 68 + "║")
            print(f"║   💰 Investment:   ${bets['total_invested']:.2f}".ljust(69) + "║")
            print(f"║   💵 Returned:     ${bets['total_returned']:.2f}".ljust(69) + "║")
            pot = bets.get("potential_returns", {})
            print(f"║   📈 Potential:    {pot.get('min', 0):.0f}x - {pot.get('max', 0):.0f}x (avg {pot.get('avg', 0):.0f}x)".ljust(69) + "║")
        else:
            print("║   No bets placed yet".ljust(68) + "║")
        
        print("╠" + "═" * 68 + "╣")
        
        # Market Discovery
        print("║" + " 🔍 MARKET DISCOVERY ".ljust(68) + "║")
        print("║" + "─" * 68 + "║")
        
        if markets["total"] > 0:
            print(f"║   Tail Markets Found: {markets['total']}".ljust(68) + "║")
            print("║" + " " * 68 + "║")
            print("║   Price Distribution:".ljust(68) + "║")
            pb = markets.get("price_buckets", {})
            print(f"║   ├─ ≤$0.01:  {pb.get('0.01', 0):>4} markets ({pb.get('0.01', 0)/markets['total']*100:.0f}%)".ljust(69) + "║")
            print(f"║   ├─ ≤$0.02:  {pb.get('0.02', 0):>4} markets ({pb.get('0.02', 0)/markets['total']*100:.0f}%)".ljust(69) + "║")
            print(f"║   ├─ ≤$0.03:  {pb.get('0.03', 0):>4} markets ({pb.get('0.03', 0)/markets['total']*100:.0f}%)".ljust(69) + "║")
            print(f"║   └─ ≤$0.04:  {pb.get('0.04', 0):>4} markets ({pb.get('0.04', 0)/markets['total']*100:.0f}%)".ljust(69) + "║")
        else:
            print("║   No tail markets discovered yet".ljust(68) + "║")
        
        print("╠" + "═" * 68 + "╣")
        
        # Performance Metrics
        print("║" + " 📈 PERFORMANCE METRICS ".ljust(68) + "║")
        print("║" + "─" * 68 + "║")
        
        if stats and stats.get("resolved_bets", 0) > 0:
            print(f"║   Hit Rate:        {stats.get('hit_rate', 0):.2f}%".ljust(68) + "║")
            print(f"║   ROI:             {stats.get('roi', 0):.1f}%".ljust(68) + "║")
            print(f"║   Best Win:        ${stats.get('best_win', 0):.2f}".ljust(68) + "║")
            print(f"║   Avg Multiplier:  {stats.get('avg_win_multiplier', 0):.1f}x".ljust(68) + "║")
        else:
            print("║   📝 No resolved bets yet - waiting for market resolutions...".ljust(68) + "║")
        
        print("╠" + "═" * 68 + "╣")
        
        # Strategy Info
        print("║" + " ⚙️  STRATEGY CONFIGURATION ".ljust(68) + "║")
        print("║" + "─" * 68 + "║")
        print("║   📌 Max YES Price:  $0.04 (4 cents)".ljust(68) + "║")
        print("║   💵 Stake per Bet:  $2.00 (fixed)".ljust(68) + "║")
        print("║   🔄 Scan Interval:  60 seconds".ljust(68) + "║")
        print("║   🎯 Target:         100x-1000x returns".ljust(68) + "║")
        print("║   📊 Expected Hit:   ~2-3% (1 in 40-50)".ljust(68) + "║")
        
        print("╠" + "═" * 68 + "╣")
        
        # Monte Carlo Projections
        print("║" + " 🎰 MONTE CARLO PROJECTIONS (100 bets) ".ljust(68) + "║")
        print("║" + "─" * 68 + "║")
        print("║   Conservative (1% hit, 40x):  -$120 avg, 9% profit chance".ljust(68) + "║")
        print("║   Moderate (2% hit, 50x):      -$1 avg, 46% profit chance".ljust(68) + "║")
        print("║   Optimistic (3% hit, 60x):    +$162 avg, 76% profit chance ✅".ljust(68) + "║")
        
        print("╠" + "═" * 68 + "╣")
        
        # Actions
        print("║" + " 🛠️  QUICK ACTIONS ".ljust(68) + "║")
        print("║" + "─" * 68 + "║")
        print("║   Run Bot:     python -m src.trading.tail_bot".ljust(68) + "║")
        print("║   Check Res:   python -m src.trading.resolution_tracker".ljust(68) + "║")
        print("║   Find Tails:  python tools/find_tails.py".ljust(68) + "║")
        print("║   Backtest:    python tools/backtest_tails.py".ljust(68) + "║")
        
        print("╚" + "═" * 68 + "╝")
        
        print(f"\n⏰ Dashboard updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    """Display dashboard"""
    dashboard = TailBotDashboard()
    dashboard.print_dashboard()


if __name__ == "__main__":
    main()
