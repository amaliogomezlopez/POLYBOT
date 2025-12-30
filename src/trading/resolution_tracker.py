"""
Resolution Tracker for Tail Bets
Monitors markets for resolution and updates bet outcomes
"""

import json
import httpx
import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from enum import Enum


class BetStatus(Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"


@dataclass
class ResolvedBet:
    """Bet with resolution information"""
    bet_id: str
    condition_id: str
    token_id: str
    question: str
    entry_price: float
    stake: float
    size: float
    potential_return: float
    status: BetStatus
    resolution_price: Optional[float] = None
    actual_return: Optional[float] = None
    resolved_at: Optional[str] = None
    profit_loss: Optional[float] = None


class ResolutionTracker:
    """
    Tracks market resolutions and updates bet outcomes
    """
    
    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"
    
    def __init__(self, bets_file: str = "data/tail_bot/bets.json"):
        self.bets_file = Path(bets_file)
        self.results_file = Path("data/tail_bot/results.json")
        self.stats_file = Path("data/tail_bot/stats.json")
        
        # Ensure directories exist
        self.bets_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing bets
        self.bets = self._load_bets()
        self.results = self._load_results()
        self.stats = self._load_stats()
        
    def _load_bets(self) -> list[dict]:
        """Load bets from file"""
        if self.bets_file.exists():
            bets = json.loads(self.bets_file.read_text())
            # Normalize status field (OPEN -> pending)
            for bet in bets:
                status = bet.get("status", "").lower()
                if status == "open" or status == "":
                    bet["status"] = "pending"
                elif status not in ["pending", "won", "lost", "cancelled"]:
                    bet["status"] = "pending"
            return bets
        return []
    
    def _load_results(self) -> list[dict]:
        """Load resolved bets"""
        if self.results_file.exists():
            return json.loads(self.results_file.read_text())
        return []
    
    def _load_stats(self) -> dict:
        """Load statistics"""
        if self.stats_file.exists():
            return json.loads(self.stats_file.read_text())
        return {
            "total_bets": 0,
            "resolved_bets": 0,
            "wins": 0,
            "losses": 0,
            "cancelled": 0,
            "total_invested": 0.0,
            "total_returned": 0.0,
            "total_profit": 0.0,
            "hit_rate": 0.0,
            "roi": 0.0,
            "best_win": 0.0,
            "avg_win_multiplier": 0.0,
            "last_updated": None
        }
    
    def _save_results(self):
        """Save results to file"""
        self.results_file.write_text(json.dumps(self.results, indent=2))
    
    def _save_stats(self):
        """Save stats to file"""
        self.stats["last_updated"] = datetime.now().isoformat()
        self.stats_file.write_text(json.dumps(self.stats, indent=2))
    
    async def get_market_status(self, condition_id: str) -> dict:
        """
        Get market status from Gamma API
        Returns: {resolved: bool, outcome: str, resolution_price: float}
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Try Gamma API first
                resp = await client.get(
                    f"{self.GAMMA_API}/markets/{condition_id}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "resolved": data.get("closed", False) or data.get("resolved", False),
                        "outcome": data.get("outcome", None),
                        "resolution_price": self._get_resolution_price(data),
                        "question": data.get("question", ""),
                        "raw": data
                    }
        except Exception as e:
            print(f"❌ Error fetching market {condition_id}: {e}")
        
        return {"resolved": False, "outcome": None, "resolution_price": None}
    
    def _get_resolution_price(self, market_data: dict) -> Optional[float]:
        """Extract resolution price from market data"""
        # If YES won, price = 1.0; if NO won, price = 0.0
        outcome = market_data.get("outcome")
        if outcome == "Yes":
            return 1.0
        elif outcome == "No":
            return 0.0
        return None
    
    async def check_resolutions(self) -> dict:
        """
        Check all pending bets for resolution
        Returns summary of newly resolved bets
        """
        print("🔍 Checking bet resolutions...")
        
        newly_resolved = []
        pending_count = 0
        
        for bet in self.bets:
            # Skip already processed bets
            if bet.get("status") != "pending":
                continue
            
            pending_count += 1
            condition_id = bet.get("condition_id")
            
            if not condition_id:
                continue
            
            # Check market status
            status = await self.get_market_status(condition_id)
            
            if status["resolved"]:
                # Determine outcome
                resolution_price = status["resolution_price"]
                
                if resolution_price is None:
                    bet["status"] = "cancelled"
                    bet["actual_return"] = bet["stake"]  # Refund
                    bet["profit_loss"] = 0.0
                elif resolution_price == 1.0:
                    # YES won - we won!
                    bet["status"] = "won"
                    bet["resolution_price"] = 1.0
                    bet["actual_return"] = bet["size"]  # Full size returned
                    bet["profit_loss"] = bet["size"] - bet["stake"]
                else:
                    # YES lost - we lost
                    bet["status"] = "lost"
                    bet["resolution_price"] = 0.0
                    bet["actual_return"] = 0.0
                    bet["profit_loss"] = -bet["stake"]
                
                bet["resolved_at"] = datetime.now().isoformat()
                newly_resolved.append(bet)
                
                print(f"  {'✅' if bet['status'] == 'won' else '❌'} {bet['question'][:50]}...")
                print(f"     Status: {bet['status'].upper()}, P/L: ${bet['profit_loss']:.2f}")
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)
        
        # Update stats
        self._update_stats()
        
        # Save everything
        self._save_bets()
        self._save_results()
        self._save_stats()
        
        summary = {
            "pending": pending_count - len(newly_resolved),
            "newly_resolved": len(newly_resolved),
            "wins": sum(1 for b in newly_resolved if b["status"] == "won"),
            "losses": sum(1 for b in newly_resolved if b["status"] == "lost"),
            "profit_loss": sum(b.get("profit_loss", 0) for b in newly_resolved)
        }
        
        return summary
    
    def _save_bets(self):
        """Save updated bets"""
        self.bets_file.write_text(json.dumps(self.bets, indent=2))
    
    def _update_stats(self):
        """Update cumulative statistics"""
        wins = [b for b in self.bets if b.get("status") == "won"]
        losses = [b for b in self.bets if b.get("status") == "lost"]
        cancelled = [b for b in self.bets if b.get("status") == "cancelled"]
        pending = [b for b in self.bets if b.get("status") == "pending"]
        
        total_invested = sum(b["stake"] for b in self.bets)
        total_returned = sum(b.get("actual_return", 0) for b in self.bets if b.get("status") != "pending")
        
        self.stats = {
            "total_bets": len(self.bets),
            "pending_bets": len(pending),
            "resolved_bets": len(wins) + len(losses) + len(cancelled),
            "wins": len(wins),
            "losses": len(losses),
            "cancelled": len(cancelled),
            "total_invested": total_invested,
            "total_returned": total_returned,
            "total_profit": total_returned - (len(wins) + len(losses)) * 2.0 if (len(wins) + len(losses)) > 0 else 0,
            "hit_rate": len(wins) / (len(wins) + len(losses)) * 100 if (len(wins) + len(losses)) > 0 else 0,
            "roi": (total_returned / total_invested - 1) * 100 if total_invested > 0 else 0,
            "best_win": max((b.get("actual_return", 0) for b in wins), default=0),
            "avg_win_multiplier": sum(b.get("actual_return", 0) / b["stake"] for b in wins) / len(wins) if wins else 0,
            "last_updated": datetime.now().isoformat()
        }
    
    def get_report(self) -> str:
        """Generate performance report"""
        self._update_stats()
        
        report = []
        report.append("=" * 60)
        report.append("📊 TAIL BETTING PERFORMANCE REPORT")
        report.append("=" * 60)
        report.append("")
        report.append(f"📈 Overall Stats:")
        report.append(f"   Total Bets:     {self.stats['total_bets']}")
        report.append(f"   Pending:        {self.stats.get('pending_bets', 0)}")
        report.append(f"   Resolved:       {self.stats['resolved_bets']}")
        report.append(f"   Wins:           {self.stats['wins']} ✅")
        report.append(f"   Losses:         {self.stats['losses']} ❌")
        report.append(f"   Cancelled:      {self.stats['cancelled']}")
        report.append("")
        report.append(f"💰 Financial:")
        report.append(f"   Total Invested: ${self.stats['total_invested']:.2f}")
        report.append(f"   Total Returned: ${self.stats['total_returned']:.2f}")
        report.append(f"   Net Profit:     ${self.stats['total_profit']:.2f}")
        report.append(f"   ROI:            {self.stats['roi']:.1f}%")
        report.append("")
        report.append(f"🎯 Performance:")
        report.append(f"   Hit Rate:       {self.stats['hit_rate']:.2f}%")
        report.append(f"   Best Win:       ${self.stats['best_win']:.2f}")
        report.append(f"   Avg Multiplier: {self.stats['avg_win_multiplier']:.1f}x")
        report.append("")
        
        # Expected vs Actual
        if self.stats['resolved_bets'] > 0:
            expected_hits = self.stats['resolved_bets'] * 0.02  # 2% expected
            report.append(f"📉 Expected vs Actual:")
            report.append(f"   Expected Wins:  {expected_hits:.1f} (at 2% hit rate)")
            report.append(f"   Actual Wins:    {self.stats['wins']}")
            if expected_hits > 0:
                report.append(f"   Performance:    {(self.stats['wins'] / expected_hits) * 100:.0f}% of expected")
        
        report.append("")
        report.append(f"⏰ Last Updated: {self.stats['last_updated']}")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def get_pending_bets_by_category(self) -> dict:
        """Group pending bets by category"""
        categories = {
            "political": [],
            "crypto": [],
            "sports": [],
            "finance": [],
            "tech": [],
            "other": []
        }
        
        for bet in self.bets:
            if bet.get("status") != "pending":
                continue
            
            question = bet.get("question", "").lower()
            
            if any(w in question for w in ["trump", "biden", "election", "congress", "senate"]):
                categories["political"].append(bet)
            elif any(w in question for w in ["bitcoin", "ethereum", "crypto", "btc", "eth"]):
                categories["crypto"].append(bet)
            elif any(w in question for w in ["game", "match", "nfl", "nba", "soccer"]):
                categories["sports"].append(bet)
            elif any(w in question for w in ["stock", "market", "gdp", "fed", "rate"]):
                categories["finance"].append(bet)
            elif any(w in question for w in ["google", "apple", "ai", "tech", "software"]):
                categories["tech"].append(bet)
            else:
                categories["other"].append(bet)
        
        return categories


class ResolutionMonitor:
    """
    Continuous monitor for bet resolutions
    Runs in background and checks periodically
    """
    
    def __init__(self, check_interval: int = 3600):  # Default 1 hour
        self.tracker = ResolutionTracker()
        self.check_interval = check_interval
        self.running = False
    
    async def start(self):
        """Start continuous monitoring"""
        self.running = True
        print(f"🚀 Starting Resolution Monitor (checking every {self.check_interval}s)")
        
        while self.running:
            try:
                summary = await self.tracker.check_resolutions()
                
                print(f"\n📋 Resolution Check Complete:")
                print(f"   Pending: {summary['pending']}")
                print(f"   Newly Resolved: {summary['newly_resolved']}")
                
                if summary['newly_resolved'] > 0:
                    print(f"   Wins: {summary['wins']}, Losses: {summary['losses']}")
                    print(f"   P/L: ${summary['profit_loss']:.2f}")
                    
                    # Print full report on new resolutions
                    print(self.tracker.get_report())
                
            except Exception as e:
                print(f"❌ Monitor error: {e}")
            
            # Wait for next check
            await asyncio.sleep(self.check_interval)
    
    def stop(self):
        """Stop monitoring"""
        self.running = False


async def main():
    """Run resolution check"""
    tracker = ResolutionTracker()
    
    print("🔍 Checking all pending bets for resolution...")
    print("")
    
    summary = await tracker.check_resolutions()
    
    print("")
    print(tracker.get_report())
    
    # Show category breakdown
    print("\n📂 Pending Bets by Category:")
    categories = tracker.get_pending_bets_by_category()
    for cat, bets in categories.items():
        if bets:
            print(f"   {cat.title()}: {len(bets)} bets (${sum(b['stake'] for b in bets):.2f})")


if __name__ == "__main__":
    asyncio.run(main())
