"""
📊 TAIL BETTING DASHBOARD
=========================
Real-time monitoring of tail bets, performance, and market scanning.

Features:
- Live bet status tracking
- Resolution monitoring
- New opportunity scanner
- P&L tracking
- XGBoost training data collection
"""

import asyncio
import json
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import sys
import os

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class BetSummary:
    total_bets: int
    total_invested: float
    pending: int
    resolved: int
    won: int
    lost: int
    total_pnl: float
    roi: float
    avg_multiplier: float
    best_bet: Optional[dict] = None
    worst_bet: Optional[dict] = None

# =============================================================================
# DASHBOARD CLASS
# =============================================================================

class TailDashboard:
    """
    Comprehensive dashboard for tail betting system.
    """
    
    def __init__(self):
        self.bets_file = Path("data/tail_bot/bets.json")
        self.resolved_file = Path("data/tail_bot/resolved.json")
        self.client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30)
        return self
        
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    # -------------------------------------------------------------------------
    # BET LOADING
    # -------------------------------------------------------------------------
    
    def load_bets(self) -> list[dict]:
        """Load all bets from file."""
        if self.bets_file.exists():
            return json.loads(self.bets_file.read_text())
        return []
    
    def load_resolved(self) -> list[dict]:
        """Load resolved bets."""
        if self.resolved_file.exists():
            return json.loads(self.resolved_file.read_text())
        return []
    
    def save_bets(self, bets: list[dict]):
        """Save bets to file."""
        self.bets_file.parent.mkdir(parents=True, exist_ok=True)
        self.bets_file.write_text(json.dumps(bets, indent=2, default=str))
    
    def save_resolved(self, resolved: list[dict]):
        """Save resolved bets."""
        self.resolved_file.parent.mkdir(parents=True, exist_ok=True)
        self.resolved_file.write_text(json.dumps(resolved, indent=2, default=str))
    
    # -------------------------------------------------------------------------
    # RESOLUTION CHECKING (Multiple methods)
    # -------------------------------------------------------------------------
    
    async def check_resolution_via_clob(self, condition_id: str) -> Optional[str]:
        """
        Check resolution via CLOB API.
        Returns 'YES', 'NO', or None if not resolved.
        """
        try:
            url = f"https://clob.polymarket.com/markets/{condition_id}"
            resp = await self.client.get(url)
            
            if resp.status_code != 200:
                return None
                
            data = resp.json()
            
            # Check if market is closed
            if data.get("closed"):
                # Get final prices - winner has price = 1.0
                tokens = data.get("tokens", [])
                for token in tokens:
                    if float(token.get("price", 0)) >= 0.99:
                        return token.get("outcome")
            
            return None
            
        except Exception as e:
            return None
    
    async def check_resolution_via_gamma(self, market_slug: str) -> Optional[dict]:
        """
        Check resolution via Gamma API using slug.
        Returns market data or None.
        """
        try:
            url = f"https://gamma-api.polymarket.com/markets"
            resp = await self.client.get(url, params={"slug": market_slug})
            
            if resp.status_code != 200:
                return None
                
            markets = resp.json()
            if markets:
                return markets[0]
            return None
            
        except Exception:
            return None
    
    async def check_single_bet_resolution(self, bet: dict) -> tuple[str, Optional[float]]:
        """
        Check if a single bet has resolved.
        Returns: (status, payout) where status is 'pending', 'won', 'lost'
        """
        condition_id = bet.get("condition_id")
        if not condition_id:
            return "pending", None
        
        # Method 1: Try CLOB API
        result = await self.check_resolution_via_clob(condition_id)
        
        if result is not None:
            # Market resolved!
            if result == "Yes":
                # YES won - our bet won!
                payout = bet.get("stake", 2) * bet.get("potential_multiplier", 50)
                return "won", payout
            else:
                # NO won - our bet lost
                return "lost", 0
        
        return "pending", None
    
    async def check_all_resolutions(self) -> dict:
        """
        Check resolution status of all pending bets.
        Returns summary of changes.
        """
        bets = self.load_bets()
        resolved = self.load_resolved()
        resolved_ids = {r.get("condition_id") for r in resolved}
        
        changes = {
            "newly_resolved": [],
            "total_checked": 0,
            "still_pending": 0
        }
        
        pending_bets = [b for b in bets if b.get("status") == "pending" 
                        and b.get("condition_id") not in resolved_ids]
        
        print(f"\n🔍 Checking {len(pending_bets)} pending bets...")
        
        for i, bet in enumerate(pending_bets):
            status, payout = await self.check_single_bet_resolution(bet)
            changes["total_checked"] += 1
            
            if status != "pending":
                bet["status"] = status
                bet["resolved_at"] = datetime.now().isoformat()
                bet["payout"] = payout or 0
                bet["profit"] = (payout or 0) - bet.get("stake", 2)
                
                resolved.append(bet)
                changes["newly_resolved"].append(bet)
                
                emoji = "🎉" if status == "won" else "❌"
                print(f"  {emoji} {status.upper()}: {bet.get('question', '')[:40]}...")
                if status == "won":
                    print(f"     💰 Payout: ${payout:.2f} (Profit: ${bet['profit']:.2f})")
            else:
                changes["still_pending"] += 1
            
            # Progress
            if (i + 1) % 10 == 0:
                print(f"  ... checked {i + 1}/{len(pending_bets)}")
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)
        
        # Save updated data
        if changes["newly_resolved"]:
            self.save_bets(bets)
            self.save_resolved(resolved)
        
        return changes
    
    # -------------------------------------------------------------------------
    # SUMMARY CALCULATION
    # -------------------------------------------------------------------------
    
    def calculate_summary(self) -> BetSummary:
        """Calculate comprehensive bet summary."""
        bets = self.load_bets()
        resolved = self.load_resolved()
        
        total_bets = len(bets)
        total_invested = sum(b.get("stake", 2) for b in bets)
        
        pending = len([b for b in bets if b.get("status") == "pending"])
        won = len([r for r in resolved if r.get("status") == "won"])
        lost = len([r for r in resolved if r.get("status") == "lost"])
        
        total_payout = sum(r.get("payout", 0) for r in resolved)
        total_lost = sum(r.get("stake", 2) for r in resolved if r.get("status") == "lost")
        total_pnl = total_payout - total_lost
        
        roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        
        # Calculate average multiplier - support both formats
        multipliers = []
        for b in bets:
            mult = b.get("potential_multiplier")
            if not mult:
                price = b.get("entry_price") or b.get("price", 0)
                mult = round(1/price, 1) if price > 0 else 50
            multipliers.append(mult)
        avg_multiplier = sum(multipliers) / max(len(multipliers), 1)
        
        # Find best/worst
        best_bet = None
        worst_bet = None
        if resolved:
            won_bets = [r for r in resolved if r.get("status") == "won"]
            if won_bets:
                best_bet = max(won_bets, key=lambda x: x.get("payout", 0))
            
            lost_bets = [r for r in resolved if r.get("status") == "lost"]
            if lost_bets:
                worst_bet = min(lost_bets, key=lambda x: x.get("profit", 0))
        
        return BetSummary(
            total_bets=total_bets,
            total_invested=total_invested,
            pending=pending,
            resolved=len(resolved),
            won=won,
            lost=lost,
            total_pnl=total_pnl,
            roi=roi,
            avg_multiplier=avg_multiplier,
            best_bet=best_bet,
            worst_bet=worst_bet
        )
    
    # -------------------------------------------------------------------------
    # MARKET SCANNING
    # -------------------------------------------------------------------------
    
    async def scan_new_opportunities(self) -> list[dict]:
        """Scan for new tail betting opportunities."""
        try:
            url = "https://clob.polymarket.com/sampling-markets?next_cursor=LTE="
            resp = await self.client.get(url)
            
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            markets = data.get("data", [])
            
            opportunities = []
            existing_ids = {b.get("condition_id") for b in self.load_bets()}
            
            for market in markets:
                condition_id = market.get("condition_id")
                
                # Skip if already bet
                if condition_id in existing_ids:
                    continue
                
                # Check for tail opportunity (YES < $0.04)
                tokens = market.get("tokens", [])
                for token in tokens:
                    if token.get("outcome") == "Yes":
                        price = float(token.get("price", 1))
                        if price < 0.04 and price > 0.001:
                            opportunities.append({
                                "condition_id": condition_id,
                                "question": market.get("question", ""),
                                "price": price,
                                "potential_multiplier": round(1 / price, 1) if price > 0 else 0,
                                "market_slug": market.get("market_slug", "")
                            })
                        break
            
            # Sort by multiplier
            opportunities.sort(key=lambda x: x.get("potential_multiplier", 0), reverse=True)
            
            return opportunities
            
        except Exception as e:
            print(f"Error scanning: {e}")
            return []
    
    # -------------------------------------------------------------------------
    # DISPLAY
    # -------------------------------------------------------------------------
    
    def display_header(self):
        """Display dashboard header."""
        print("\n" + "=" * 70)
        print("  🎯 TAIL BETTING DASHBOARD")
        print(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)
    
    def display_summary(self, summary: BetSummary):
        """Display bet summary."""
        print("\n📊 PORTFOLIO SUMMARY")
        print("-" * 40)
        print(f"  Total Bets:     {summary.total_bets}")
        print(f"  Total Invested: ${summary.total_invested:.2f}")
        print(f"  Avg Multiplier: {summary.avg_multiplier:.1f}x")
        print()
        print(f"  ⏳ Pending:     {summary.pending}")
        print(f"  ✅ Resolved:    {summary.resolved}")
        print(f"     Won:         {summary.won}")
        print(f"     Lost:        {summary.lost}")
        print()
        
        if summary.resolved > 0:
            hit_rate = summary.won / summary.resolved * 100
            print(f"  📈 Hit Rate:    {hit_rate:.1f}%")
            print(f"  💰 Total P&L:   ${summary.total_pnl:+.2f}")
            print(f"  📊 ROI:         {summary.roi:+.1f}%")
            
            if summary.best_bet:
                print(f"\n  🏆 Best Win:    ${summary.best_bet.get('payout', 0):.2f}")
                print(f"     {summary.best_bet.get('question', '')[:40]}...")
        else:
            print("  ⏳ Waiting for first resolution...")
            print("     (Tail bets can take weeks/months to resolve)")
    
    def display_recent_bets(self, limit: int = 5):
        """Display recent bets."""
        bets = self.load_bets()
        recent = sorted(bets, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
        
        print(f"\n📝 RECENT BETS (Last {limit})")
        print("-" * 40)
        
        for bet in recent:
            # Support both old (price) and new (entry_price) format
            price = bet.get("entry_price") or bet.get("price", 0)
            mult = bet.get("potential_multiplier") or (round(1/price, 1) if price > 0 else 0)
            q = bet.get("question", "")[:35]
            status = bet.get("status", "pending")
            
            emoji = {"pending": "⏳", "won": "🎉", "lost": "❌"}.get(status, "❓")
            print(f"  {emoji} ${price:.3f} ({mult:.0f}x) - {q}...")
    
    def display_opportunities(self, opportunities: list[dict], limit: int = 10):
        """Display new opportunities."""
        print(f"\n🔍 NEW OPPORTUNITIES ({len(opportunities)} found)")
        print("-" * 40)
        
        if not opportunities:
            print("  No new tail opportunities at this time.")
            return
        
        for opp in opportunities[:limit]:
            price = opp.get("price", 0)
            mult = opp.get("potential_multiplier", 0)
            q = opp.get("question", "")[:40]
            print(f"  💎 ${price:.3f} ({mult:.0f}x) - {q}...")
    
    def display_xgboost_status(self):
        """Display XGBoost training data status."""
        resolved = self.load_resolved()
        
        print("\n🤖 XGBOOST TRAINING STATUS")
        print("-" * 40)
        print(f"  Resolved bets (training data): {len(resolved)}")
        
        if len(resolved) < 30:
            print(f"  Need {30 - len(resolved)} more for initial training")
            print("  Status: ⏳ Collecting data...")
        else:
            won = len([r for r in resolved if r.get("status") == "won"])
            lost = len(resolved) - won
            print(f"  ✅ Ready for training!")
            print(f"  Wins: {won}, Losses: {lost}")
            print(f"  Hit Rate: {won / len(resolved) * 100:.1f}%")
    
    def display_required_hit_rate(self):
        """Display breakeven analysis."""
        bets = self.load_bets()
        
        print("\n📐 BREAKEVEN ANALYSIS")
        print("-" * 40)
        
        if not bets:
            print("  No bets to analyze.")
            return
        
        # Calculate average multiplier - support both formats
        multipliers = []
        for b in bets:
            mult = b.get("potential_multiplier")
            if not mult:
                price = b.get("entry_price") or b.get("price", 0)
                mult = round(1/price, 1) if price > 0 else 50
            multipliers.append(mult)
        avg_mult = sum(multipliers) / len(multipliers)
        
        required_hit_rate = 1 / avg_mult * 100
        
        print(f"  Average Multiplier: {avg_mult:.1f}x")
        print(f"  Required Hit Rate:  {required_hit_rate:.2f}%")
        print(f"  (Need 1 win per {int(avg_mult)} bets to break even)")
        
        # Projection at different hit rates
        total_bets = len(bets)
        total_invested = sum(b.get("stake", 2) for b in bets)
        stake = total_invested / total_bets
        
        print(f"\n  💰 Projections for {total_bets} bets (${total_invested:.0f} invested):")
        for hit_rate in [0.5, 1.0, 2.0, 5.0]:
            expected_wins = total_bets * (hit_rate / 100)
            expected_payout = expected_wins * stake * avg_mult
            expected_profit = expected_payout - total_invested
            emoji = "📈" if expected_profit > 0 else "📉"
            print(f"     {hit_rate}% hits: {expected_wins:.1f} wins → ${expected_profit:+.0f} {emoji}")

    # -------------------------------------------------------------------------
    # MAIN RUN
    # -------------------------------------------------------------------------
    
    async def run_once(self, scan: bool = True, check_resolutions: bool = True):
        """Run dashboard once."""
        self.display_header()
        
        # Summary
        summary = self.calculate_summary()
        self.display_summary(summary)
        
        # Recent bets
        self.display_recent_bets()
        
        # Resolution check
        if check_resolutions:
            changes = await self.check_all_resolutions()
            if changes["newly_resolved"]:
                print(f"\n🆕 {len(changes['newly_resolved'])} bets resolved!")
                # Recalculate summary
                summary = self.calculate_summary()
                self.display_summary(summary)
        
        # New opportunities
        if scan:
            opportunities = await self.scan_new_opportunities()
            self.display_opportunities(opportunities)
        
        # XGBoost status
        self.display_xgboost_status()
        
        # Breakeven analysis
        self.display_required_hit_rate()
        
        print("\n" + "=" * 70)
        print("  Use --place to place new bets on opportunities")
        print("  Use --continuous to run continuously")
        print("=" * 70 + "\n")
        
        return summary
    
    async def run_continuous(self, interval_minutes: int = 5):
        """Run dashboard continuously."""
        print(f"🔄 Running dashboard every {interval_minutes} minutes...")
        print("   Press Ctrl+C to stop\n")
        
        while True:
            try:
                await self.run_once()
                print(f"\n⏰ Next update in {interval_minutes} minutes...")
                await asyncio.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                print("\n\n👋 Dashboard stopped.")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                await asyncio.sleep(60)

# =============================================================================
# MAIN
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Tail Betting Dashboard")
    parser.add_argument("--continuous", "-c", action="store_true", help="Run continuously")
    parser.add_argument("--interval", "-i", type=int, default=5, help="Update interval (minutes)")
    parser.add_argument("--no-scan", action="store_true", help="Skip opportunity scanning")
    parser.add_argument("--no-check", action="store_true", help="Skip resolution checking")
    
    args = parser.parse_args()
    
    async with TailDashboard() as dashboard:
        if args.continuous:
            await dashboard.run_continuous(args.interval)
        else:
            await dashboard.run_once(
                scan=not args.no_scan,
                check_resolutions=not args.no_check
            )

if __name__ == "__main__":
    asyncio.run(main())
