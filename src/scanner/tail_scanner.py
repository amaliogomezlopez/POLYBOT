"""
Advanced Tail Market Scanner
Finds and monitors tail betting opportunities (YES < 4 cents).
Uses CLOB API for accurate pricing.
"""
import asyncio
import aiohttp
import json
import time
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class TailMarket:
    """A tail market opportunity"""
    question: str
    slug: str
    condition_id: str
    token_id: str
    yes_price: float
    no_price: float
    liquidity: float
    volume_24h: float
    spread: float
    end_date: str
    score: float = 0.0  # Calculated score for ranking


GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


async def get_all_markets(session: aiohttp.ClientSession) -> List[Dict]:
    """Get all active markets from Gamma API"""
    url = f"{GAMMA_API}/markets"
    params = {
        "active": "true",
        "closed": "false",
        "limit": 500
    }
    
    async with session.get(url, params=params) as resp:
        if resp.status == 200:
            return await resp.json()
    return []


async def get_clob_markets(session: aiohttp.ClientSession) -> List[Dict]:
    """Get markets from CLOB API with real prices"""
    url = f"{CLOB_API}/sampling-markets"
    
    async with session.get(url) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("data", [])
    return []


async def get_orderbook_price(session: aiohttp.ClientSession, token_id: str) -> Optional[Dict]:
    """Get real orderbook price for a token"""
    url = f"{CLOB_API}/book"
    params = {"token_id": token_id}
    
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                data = await resp.json()
                bids = data.get("bids", [])
                asks = data.get("asks", [])
                
                if bids and asks:
                    best_bid = float(bids[0].get("price", 0))
                    best_ask = float(asks[0].get("price", 1))
                    return {
                        "bid": best_bid,
                        "ask": best_ask,
                        "mid": (best_bid + best_ask) / 2,
                        "spread": best_ask - best_bid
                    }
    except:
        pass
    return None


async def find_tail_markets(max_price: float = 0.04) -> List[TailMarket]:
    """Find all tail markets with YES price below threshold"""
    print(f"🔍 Scanning for tail markets (YES < ${max_price})...")
    
    tail_markets = []
    
    async with aiohttp.ClientSession() as session:
        # Get all CLOB markets
        clob_markets = await get_clob_markets(session)
        print(f"  Found {len(clob_markets)} CLOB markets")
        
        # Filter for active markets with orderbook
        active_markets = [
            m for m in clob_markets 
            if m.get("enable_order_book") and m.get("active") and not m.get("closed")
        ]
        print(f"  {len(active_markets)} active with orderbook")
        
        # Check prices for each market
        checked = 0
        for market in active_markets:
            tokens = market.get("tokens", [])
            if not tokens:
                continue
                
            # Find YES token
            yes_token = None
            no_token = None
            for t in tokens:
                outcome = t.get("outcome", "").lower()
                if "yes" in outcome:
                    yes_token = t
                elif "no" in outcome:
                    no_token = t
                    
            if not yes_token:
                continue
                
            # Get real price from orderbook
            token_id = yes_token.get("token_id")
            price_data = await get_orderbook_price(session, token_id)
            
            if not price_data:
                continue
                
            yes_price = price_data["mid"]
            
            # Check if tail market
            if yes_price < max_price and yes_price > 0.001:
                # Get liquidity from market data
                liquidity = 0
                for t in tokens:
                    liquidity += float(t.get("liquidity", 0) or 0)
                    
                # Skip very low liquidity
                if liquidity < 500:
                    continue
                    
                # Calculate score (lower price + higher liquidity = better)
                score = (1 / yes_price) * min(liquidity / 10000, 10)
                
                tail_markets.append(TailMarket(
                    question=market.get("question", "")[:150],
                    slug=market.get("market_slug", ""),
                    condition_id=market.get("condition_id", ""),
                    token_id=token_id,
                    yes_price=yes_price,
                    no_price=1 - yes_price,
                    liquidity=liquidity,
                    volume_24h=float(market.get("volume", 0) or 0),
                    spread=price_data["spread"],
                    end_date=market.get("end_date_iso", ""),
                    score=score
                ))
                
            checked += 1
            if checked % 50 == 0:
                print(f"  Checked {checked}/{len(active_markets)} markets...")
                
            # Rate limit
            await asyncio.sleep(0.1)
            
    # Sort by score (best opportunities first)
    tail_markets.sort(key=lambda x: x.score, reverse=True)
    
    print(f"✅ Found {len(tail_markets)} tail markets")
    return tail_markets


def is_tail_market(market: Dict) -> bool:
    """Check if market qualifies as tail bet"""
    try:
        # Check if active
        if not market.get("active"):
            return False
            
        # Get outcomes and prices
        outcomes = market.get("outcomes", [])
        if len(outcomes) < 1:
            return False
            
        # Find YES outcome
        yes = outcomes[0]
        price = float(yes.get("price", 1) if isinstance(yes, dict) else 1)
        liquidity = float(market.get("liquidity", 0) or 0)
        
        # Tail criteria
        if price > 0.04:  # Max 4 cents
            return False
        if liquidity > 50000:  # Max liquidity (avoid manipulated markets)
            return False
            
        return True
        
    except Exception:
        return False


