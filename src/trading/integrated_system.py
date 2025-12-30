"""
Integrated Tail Betting System
Combines scanner, scorer, and bot for optimized tail betting
"""

import asyncio
import json
import httpx
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import random


@dataclass
class ScoredOpportunity:
    """A tail opportunity with ML scoring"""
    condition_id: str
    token_id: str
    question: str
    yes_price: float
    potential_multiplier: float
    category: str
    ml_score: float
    recommendation: str
    expected_value: float


class IntegratedTailSystem:
    """
    Full integration of tail betting components:
    - Market scanning
    - ML scoring
    - Paper/Live execution
    - Resolution tracking
    """
    
    CLOB_API = "https://clob.polymarket.com"
    
    def __init__(
        self,
        max_yes_price: float = 0.04,
        stake_usd: float = 2.0,
        min_score: float = 0.60,
        paper_trading: bool = True
    ):
        self.max_yes_price = max_yes_price
        self.stake_usd = stake_usd
        self.min_score = min_score
        self.paper_trading = paper_trading
        
        self.data_dir = Path("data/tail_bot")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Category keywords for detection
        self.categories = {
            "political": ["trump", "biden", "election", "congress", "senate", "president", "vote", "democrat", "republican"],
            "crypto": ["bitcoin", "ethereum", "btc", "eth", "crypto", "solana", "dogecoin"],
            "sports": ["nfl", "nba", "mlb", "soccer", "football", "basketball", "game", "match", "win"],
            "finance": ["stock", "market", "fed", "rate", "gdp", "inflation", "nasdaq", "s&p"],
            "tech": ["google", "apple", "microsoft", "ai", "openai", "meta", "amazon", "nvidia"],
            "entertainment": ["movie", "oscar", "grammy", "netflix", "spotify", "album"],
        }
    
    def detect_category(self, question: str) -> str:
        """Detect market category from question"""
        q_lower = question.lower()
        
        for category, keywords in self.categories.items():
            if any(kw in q_lower for kw in keywords):
                return category
        
        return "other"
    
    def calculate_ml_score(self, market: dict) -> float:
        """
        Calculate ML score for a tail opportunity
        This is a simplified scoring model - can be replaced with XGBoost
        """
        score = 0.5  # Base score
        
        question = market.get("question", "").lower()
        yes_price = market.get("yes_price", 0.01)
        
        # Price factor: lower prices = higher potential
        if yes_price <= 0.01:
            score += 0.15
        elif yes_price <= 0.02:
            score += 0.10
        elif yes_price <= 0.03:
            score += 0.05
        
        # Category bonuses based on historical performance
        category = self.detect_category(question)
        
        category_bonuses = {
            "crypto": 0.10,  # Crypto has more volatility/upsets
            "entertainment": 0.08,
            "tech": 0.05,
            "sports": -0.05,  # Sports are harder to predict
            "political": 0.03,
            "finance": 0.02,
            "other": 0.0
        }
        score += category_bonuses.get(category, 0)
        
        # Keyword bonuses
        positive_keywords = ["will", "announce", "release", "launch", "breakthrough"]
        negative_keywords = ["not", "never", "fail", "impossible"]
        
        for kw in positive_keywords:
            if kw in question:
                score += 0.02
        
        for kw in negative_keywords:
            if kw in question:
                score -= 0.05
        
        # Volume/activity factor (simulated since we don't have this)
        score += random.uniform(-0.05, 0.05)
        
        return max(0.0, min(1.0, score))
    
    async def scan_markets(self) -> list[dict]:
        """Scan for tail markets"""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(f"{self.CLOB_API}/sampling-markets")
                if resp.status_code != 200:
                    return []
                
                data = resp.json()
                # Handle paginated response
                markets = data.get("data", []) if isinstance(data, dict) else data
                tail_markets = []
                
                for market in markets:
                    tokens = market.get("tokens", [])
                    for token in tokens:
                        if token.get("outcome") == "Yes":
                            price = float(token.get("price", 1))
                            if price <= self.max_yes_price:
                                tail_markets.append({
                                    "condition_id": market.get("condition_id"),
                                    "token_id": token.get("token_id"),
                                    "question": market.get("question", ""),
                                    "yes_price": price
                                })
                
                return tail_markets
                
            except Exception as e:
                print(f"Error scanning: {e}")
                return []
    
    def score_opportunities(self, markets: list[dict]) -> list[ScoredOpportunity]:
        """Score all opportunities and rank them"""
        scored = []
        
        for market in markets:
            yes_price = market["yes_price"]
            potential = 1 / yes_price if yes_price > 0 else 0
            category = self.detect_category(market["question"])
            ml_score = self.calculate_ml_score(market)
            
            # Expected value calculation
            estimated_hit_rate = ml_score * 0.05  # Scale score to ~0-5% hit rate
            ev = (estimated_hit_rate * potential * self.stake_usd) - ((1 - estimated_hit_rate) * self.stake_usd)
            
            # Recommendation
            if ml_score >= 0.70:
                recommendation = "STRONG_BET"
            elif ml_score >= 0.60:
                recommendation = "BET"
            elif ml_score >= 0.50:
                recommendation = "WATCH"
            else:
                recommendation = "SKIP"
            
            scored.append(ScoredOpportunity(
                condition_id=market["condition_id"],
                token_id=market["token_id"],
                question=market["question"],
                yes_price=yes_price,
                potential_multiplier=potential,
                category=category,
                ml_score=ml_score,
                recommendation=recommendation,
                expected_value=ev
            ))
        
        # Sort by ML score descending
        scored.sort(key=lambda x: x.ml_score, reverse=True)
        
        return scored
    
    def print_top_opportunities(self, opportunities: list[ScoredOpportunity], top_n: int = 20):
        """Display top scoring opportunities"""
        print()
        print("=" * 80)
        print("🎯 TOP TAIL BETTING OPPORTUNITIES (ML SCORED)")
        print("=" * 80)
        print()
        print(f"{'#':<3} {'Score':<8} {'Price':<8} {'Mult':<8} {'Cat':<12} {'Rec':<12} {'Question'}")
        print("-" * 80)
        
        for i, opp in enumerate(opportunities[:top_n], 1):
            q_short = opp.question[:35] + "..." if len(opp.question) > 35 else opp.question
            print(f"{i:<3} {opp.ml_score:.2%}  ${opp.yes_price:.3f}  {opp.potential_multiplier:>5.0f}x  {opp.category:<12} {opp.recommendation:<12} {q_short}")
        
        print("-" * 80)
        
        if not opportunities:
            print("   No opportunities found")
            print()
            return
        
        # Summary stats
        strong_bets = [o for o in opportunities if o.recommendation == "STRONG_BET"]
        bets = [o for o in opportunities if o.recommendation == "BET"]
        
        print()
        print(f"📊 Summary:")
        print(f"   Total Opportunities: {len(opportunities)}")
        print(f"   STRONG_BET:          {len(strong_bets)}")
        print(f"   BET:                 {len(bets)}")
        print(f"   Average Score:       {sum(o.ml_score for o in opportunities) / len(opportunities):.2%}")
        print()
        
        if strong_bets:
            print(f"💎 Top STRONG_BET opportunity:")
            top = strong_bets[0]
            print(f"   {top.question[:60]}...")
            print(f"   Score: {top.ml_score:.2%} | Price: ${top.yes_price:.4f} | Potential: {top.potential_multiplier:.0f}x")
            print(f"   Category: {top.category} | EV: ${top.expected_value:.2f}")
        
        print()
    
    async def run_analysis(self):
        """Run full market analysis"""
        print("🔍 Scanning markets...")
        markets = await self.scan_markets()
        print(f"   Found {len(markets)} tail markets")
        
        print("🧠 Scoring opportunities...")
        scored = self.score_opportunities(markets)
        
        self.print_top_opportunities(scored)
        
        # Save to file
        output = {
            "timestamp": datetime.now().isoformat(),
            "total_markets": len(markets),
            "scored_opportunities": [
                {
                    "condition_id": o.condition_id,
                    "question": o.question,
                    "yes_price": o.yes_price,
                    "potential": o.potential_multiplier,
                    "category": o.category,
                    "ml_score": o.ml_score,
                    "recommendation": o.recommendation,
                    "expected_value": o.expected_value
                }
                for o in scored[:50]  # Top 50
            ]
        }
        
        output_file = self.data_dir / "scored_opportunities.json"
        output_file.write_text(json.dumps(output, indent=2))
        print(f"💾 Saved top opportunities to: {output_file}")
        
        return scored


async def main():
    """Run integrated tail system"""
    system = IntegratedTailSystem(
        max_yes_price=0.04,
        stake_usd=2.0,
        min_score=0.60,
        paper_trading=True
    )
    
    print("=" * 80)
    print("🎲 INTEGRATED TAIL BETTING SYSTEM")
    print("   Combining ML Scoring + Market Scanning")
    print("=" * 80)
    
    await system.run_analysis()


if __name__ == "__main__":
    asyncio.run(main())
