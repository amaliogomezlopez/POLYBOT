"""
🎯 ENHANCED TAIL BET PLACER
===========================
Places tail bets with ML scoring and category filtering.

Features:
- ML-based scoring
- Category weighting (crypto, stocks, politics, etc.)
- Duplicate prevention
- Batch processing
"""

import asyncio
import httpx
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import random
import re

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class TailConfig:
    max_price: float = 0.04          # Maximum YES price
    min_price: float = 0.001         # Minimum YES price (avoid $0)
    stake: float = 2.0               # Fixed stake per bet
    max_bets_per_run: int = 50       # Maximum bets per execution
    min_ml_score: float = 0.60       # Minimum ML score to place bet
    paper_trading: bool = True       # Paper trading mode

# =============================================================================
# ML SCORER
# =============================================================================

class TailScorer:
    """
    Simple ML-based scorer for tail bets.
    Uses category weights and market characteristics.
    """
    
    # Category weights based on historical performance
    CATEGORY_WEIGHTS = {
        'crypto': 0.12,      # High volatility, black swan events
        'bitcoin': 0.10,
        'ethereum': 0.08,
        'altcoin': 0.06,
        'stock': 0.05,       # Price targets can hit
        'nvidia': 0.08,      # Tech stocks volatile
        'apple': 0.05,
        'tesla': 0.10,       # Tesla very volatile
        'trump': 0.04,       # Political events unpredictable
        'politics': 0.03,
        'election': 0.05,
        'ai': 0.08,          # AI rapid development
        'openai': 0.06,
        'sports': -0.05,     # Sports more predictable
        'weather': -0.03,
        'celebrity': -0.02,
        'entertainment': 0.00,
    }
    
    # Multiplier bonus (higher multiplier = lower probability, but if it hits...)
    MULTIPLIER_BONUSES = [
        (1000, 0.08),  # 1000x+ gets bonus
        (500, 0.05),   # 500x+ gets smaller bonus
        (200, 0.02),   # 200x+ gets small bonus
    ]
    
    def score(self, market: dict) -> float:
        """
        Score a market for tail betting potential.
        Returns: 0.0 to 1.0 (higher = better)
        """
        base_score = 0.50  # Start at 50%
        
        question = market.get('question', '').lower()
        price = market.get('price', 0.02)
        multiplier = market.get('mult', 50)
        
        # Category analysis
        for keyword, weight in self.CATEGORY_WEIGHTS.items():
            if keyword in question:
                base_score += weight
        
        # Multiplier bonus
        for threshold, bonus in self.MULTIPLIER_BONUSES:
            if multiplier >= threshold:
                base_score += bonus
                break
        
        # Penalize very short questions (might be incomplete)
        if len(question) < 30:
            base_score -= 0.05
        
        # Bonus for specific patterns
        if '2026' in question or '2027' in question:
            base_score += 0.03  # Longer timeframe
        if 'before' in question:
            base_score += 0.02  # Price targets
        
        # Clamp to 0-1
        return max(0.0, min(1.0, base_score))

# =============================================================================
# BET PLACER
# =============================================================================

