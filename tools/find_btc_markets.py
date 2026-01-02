"""Find Bitcoin markets on Polymarket."""
import asyncio
import httpx
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def find_btc_markets():
    async with httpx.AsyncClient() as client:
        # Search BTC on Polymarket
        resp = await client.get(
            'https://gamma-api.polymarket.com/markets',
            params={'limit': 200, 'active': 'true', 'closed': 'false'}
        )
        markets = resp.json()
        
        btc_markets = [
            m for m in markets 
            if 'bitcoin' in m.get('question', '').lower() 
            or 'btc' in m.get('question', '').lower()
        ]
        
        print(f"Found {len(btc_markets)} BTC markets on Polymarket:")
        for m in btc_markets[:15]:
            q = m.get("question", "")[:100]
            print(f"  - {q}")

if __name__ == "__main__":
    asyncio.run(find_btc_markets())
