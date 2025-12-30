"""Debug the CLOB API directly - Find active CLOB markets"""
import asyncio
import aiohttp

async def test_clob():
    async with aiohttp.ClientSession() as session:
        # Get markets directly from CLOB
        print("=== Testing CLOB API Markets ===\n")
        
        # 1. Get sampling markets (most active)
        url = "https://clob.polymarket.com/sampling-markets"
        async with session.get(url) as resp:
            print(f"Sampling markets status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"Sample markets keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                print(f"Data preview: {str(data)[:500]}")
        
        print("\n" + "=" * 50 + "\n")
        
        # 2. Get markets with orderbook
        url = "https://clob.polymarket.com/markets"
        async with session.get(url) as resp:
            print(f"CLOB markets status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, list):
                    print(f"Found {len(data)} markets")
                    for m in data[:5]:
                        print(f"\nMarket: {m}")
                elif isinstance(data, dict):
                    print(f"Dict keys: {data.keys()}")
                    # Try to find markets in the dict
                    if 'data' in data:
                        markets = data['data']
                        print(f"Found {len(markets)} markets in 'data'")
                        for m in markets[:3]:
                            print(f"\n  {m}")
                    elif 'next_cursor' in data:
                        print("Paginated response")
                        print(f"Content: {str(data)[:1000]}")
        
        print("\n" + "=" * 50 + "\n")
        
        # 3. Get simplified markets
        url = "https://clob.polymarket.com/simplified-markets"
        async with session.get(url) as resp:
            print(f"Simplified markets status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print(f"Type: {type(data)}")
                if isinstance(data, list):
                    print(f"Found {len(data)} simplified markets")
                    for m in data[:3]:
                        print(f"\nSimplified market: {m}")
                        
                        # Try to get orderbook for this
                        if isinstance(m, dict) and 'tokens' in m:
                            for t in m['tokens'][:1]:
                                token_id = t.get('token_id')
                                if token_id:
                                    book_url = f"https://clob.polymarket.com/book"
                                    async with session.get(book_url, params={"token_id": token_id}) as book_resp:
                                        print(f"    Book for {token_id[:20]}: {book_resp.status}")
                                        if book_resp.status == 200:
                                            bd = await book_resp.json()
                                            print(f"    Bids: {len(bd.get('bids', []))}, Asks: {len(bd.get('asks', []))}")

asyncio.run(test_clob())
