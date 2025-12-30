"""Find tight spread markets for HFT"""
import asyncio
import aiohttp

async def find_tight_markets():
    async with aiohttp.ClientSession() as session:
        print("=== Finding Tight Spread Markets for HFT ===\n")
        
        # Get sampling markets
        url = "https://clob.polymarket.com/sampling-markets"
        async with session.get(url) as resp:
            if resp.status != 200:
                print(f"Error: {resp.status}")
                return
                
            data = await resp.json()
            markets = data.get('data', [])
            
            # Filter for active markets with orderbook
            active_markets = [
                m for m in markets 
                if m.get('enable_order_book') and m.get('active') and not m.get('closed')
            ]
            
            print(f"Scanning {len(active_markets)} markets for tight spreads...\n")
            
            tight_markets = []
            
            for m in active_markets[:100]:  # Check first 100
                tokens = m.get('tokens', [])
                if not tokens:
                    continue
                    
                token = tokens[0]
                token_id = token.get('token_id')
                
                # Get orderbook
                book_url = "https://clob.polymarket.com/book"
                async with session.get(book_url, params={"token_id": token_id}) as book_resp:
                    if book_resp.status != 200:
                        continue
                        
                    book = await book_resp.json()
                    bids = book.get('bids', [])
                    asks = book.get('asks', [])
                    
                    if not bids or not asks:
                        continue
                        
                    best_bid = float(bids[0].get('price', 0))
                    best_ask = float(asks[0].get('price', 1))
                    spread = best_ask - best_bid
                    
                    # Look for spreads under 5%
                    if spread < 0.05:
                        tight_markets.append({
                            'question': m['question'][:60],
                            'token_id': token_id,
                            'bid': best_bid,
                            'ask': best_ask,
                            'spread': spread,
                            'mid': (best_bid + best_ask) / 2,
                            'bid_depth': len(bids),
                            'ask_depth': len(asks)
                        })
                        
                # Rate limit
                await asyncio.sleep(0.3)
                
            # Sort by spread
            tight_markets.sort(key=lambda x: x['spread'])
            
            print(f"\n🎯 Found {len(tight_markets)} markets with spread < 5%:\n")
            
            for m in tight_markets[:10]:
                print(f"Spread: {m['spread']:.4f} ({m['spread']*100:.2f}%)")
                print(f"  Q: {m['question']}...")
                print(f"  Bid: {m['bid']:.4f} | Ask: {m['ask']:.4f} | Mid: {m['mid']:.4f}")
                print(f"  Depth: {m['bid_depth']} bids, {m['ask_depth']} asks")
                print(f"  Token: {m['token_id'][:40]}...")
                print()
                
            return tight_markets

if __name__ == "__main__":
    asyncio.run(find_tight_markets())
