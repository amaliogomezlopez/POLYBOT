"""Find crypto and price markets"""
import asyncio
import aiohttp

async def find_crypto():
    async with aiohttp.ClientSession() as session:
        url = 'https://gamma-api.polymarket.com/markets'
        params = {'active': 'true', 'closed': 'false', 'limit': 200}
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            
            keywords = ['btc', 'bitcoin', 'eth', 'ethereum', 'sol', 'solana', 'price', '1-min', '5-min', 'minute', 'crypto']
            
            crypto = [m for m in data if any(kw in m.get('question', '').lower() for kw in keywords)]
            
            print(f'Found {len(crypto)} crypto/price markets:')
            for m in crypto[:20]:
                q = m.get('question', '')[:70]
                tokens = len(m.get('clobTokenIds', []))
                vol = m.get('volume24hr', 0) or 0
                print(f'  - {q}')
                print(f'    Tokens: {tokens} | Volume: ${vol:,.0f}')

asyncio.run(find_crypto())
