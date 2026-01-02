"""Debug script to understand market matching between platforms."""
import asyncio
import logging
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)

async def debug_matching():
    import httpx
    from src.exchanges.predictbase_client import PredictBaseClient
    
    # Get Poly markets - SORTED BY VOLUME to get active ones
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            'https://gamma-api.polymarket.com/markets', 
            params={
                'limit': 50, 
                'active': 'true',
                'closed': 'false',
                '_sort': 'volume:desc',  # Sort by volume
            }
        )
        poly = resp.json()
    
    print("\n" + "=" * 70)
    print("POLYMARKET SAMPLES (sorted by volume)")
    print("=" * 70)
    for m in poly[:15]:
        q = m.get('question', '')[:80]
        vol = float(m.get('volume', 0))
        print(f"  [${vol/1000:.0f}k] {q}")
    
    # Get PB markets
    async with PredictBaseClient() as pb:
        pb_markets = await pb.get_markets(limit=100, include_resolved=True)
    
    print("\n" + "=" * 70)
    print("PREDICTBASE SAMPLES")
    print("=" * 70)
    for m in pb_markets[:15]:
        print(f"  [{m.yes_price:.2f}] {m.question[:80]}")
    
    # Try lower threshold matching
    print("\n" + "=" * 70)
    print("ATTEMPTING MATCHING (threshold=40)")
    print("=" * 70)
    
    from src.scanner.arb_scanner import batch_match_markets
    
    # Convert poly to expected format
    poly_dicts = []
    for m in poly:
        poly_dicts.append({
            'question': m.get('question', ''),
            'condition_id': m.get('conditionId', ''),
            'token_id': '',
            'yes_price': 0.5,
            'no_price': 0.5,
            'volume': m.get('volume', 0),
        })
    
    matches = batch_match_markets(
        poly_markets=poly_dicts,
        pb_markets=pb_markets,
        threshold=40,  # Very low threshold to see what matches
        max_matches=30
    )
    
    print(f"\nFound {len(matches)} matches:")
    for m in matches[:10]:
        print(f"\n  Score: {m.match_score:.0f}")
        print(f"  Poly: {m.poly_question[:70]}...")
        print(f"  PB:   {m.pb_question[:70]}...")

if __name__ == "__main__":
    asyncio.run(debug_matching())
