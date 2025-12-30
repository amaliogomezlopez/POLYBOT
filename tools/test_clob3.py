"""Debug the CLOB API - Find markets with active orderbooks"""
import asyncio
import aiohttp

async def test_clob():
    async with aiohttp.ClientSession() as session:
        print("=== Finding Active CLOB Markets ===\n")
        
        # Get sampling markets (most active, with orderbook enabled)
        url = "https://clob.polymarket.com/sampling-markets"
        async with session.get(url) as resp:
            if resp.status != 200:
                print(f"Error: {resp.status}")
                return
                
            data = await resp.json()
            markets = data.get('data', [])
            
            # Filter for active markets with orderbook enabled
            active_markets = [
                m for m in markets 
                if m.get('enable_order_book') and m.get('active') and not m.get('closed')
            ]
            
            print(f"Found {len(active_markets)} active markets with orderbooks\n")
            
            # Test first 3
            for m in active_markets[:3]:
                print(f"Market: {m['question'][:60]}...")
                print(f"  Tokens: {len(m.get('tokens', []))}")
                
                tokens = m.get('tokens', [])
                if tokens:
                    token = tokens[0]
                    token_id = token.get('token_id')
                    outcome = token.get('outcome')
                    price = token.get('price')
                    
                    print(f"  Token: {token_id[:30]}... ({outcome}) = ${price}")
                    
                    # Test orderbook
                    book_url = "https://clob.polymarket.com/book"
                    async with session.get(book_url, params={"token_id": token_id}) as book_resp:
                        if book_resp.status == 200:
                            book = await book_resp.json()
                            bids = book.get('bids', [])
                            asks = book.get('asks', [])
                            print(f"  Orderbook: {len(bids)} bids, {len(asks)} asks")
                            
                            if bids and asks:
                                best_bid = float(bids[0].get('price', 0))
                                best_ask = float(asks[0].get('price', 1))
                                mid = (best_bid + best_ask) / 2
                                spread = best_ask - best_bid
                                print(f"  Bid: {best_bid:.4f} | Ask: {best_ask:.4f} | Mid: {mid:.4f} | Spread: {spread:.4f}")
                        else:
                            print(f"  Orderbook error: {book_resp.status}")
                print()

asyncio.run(test_clob())
