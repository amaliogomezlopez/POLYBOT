#!/usr/bin/env python3
"""Check PredictBase resolved markets for potential overlap."""

import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        r = await client.get('https://predictbase.app/api/get_resolved_markets_v2')
        markets = r.json()
        
        print("=" * 70)
        print("PB RESOLVED MARKETS (last 50)")
        print("=" * 70)
        
        for m in markets[:50]:
            title = m.get('title') or m.get('question') or m.get('name', 'N/A')
            print(f"  {title[:70]}")
        
        print(f"\nTotal: {len(markets)}")
        
        # Check for championship-style markets
        print("\n" + "=" * 70)
        print("SEARCHING FOR CHAMPIONSHIP/SEASON MARKETS IN PB")
        print("=" * 70)
        
        keywords = ['championship', 'super bowl', 'playoff', 'season', 'mvp', 'finals', 'win the']
        
        for m in markets:
            title = (m.get('title') or m.get('question') or '').lower()
            if any(kw in title for kw in keywords):
                print(f"  {title[:70]}")

asyncio.run(main())