def build_order(market: TailMarket, stake_usd: float = 2.0) -> Dict:
    """Build order for tail market"""
    size = round(stake_usd / market.yes_price, 2)
    
    return {
        "condition_id": market.condition_id,
        "token_id": market.token_id,
        "side": "BUY",
        "price": market.yes_price,
        "size": size,
        "question": market.question,
        "potential_return": size * 1.0,  # If YES wins
        "risk": stake_usd
    }


async def run_tail_scanner(
    max_price: float = 0.04,
    min_liquidity: float = 500,
    stake_usd: float = 2.0
) -> List[Dict]:
    """Run the tail market scanner and generate orders"""
    print("\n" + "=" * 60)
    print("🎯 TAIL MARKET SCANNER")
    print(f"   Max YES Price: ${max_price}")
    print(f"   Min Liquidity: ${min_liquidity}")
    print(f"   Stake per Bet: ${stake_usd}")
    print("=" * 60)
    
    # Find tail markets
    tail_markets = await find_tail_markets(max_price)
    
    # Filter by liquidity
    qualified = [m for m in tail_markets if m.liquidity >= min_liquidity]
    
    print(f"\n📊 Qualified Tail Markets: {len(qualified)}")
    print("-" * 60)
    
    orders = []
    
    for i, market in enumerate(qualified[:20]):
        potential_return = stake_usd / market.yes_price
        
        print(f"\n{i+1}. {market.question[:60]}...")
        print(f"   YES Price: ${market.yes_price:.3f} (Spread: {market.spread:.3f})")
        print(f"   Liquidity: ${market.liquidity:,.0f}")
        print(f"   Potential Return: ${potential_return:,.0f} ({potential_return/stake_usd:.0f}x)")
        
        order = build_order(market, stake_usd)
        orders.append(order)
        
    print("\n" + "=" * 60)
    print(f"💰 Total Potential Orders: {len(orders)}")
    print(f"   Total Risk: ${len(orders) * stake_usd}")
    print("=" * 60)
    
    return orders


async def monitor_tail_markets(interval_seconds: int = 60):
    """Continuously monitor for new tail markets"""
    print("\n🔄 Starting tail market monitor...")
    print(f"   Scanning every {interval_seconds} seconds")
    print("   Press Ctrl+C to stop\n")
    
    seen_conditions = set()
    
    while True:
        try:
            markets = await find_tail_markets(max_price=0.04)
            now = datetime.now().isoformat()
            
            for m in markets:
                if m.condition_id in seen_conditions:
                    continue
                    
                # New tail market found!
                seen_conditions.add(m.condition_id)
                
                potential = 2.0 / m.yes_price  # $2 stake
                
                print(f"\n[{now}] 🎯 TAIL BET FOUND")
                print(f"   Question: {m.question[:60]}...")
                print(f"   YES Price: ${m.yes_price:.3f}")
                print(f"   Potential: ${potential:,.0f} ({potential/2:.0f}x)")
                print(f"   Condition: {m.condition_id[:20]}...")
                print("-" * 40)
                
            await asyncio.sleep(interval_seconds)
            
        except KeyboardInterrupt:
            print("\n⏹️ Monitor stopped")
            break
        except Exception as e:
            print(f"\n[ERROR] {e}")
            await asyncio.sleep(10)


def save_results(markets: List[TailMarket], orders: List[Dict]):
    """Save scanner results"""
    os.makedirs("analysis/spon", exist_ok=True)
    
    # Save markets
    markets_data = [
        {
            "question": m.question,
            "slug": m.slug,
            "condition_id": m.condition_id,
            "token_id": m.token_id,
            "yes_price": m.yes_price,
            "liquidity": m.liquidity,
            "score": m.score,
            "potential_return": 2.0 / m.yes_price if m.yes_price > 0 else 0
        }
        for m in markets
    ]
    
    with open("analysis/spon/tail_markets.json", "w", encoding="utf-8") as f:
        json.dump(markets_data, f, indent=2)
        
    # Save orders
    with open("analysis/spon/pending_orders.json", "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2)
        
    print(f"\n💾 Saved {len(markets)} markets and {len(orders)} orders")


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Tail Market Scanner")
    parser.add_argument("--max-price", type=float, default=0.04, help="Max YES price")
    parser.add_argument("--stake", type=float, default=2.0, help="Stake per bet in USD")
    parser.add_argument("--monitor", action="store_true", help="Run continuous monitor")
    
    args = parser.parse_args()
    
    if args.monitor:
        await monitor_tail_markets()
    else:
        markets = await find_tail_markets(args.max_price)
        orders = await run_tail_scanner(args.max_price, stake_usd=args.stake)
        save_results(markets, orders)


if __name__ == "__main__":
    asyncio.run(main())
