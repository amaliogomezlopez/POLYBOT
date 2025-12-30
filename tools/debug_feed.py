"""Debug script for Polymarket feed"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.polymarket_feed import PolymarketFeed

async def debug():
    async with PolymarketFeed() as feed:
        markets = await feed.get_active_markets(limit=3)
        print(f"Markets found: {len(markets)}")
        
        for m in markets:
            print(f"\nMarket: {m['question'][:50]}")
            print(f"Tokens: {m['tokens']}")
            
            if m['tokens']:
                token_id = m['tokens'][0]
                print(f"Testing token: {token_id}")
                
                # Get orderbook
                book = await feed.get_orderbook(token_id)
                if book:
                    print(f"  Orderbook OK - Mid: {book.mid_price:.4f}")
                else:
                    print("  Orderbook FAILED")
                    
                # Get tick
                tick = await feed.get_market_tick(token_id, m['question'])
                if tick:
                    print(f"  Tick OK - Mid: {tick.mid_price:.4f}")
                else:
                    print("  Tick FAILED")

if __name__ == "__main__":
    asyncio.run(debug())