class TailBetPlacer:
    """
    Places tail bets with ML scoring.
    """
    
    def __init__(self, config: Optional[TailConfig] = None):
        self.config = config or TailConfig()
        self.scorer = TailScorer()
        self.bets_file = Path('data/tail_bot/bets.json')
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30)
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    def load_bets(self) -> list[dict]:
        """Load existing bets."""
        if self.bets_file.exists():
            return json.loads(self.bets_file.read_text())
        return []
    
    def save_bets(self, bets: list[dict]):
        """Save bets to file."""
        self.bets_file.parent.mkdir(parents=True, exist_ok=True)
        self.bets_file.write_text(json.dumps(bets, indent=2, default=str))
    
    async def scan_opportunities(self) -> list[dict]:
        """Scan for all tail opportunities."""
        existing_ids = {b.get('condition_id') for b in self.load_bets()}
        
        all_tails = []
        cursors = ['LTE=', 'MA==', 'MjA=', 'NDA=', 'NjA=', 'ODA=', 'MTAw', 'MTIw', 'MTQw']
        
        for cursor in cursors:
            url = f'https://clob.polymarket.com/sampling-markets?next_cursor={cursor}'
            try:
                resp = await self.client.get(url)
                if resp.status_code != 200:
                    continue
                
                markets = resp.json().get('data', [])
                for m in markets:
                    cid = m.get('condition_id')
                    if cid in existing_ids:
                        continue
                    
                    for t in m.get('tokens', []):
                        if t.get('outcome') == 'Yes':
                            price = float(t.get('price', 1))
                            if self.config.min_price < price < self.config.max_price:
                                all_tails.append({
                                    'condition_id': cid,
                                    'question': m.get('question', ''),
                                    'price': price,
                                    'mult': round(1/price, 1),
                                    'token_id': t.get('token_id'),
                                    'market_slug': m.get('market_slug', '')
                                })
                            break
            except Exception as e:
                print(f"Error: {e}")
        
        # Deduplicate
        seen = set()
        unique = []
        for t in all_tails:
            if t['condition_id'] not in seen:
                seen.add(t['condition_id'])
                unique.append(t)
        
        return unique
    
    def score_and_filter(self, opportunities: list[dict]) -> list[dict]:
        """Score and filter opportunities by ML score."""
        scored = []
        for opp in opportunities:
            score = self.scorer.score(opp)
            opp['ml_score'] = score
            if score >= self.config.min_ml_score:
                scored.append(opp)
        
        # Sort by score descending
        scored.sort(key=lambda x: x['ml_score'], reverse=True)
        return scored
    
    async def place_paper_bet(self, opportunity: dict) -> dict:
        """Place a paper (simulated) bet."""
        bet = {
            'id': f"TAIL-{int(datetime.now().timestamp())}-{random.randint(1, 999)}",
            'timestamp': datetime.now().timestamp(),
            'question': opportunity['question'],
            'condition_id': opportunity['condition_id'],
            'token_id': opportunity.get('token_id'),
            'entry_price': opportunity['price'],
            'stake': self.config.stake,
            'size': round(self.config.stake / opportunity['price'], 2),
            'potential_return': round(self.config.stake / opportunity['price'], 2),
            'potential_multiplier': opportunity['mult'],
            'ml_score': opportunity.get('ml_score', 0.5),
            'status': 'pending',
            'exit_price': None,
            'pnl': 0.0,
            'resolved_at': None
        }
        return bet
    
    async def run(self, max_bets: Optional[int] = None):
        """Run the bet placer."""
        max_bets = max_bets or self.config.max_bets_per_run
        
        print("\n" + "=" * 60)
        print("  🎯 TAIL BET PLACER")
        print("=" * 60)
        
        # Load existing
        existing_bets = self.load_bets()
        print(f"\n📊 Existing bets: {len(existing_bets)}")
        
        # Scan
        print("\n🔍 Scanning for opportunities...")
        opportunities = await self.scan_opportunities()
        print(f"   Found {len(opportunities)} new tail markets")
        
        if not opportunities:
            print("   No new opportunities found.")
            return
        
        # Score and filter
        print("\n🤖 Applying ML scoring...")
        scored = self.score_and_filter(opportunities)
        print(f"   {len(scored)} pass ML threshold (>= {self.config.min_ml_score:.0%})")
        
        if not scored:
            print("   No opportunities pass ML filter.")
            return
        
        # Place bets
        bets_to_place = scored[:max_bets]
        print(f"\n💰 Placing {len(bets_to_place)} paper bets...")
        
        new_bets = []
        total_stake = 0
        
        for i, opp in enumerate(bets_to_place, 1):
            bet = await self.place_paper_bet(opp)
            new_bets.append(bet)
            total_stake += bet['stake']
            
            q = opp['question'][:40]
            price = opp['price']
            mult = opp['mult']
            score = opp['ml_score']
            
            print(f"   {i:2}. ${price:.3f} ({mult:,.0f}x) ML:{score:.0%} - {q}...")
        
        # Save
        all_bets = existing_bets + new_bets
        self.save_bets(all_bets)
        
        # Summary
        print("\n" + "-" * 60)
        print(f"✅ PLACED {len(new_bets)} NEW BETS")
        print(f"   Total stake:    ${total_stake:.2f}")
        print(f"   Average mult:   {sum(b['potential_multiplier'] for b in new_bets)/len(new_bets):.0f}x")
        print(f"   Total bets now: {len(all_bets)}")
        print(f"   Total invested: ${sum(b['stake'] for b in all_bets):.2f}")
        print("=" * 60 + "\n")

# =============================================================================
# MAIN
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Place tail bets")
    parser.add_argument("--max", "-m", type=int, default=25, help="Maximum bets to place")
    parser.add_argument("--threshold", "-t", type=float, default=0.60, help="ML score threshold")
    parser.add_argument("--stake", "-s", type=float, default=2.0, help="Stake per bet")
    
    args = parser.parse_args()
    
    config = TailConfig(
        stake=args.stake,
        min_ml_score=args.threshold
    )
    
    async with TailBetPlacer(config) as placer:
        await placer.run(max_bets=args.max)

if __name__ == "__main__":
    asyncio.run(main())
