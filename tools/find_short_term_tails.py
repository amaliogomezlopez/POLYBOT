"""
Short-Term Tail Finder - Find tail bets that resolve SOON
For faster data collection and XGBoost training
"""

import asyncio
import httpx
import json
from datetime import datetime, timedelta
from pathlib import Path


class ShortTermTailFinder:
    """
    Find tail opportunities that resolve within days (not months)
    Better for fast data collection and strategy validation
    """
    
    CLOB_API = "https://clob.polymarket.com"
    GAMMA_API = "https://gamma-api.polymarket.com"
    
    def __init__(self):
        self.output_dir = Path("data/short_term_tails")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_markets_expiring_soon(self, days: int = 7) -> list[dict]:
        """Get markets that expire within X days"""
        print(f"🔍 Searching for markets expiring within {days} days...")
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                # Get markets from Gamma API
                resp = await client.get(
                    f"{self.GAMMA_API}/markets",
                    params={
                        "active": "true",
                        "limit": 500,
                        "order": "endDate",
                        "ascending": "true"  # Soonest first
                    }
                )
                
                if resp.status_code != 200:
                    print(f"❌ Gamma API error: {resp.status_code}")
                    return []
                
                markets = resp.json()
                print(f"   Got {len(markets)} markets from Gamma API")
                
                # Filter by end date
                now = datetime.now()
                cutoff = now + timedelta(days=days)
                
                expiring_soon = []
                for m in markets:
                    end_date_str = m.get("endDate")
                    if not end_date_str:
                        continue
                    
                    try:
                        # Parse ISO date
                        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                        end_date = end_date.replace(tzinfo=None)
                        
                        if end_date <= cutoff:
                            m["parsed_end_date"] = end_date.isoformat()
                            m["days_to_expiry"] = (end_date - now).days
                            expiring_soon.append(m)
                    except:
                        pass
                
                print(f"   Found {len(expiring_soon)} markets expiring within {days} days")
                return expiring_soon
                
            except Exception as e:
                print(f"❌ Error: {e}")
                return []
    
    async def get_clob_prices(self) -> dict:
        """Get current prices from CLOB API"""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(f"{self.CLOB_API}/sampling-markets")
                if resp.status_code != 200:
                    return {}
                
                data = resp.json()
                markets = data.get("data", []) if isinstance(data, dict) else data
                
                prices = {}
                for m in markets:
                    condition_id = m.get("condition_id")
                    tokens = m.get("tokens", [])
                    for token in tokens:
                        if token.get("outcome") == "Yes":
                            prices[condition_id] = float(token.get("price", 1))
                
                return prices
                
            except Exception as e:
                print(f"❌ CLOB error: {e}")
                return {}
    
    async def find_short_term_tails(
        self,
        max_price: float = 0.05,
        max_days: int = 7
    ) -> list[dict]:
        """Find tail bets that resolve soon"""
        
        # Get expiring markets
        expiring = await self.get_markets_expiring_soon(max_days)
        
        # Get current prices
        prices = await self.get_clob_prices()
        print(f"   Got prices for {len(prices)} markets")
        
        # Find tails
        tails = []
        for m in expiring:
            condition_id = m.get("conditionId", m.get("condition_id", ""))
            
            # Try to match with CLOB data
            yes_price = prices.get(condition_id)
            
            # Also try tokens from Gamma
            if yes_price is None:
                tokens = m.get("tokens", [])
                for token in tokens:
                    if token.get("outcome") == "Yes":
                        yes_price = float(token.get("price", 1))
            
            if yes_price and yes_price <= max_price:
                tails.append({
                    "condition_id": condition_id,
                    "question": m.get("question", ""),
                    "yes_price": yes_price,
                    "potential": 1 / yes_price if yes_price > 0 else 0,
                    "end_date": m.get("parsed_end_date"),
                    "days_to_expiry": m.get("days_to_expiry"),
                    "category": self._detect_category(m.get("question", ""))
                })
        
        # Sort by expiry (soonest first)
        tails.sort(key=lambda x: x.get("days_to_expiry", 999))
        
        return tails
    
    def _detect_category(self, question: str) -> str:
        """Simple category detection"""
        q = question.lower()
        
        if any(w in q for w in ["trump", "biden", "election", "congress"]):
            return "political"
        if any(w in q for w in ["bitcoin", "ethereum", "crypto", "btc"]):
            return "crypto"
        if any(w in q for w in ["game", "nfl", "nba", "match", "win"]):
            return "sports"
        if any(w in q for w in ["google", "apple", "ai", "microsoft"]):
            return "tech"
        if any(w in q for w in ["stock", "fed", "rate"]):
            return "finance"
        
        return "other"
    
    async def run(self):
        """Find and display short-term tail opportunities"""
        print("=" * 70)
        print("🎯 SHORT-TERM TAIL FINDER")
        print("   Finding tail bets that resolve SOON")
        print("=" * 70)
        print()
        
        tails = await self.find_short_term_tails(max_price=0.10, max_days=14)
        
        if not tails:
            print("❌ No short-term tail opportunities found")
            return
        
        print(f"\n✅ Found {len(tails)} short-term tail opportunities:\n")
        
        print(f"{'#':<3} {'Days':<5} {'Price':<8} {'Mult':<8} {'Cat':<10} {'Question'}")
        print("-" * 70)
        
        for i, t in enumerate(tails[:30], 1):
            q_short = t['question'][:35] + "..." if len(t['question']) > 35 else t['question']
            print(f"{i:<3} {t['days_to_expiry']:<5} ${t['yes_price']:.3f}  {t['potential']:>6.0f}x  {t['category']:<10} {q_short}")
        
        print("-" * 70)
        print()
        
        # Summary by days
        by_days = {}
        for t in tails:
            d = t['days_to_expiry']
            if d not in by_days:
                by_days[d] = []
            by_days[d].append(t)
        
        print("📊 By Days to Expiry:")
        for days in sorted(by_days.keys()):
            count = len(by_days[days])
            avg_mult = sum(t['potential'] for t in by_days[days]) / count
            print(f"   {days} days: {count} markets (avg {avg_mult:.0f}x)")
        
        # Save to file
        output = {
            "timestamp": datetime.now().isoformat(),
            "total": len(tails),
            "opportunities": tails[:50]
        }
        
        output_file = self.output_dir / "short_term_tails.json"
        output_file.write_text(json.dumps(output, indent=2))
        print(f"\n💾 Saved to: {output_file}")
        
        # Show immediate opportunities (resolving today/tomorrow)
        immediate = [t for t in tails if t['days_to_expiry'] <= 1]
        if immediate:
            print(f"\n⚡ IMMEDIATE OPPORTUNITIES (resolve in 0-1 days):")
            for t in immediate[:10]:
                print(f"   • {t['question'][:50]}...")
                print(f"     Price: ${t['yes_price']:.3f} | Potential: {t['potential']:.0f}x | Days: {t['days_to_expiry']}")
        
        return tails


async def main():
    finder = ShortTermTailFinder()
    await finder.run()


if __name__ == "__main__":
    asyncio.run(main())
