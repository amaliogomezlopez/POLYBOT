#!/usr/bin/env python3
"""Debug script to test market parsing."""
import httpx
import json

# Fetch markets from Gamma
r = httpx.get("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false", timeout=30)
markets = r.json()

MIN_VOLUME = 500
MIN_LIQ = 100
MIN_PRICE = 0.01
MAX_PRICE = 0.99

print(f"Fetched {len(markets)} markets\n")

for m in markets[:3]:
    cid = m.get("conditionId") or m.get("condition_id")
    vol = float(m.get("volume") or m.get("volumeNum") or 0)
    liq = float(m.get("liquidity") or m.get("liquidityNum") or 0)
    active = m.get("active")
    closed = m.get("closed")
    outcomes = m.get("outcomes")
    prices = m.get("outcomePrices")
    
    print(f"CID: {cid[:40]}...")
    print(f"  Question: {m.get('question', '')[:60]}...")
    print(f"  Volume: ${vol:,.0f} (min: ${MIN_VOLUME})")
    print(f"  Liquidity: ${liq:,.0f} (min: ${MIN_LIQ})")
    print(f"  Active: {active} | Closed: {closed}")
    
    # Quick filter checks
    checks = []
    if active is not False:
        checks.append("✅ active")
    else:
        checks.append("❌ not active")
    
    if closed is not True:
        checks.append("✅ not closed")
    else:
        checks.append("❌ closed")
        
    if vol >= MIN_VOLUME:
        checks.append(f"✅ vol >= {MIN_VOLUME}")
    else:
        checks.append(f"❌ vol < {MIN_VOLUME}")
    
    if liq >= MIN_LIQ:
        checks.append(f"✅ liq >= {MIN_LIQ}")
    else:
        checks.append(f"❌ liq < {MIN_LIQ}")
        
    if outcomes:
        checks.append("✅ has outcomes")
    else:
        checks.append("❌ no outcomes")
        
    if prices:
        checks.append("✅ has prices")
    else:
        checks.append("❌ no prices")
    
    print(f"  Quick Filter: {' | '.join(checks)}")
    
    # Parse prices
    if prices:
        try:
            plist = json.loads(prices) if isinstance(prices, str) else prices
            olist = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
            
            yes_price = 0.0
            no_price = 0.0
            for i, o in enumerate(olist):
                if o.upper() == "YES":
                    yes_price = float(plist[i])
                elif o.upper() == "NO":
                    no_price = float(plist[i])
            
            print(f"  Prices: YES={yes_price:.4f}, NO={no_price:.4f}")
            
            # Price validation
            if MIN_PRICE <= yes_price <= MAX_PRICE:
                print(f"  ✅ YES price {yes_price:.4f} is valid (0.01-0.99)")
            else:
                print(f"  ❌ YES price {yes_price:.4f} outside range (0.01-0.99)")
                
        except Exception as e:
            print(f"  ❌ Parse error: {e}")
    
    print()
