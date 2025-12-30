"""Scan for new tail betting opportunities."""

import asyncio
import httpx
import json
from pathlib import Path

async def scan_all_tails():
    bets_file = Path('data/tail_bot/bets.json')
    existing_ids = set()
    
    if bets_file.exists():
        existing = json.loads(bets_file.read_text())
        existing_ids = {b.get('condition_id') for b in existing}
    
    async with httpx.AsyncClient(timeout=30) as client:
        all_tails = []
        cursors = ['LTE=', 'MA==', 'MjA=', 'NDA=', 'NjA=', 'ODA=', 'MTAw', 'MTIw', 'MTQw']
        
        for cursor in cursors:
            url = f'https://clob.polymarket.com/sampling-markets?next_cursor={cursor}'
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                
                markets = resp.json().get('data', [])
                for m in markets:
                    cid = m.get('condition_id')
                    if cid in existing_ids:
                        continue
                    
                    for t in m.get('tokens', []):
                        if t.get('outcome') == 'Yes':
                            price = float(t.get('price', 1))
                            if price < 0.05 and price > 0.001:
                                all_tails.append({
                                    'condition_id': cid,
                                    'question': m.get('question', '')[:60],
                                    'price': price,
                                    'mult': round(1/price, 1),
                                    'token_id': t.get('token_id'),
                                    'market_slug': m.get('market_slug', '')
                                })
                            break
            except Exception as e:
                print(f"Error with cursor {cursor}: {e}")
        
        # Deduplicate
        seen = set()
        unique_tails = []
        for t in all_tails:
            if t['condition_id'] not in seen:
                seen.add(t['condition_id'])
                unique_tails.append(t)
        
        unique_tails.sort(key=lambda x: x['mult'], reverse=True)
        
        print(f"\n🔍 NEW TAIL OPPORTUNITIES (YES < $0.05)")
        print(f"Found {len(unique_tails)} new markets")
        print(f"Already bet on: {len(existing_ids)} markets")
        print("-" * 60)
        
        for i, t in enumerate(unique_tails[:20], 1):
            price = t['price']
            mult = t['mult']
            q = t['question']
            print(f"{i:2}. ${price:.3f} ({mult:,.0f}x) - {q}...")
        
        if len(unique_tails) > 20:
            print(f"\n... and {len(unique_tails) - 20} more")
        
        return unique_tails

if __name__ == "__main__":
    asyncio.run(scan_all_tails())
