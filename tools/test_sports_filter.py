"""Test sports filtering approaches."""
import httpx
import asyncio

SPORTS_KEYWORDS = ['nba', 'nfl', 'nhl', 'mlb', 'soccer', 'football', 'basketball', 
                  'esport', 'ufc', 'boxing', 'tennis', 'premier league', 'champions']

async def test():
    async with httpx.AsyncClient() as c:
        # Test 1: Events endpoint
        print("=" * 70)
        print("TEST 1: Events Endpoint")
        print("=" * 70)
        
        r = await c.get('https://gamma-api.polymarket.com/events', params={'limit': 100, 'active': 'true'})
        events = r.json()
        print(f'Total events: {len(events)}')
        
        sports_events = []
        for e in events:
            title = e.get('title', '').lower()
            slug = e.get('slug', '').lower()
            if any(kw in title or kw in slug for kw in SPORTS_KEYWORDS):
                sports_events.append(e)
        
        print(f'Sports events: {len(sports_events)}')
        for e in sports_events[:10]:
            print(f"  {e.get('id')} | {e.get('title', '')[:50]}")
        
        # Test 2: Markets with tag param
        print()
        print("=" * 70)
        print("TEST 2: Markets with tag='Sports'")
        print("=" * 70)
        
        r = await c.get('https://gamma-api.polymarket.com/markets', 
                       params={'limit': 20, 'active': 'true', 'tag': 'Sports'})
        markets = r.json()
        print(f'Markets returned: {len(markets)}')
        
        # Check tags in returned markets
        for m in markets[:5]:
            tags = m.get('tags', [])
            q = m.get('question', '')[:50]
            print(f"  Tags: {tags} | {q}")
        
        # Test 3: Search in question text directly
        print()
        print("=" * 70)
        print("TEST 3: Keyword filtering in questions")
        print("=" * 70)
        
        # Get a large batch and filter locally
        r = await c.get('https://gamma-api.polymarket.com/markets', 
                       params={'limit': 500, 'active': 'true', 'closed': 'false'})
        all_markets = r.json()
        print(f'Total markets fetched: {len(all_markets)}')
        
        sports_markets = []
        for m in all_markets:
            q = m.get('question', '').lower()
            if any(kw in q for kw in SPORTS_KEYWORDS):
                sports_markets.append(m)
        
        print(f'Sports markets (by keyword): {len(sports_markets)}')
        for m in sports_markets[:15]:
            q = m.get('question', '')[:60]
            vol = float(m.get('volume', 0))
            print(f"  [${vol/1000:.0f}k] {q}...")

if __name__ == "__main__":
    asyncio.run(test())
