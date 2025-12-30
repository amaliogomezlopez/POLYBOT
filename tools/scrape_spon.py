"""
Scraper for @Spon Polymarket activity.
Tail betting strategy analysis.
"""
import requests
import json
import time
import os
from datetime import datetime
from typing import List, Dict, Any

# Gamma API
GAMMA_API = "https://gamma-api.polymarket.com"

# User to scrape
USER_ADDRESS = None  # Will find from profile


def get_user_profile(username: str) -> Dict:
    """Get user profile by username"""
    # Try to find user
    url = f"{GAMMA_API}/users"
    params = {"username": username}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                return data[0] if isinstance(data, list) else data
    except Exception as e:
        print(f"Error getting profile: {e}")
    
    return {}


def get_user_activity(address: str, limit: int = 100, offset: int = 0) -> List[Dict]:
    """Get user trading activity"""
    url = f"{GAMMA_API}/activity"
    params = {
        "user": address,
        "limit": limit,
        "offset": offset
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Error getting activity: {e}")
    
    return []


def get_user_positions(address: str) -> List[Dict]:
    """Get user current positions"""
    url = f"{GAMMA_API}/positions"
    params = {"user": address}
    
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Error getting positions: {e}")
    
    return []


def scrape_all_activity(address: str, max_pages: int = 100) -> List[Dict]:
    """Scrape all activity with pagination"""
    all_activity = []
    offset = 0
    limit = 100
    
    print(f"🔍 Scraping activity for {address}...")
    
    for page in range(max_pages):
        print(f"  Page {page + 1}... (offset {offset})")
        
        activity = get_user_activity(address, limit=limit, offset=offset)
        
        if not activity:
            print(f"  No more activity at offset {offset}")
            break
            
        all_activity.extend(activity)
        offset += limit
        
        # Rate limit
        time.sleep(0.5)
        
        # Check if we got less than limit (last page)
        if len(activity) < limit:
            break
            
    print(f"✅ Total activity records: {len(all_activity)}")
    return all_activity


def analyze_tail_strategy(activity: List[Dict]) -> Dict:
    """Analyze the tail betting strategy"""
    
    analysis = {
        "total_trades": 0,
        "buy_trades": 0,
        "sell_trades": 0,
        "total_invested": 0.0,
        "total_returns": 0.0,
        "avg_buy_price": 0.0,
        "price_distribution": {
            "under_5c": 0,
            "5c_to_10c": 0,
            "10c_to_20c": 0,
            "over_20c": 0
        },
        "outcome_distribution": {
            "yes_buys": 0,
            "no_buys": 0
        },
        "markets_traded": set(),
        "winning_trades": [],
        "losing_trades": [],
        "pending_positions": [],
        "trade_sizes": [],
        "unique_markets": 0
    }
    
    buy_prices = []
    
    for trade in activity:
        try:
            action = trade.get("action", "").lower()
            price = float(trade.get("price", 0) or 0)
            size = float(trade.get("size", 0) or 0)
            outcome = trade.get("outcome", "").lower()
            market_slug = trade.get("market", {}).get("slug", "") if isinstance(trade.get("market"), dict) else ""
            question = trade.get("market", {}).get("question", "") if isinstance(trade.get("market"), dict) else str(trade.get("market", ""))
            
            analysis["total_trades"] += 1
            
            if "buy" in action:
                analysis["buy_trades"] += 1
                analysis["total_invested"] += price * size
                buy_prices.append(price)
                analysis["trade_sizes"].append(size)
                
                # Price distribution
                if price < 0.05:
                    analysis["price_distribution"]["under_5c"] += 1
                elif price < 0.10:
                    analysis["price_distribution"]["5c_to_10c"] += 1
                elif price < 0.20:
                    analysis["price_distribution"]["10c_to_20c"] += 1
                else:
                    analysis["price_distribution"]["over_20c"] += 1
                    
                # Outcome distribution
                if "yes" in outcome:
                    analysis["outcome_distribution"]["yes_buys"] += 1
                else:
                    analysis["outcome_distribution"]["no_buys"] += 1
                    
            elif "sell" in action:
                analysis["sell_trades"] += 1
                analysis["total_returns"] += price * size
                
            # Track markets
            if market_slug:
                analysis["markets_traded"].add(market_slug)
            elif question:
                analysis["markets_traded"].add(question[:50])
                
        except Exception as e:
            print(f"Error processing trade: {e}")
            continue
            
    # Calculate averages
    if buy_prices:
        analysis["avg_buy_price"] = sum(buy_prices) / len(buy_prices)
        
    analysis["unique_markets"] = len(analysis["markets_traded"])
    analysis["markets_traded"] = list(analysis["markets_traded"])[:50]  # Keep first 50
    
    # ROI
    if analysis["total_invested"] > 0:
        analysis["roi_pct"] = ((analysis["total_returns"] - analysis["total_invested"]) / analysis["total_invested"]) * 100
    else:
        analysis["roi_pct"] = 0
        
    return analysis


def find_tail_markets() -> List[Dict]:
    """Find current tail markets (YES price < 4 cents)"""
    print("\n🔍 Finding current tail markets...")
    
    url = f"{GAMMA_API}/markets"
    params = {
        "active": "true",
        "closed": "false",
        "limit": 500
    }
    
    try:
        r = requests.get(url, params=params, timeout=30)
        markets = r.json() if r.status_code == 200 else []
    except:
        markets = []
        
    tail_markets = []
    
    for m in markets:
        try:
            outcomes = m.get("outcomes", [])
            if not outcomes:
                continue
                
            # Get YES price
            yes_price = None
            for o in outcomes:
                if isinstance(o, dict) and o.get("name", "").lower() == "yes":
                    yes_price = float(o.get("price", 1))
                    break
                elif isinstance(o, str) and "yes" in o.lower():
                    # Price might be in different format
                    yes_price = float(m.get("outcomePrices", [1])[0] if m.get("outcomePrices") else 1)
                    break
                    
            # Try clobTokenIds for price
            if yes_price is None and m.get("clobTokenIds"):
                tokens = m.get("clobTokenIds", [])
                if tokens:
                    # Would need CLOB API for actual price
                    pass
                    
            # Check for tail (< 4 cents)
            if yes_price and yes_price < 0.04 and yes_price > 0:
                liquidity = float(m.get("liquidityClob", 0) or m.get("liquidity", 0) or 0)
                
                # Skip very low liquidity
                if liquidity < 1000:
                    continue
                    
                tail_markets.append({
                    "question": m.get("question", "")[:100],
                    "slug": m.get("slug", ""),
                    "yes_price": yes_price,
                    "liquidity": liquidity,
                    "volume_24h": float(m.get("volume24hr", 0) or 0),
                    "condition_id": m.get("conditionId", ""),
                    "token_id": m.get("clobTokenIds", [""])[0] if m.get("clobTokenIds") else ""
                })
                
        except Exception as e:
            continue
            
    # Sort by price (lowest first)
    tail_markets.sort(key=lambda x: x["yes_price"])
    
    print(f"✅ Found {len(tail_markets)} tail markets (YES < 4¢)")
    return tail_markets


def main():
    """Main scraper function"""
    print("=" * 60)
    print("🎯 SPON TAIL BETTING STRATEGY ANALYSIS")
    print("=" * 60)
    
    # Known address for @Spon (from Polymarket)
    # We'll try to find it or use direct activity endpoint
    
    # Try multiple approaches
    addresses_to_try = [
        "0x0000000000000000000000000000000000000000",  # Placeholder
    ]
    
    # First, let's get tail markets regardless
    tail_markets = find_tail_markets()
    
    print(f"\n📊 Top 10 Tail Markets (YES < 4¢):")
    for i, m in enumerate(tail_markets[:10]):
        print(f"  {i+1}. {m['question'][:60]}...")
        print(f"     YES: ${m['yes_price']:.3f} | Liquidity: ${m['liquidity']:,.0f}")
        
    # Save tail markets
    os.makedirs("analysis/spon", exist_ok=True)
    
    with open("analysis/spon/tail_markets.json", "w") as f:
        json.dump(tail_markets, f, indent=2)
    print(f"\n💾 Saved {len(tail_markets)} tail markets to analysis/spon/tail_markets.json")
    
    # Try to find Spon's address from leaderboard or known addresses
    print("\n🔍 Looking for @Spon address...")
    
    # Check leaderboard
    try:
        leaderboard_url = f"{GAMMA_API}/leaderboard"
        r = requests.get(leaderboard_url, timeout=10)
        if r.status_code == 200:
            leaders = r.json()
            for leader in leaders[:100]:
                username = leader.get("username", "").lower()
                if "spon" in username:
                    print(f"  Found: {leader.get('username')} - {leader.get('address')}")
                    addresses_to_try.insert(0, leader.get("address"))
    except Exception as e:
        print(f"  Leaderboard error: {e}")
        
    # Generate analysis document
    analysis_doc = f"""# @Spon Tail Betting Strategy Analysis

## Strategy Overview

Based on community insights, @Spon uses a **Tail Betting** strategy:

### Core Strategy
- **Scan all markets** every 60 seconds
- **Hunt tail outcomes** (very unlikely events)
- **Buy YES at 1-3¢** (maximum price: 4¢)
- **Fixed $2 downside** per bet
- A few hits cover hundreds of misses

### Why It Works
1. **Markets price consensus, not probability** - tail events are often mispriced
2. **Asymmetric risk/reward** - $2 risk, potential $200 return
3. **Time is your friend** - with capped downside and uncapped upside

### ROI Math
- Risk per bet: $2
- 100 bets = -$200 worst case
- 1 hit at 1¢ = ~$200 return (100x)
- **Only need 1-2 tail hits per month to stay +ROI**

## Current Tail Markets Found

Found **{len(tail_markets)}** markets with YES price < 4¢:

| # | Question | YES Price | Liquidity |
|---|----------|-----------|-----------|
"""
    
    for i, m in enumerate(tail_markets[:20]):
        analysis_doc += f"| {i+1} | {m['question'][:50]}... | ${m['yes_price']:.3f} | ${m['liquidity']:,.0f} |\n"
        
    analysis_doc += f"""

## Strategy Implementation

### Entry Criteria
1. YES price ≤ $0.04 (4 cents)
2. Liquidity > $1,000
3. Market is active and not closed
4. Event has reasonable probability of occurring

### Position Sizing
- Fixed stake: $2 per bet
- Maximum exposure: ~100 bets = $200

### Exit Strategy
- Hold until resolution
- No stop losses (already capped at $2)
- Take profit on big wins

## Bot Implementation

```python
# Tail Bot Parameters
MAX_YES_PRICE = 0.04  # 4 cents
MAX_LIQUIDITY = 50_000
STAKE_USD = 2
SLEEP_SECONDS = 60
```

## Key Differences from HFT Strategy

| Aspect | HFT (Account88888) | Tail Betting (Spon) |
|--------|-------------------|---------------------|
| Frequency | High (seconds) | Low (minutes) |
| Hold Time | Seconds | Days/Weeks |
| Risk/Trade | Variable | Fixed $2 |
| Win Rate | High (>60%) | Low (~1-2%) |
| Profit/Win | Small | Huge (50-100x) |
| Markets | Flash/Price | Any tail event |

## Timestamp
Analysis generated: {datetime.now().isoformat()}
"""
    
    with open("analysis/spon/strategy_analysis.md", "w", encoding="utf-8") as f:
        f.write(analysis_doc)
    print(f"💾 Saved strategy analysis to analysis/spon/strategy_analysis.md")
    
    return tail_markets


if __name__ == "__main__":
    main()
