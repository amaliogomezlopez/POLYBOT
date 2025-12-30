"""Debug the CLOB API directly"""
import asyncio
import aiohttp

async def test_clob():
    async with aiohttp.ClientSession() as session:
        # First, let's see what the markets endpoint returns
        url = "https://gamma-api.polymarket.com/markets"
        params = {"active": "true", "closed": "false", "limit": 3}
        
        async with session.get(url, params=params) as resp:
            print(f"Markets status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                for m in data[:2]:
                    print(f"\nQuestion: {m.get('question', '')[:50]}")
                    print(f"Tokens: {m.get('clobTokenIds', [])}")
                    tokens = m.get('clobTokenIds', [])
                    
                    if tokens:
                        token_id = tokens[0]
                        print(f"Testing token: {token_id[:40]}...")
                        
                        # Try the book endpoint
                        book_url = f"https://clob.polymarket.com/book"
                        book_params = {"token_id": token_id}
                        
                        async with session.get(book_url, params=book_params) as book_resp:
                            print(f"  Book status: {book_resp.status}")
                            if book_resp.status == 200:
                                book_data = await book_resp.json()
                                print(f"  Book keys: {book_data.keys()}")
                                print(f"  Bids: {len(book_data.get('bids', []))}")
                                print(f"  Asks: {len(book_data.get('asks', []))}")
                            else:
                                print(f"  Book error: {await book_resp.text()}")
                                
                        # Try midpoint
                        mid_url = f"https://clob.polymarket.com/midpoint"
                        mid_params = {"token_id": token_id}
                        
                        async with session.get(mid_url, params=mid_params) as mid_resp:
                            print(f"  Mid status: {mid_resp.status}")
                            if mid_resp.status == 200:
                                mid_data = await mid_resp.json()
                                print(f"  Mid: {mid_data}")

asyncio.run(test_clob())
