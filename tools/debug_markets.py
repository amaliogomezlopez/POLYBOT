#!/usr/bin/env python3
"""Debug: Compare actual markets between Poly and PB."""

import asyncio
import httpx
import sys
sys.path.insert(0, r'c:\Users\amalio\Desktop\PROGRAMACION\01-VS_CODE\32-POLYMARKET-BOT')

from src.scanner.arb_scanner import clean_question, calculate_match_score, _is_sports_question

async def main():
    async with httpx.AsyncClient() as client:
        # Get PredictBase markets
        r = await client.get('https://predictbase.app/api/get_recent_markets_v2')
        pb_raw = r.json()
        
        r2 = await client.get('https://predictbase.app/api/get_resolved_markets_v2')
        pb_resolved = r2.json()
        
        print("=" * 70)
        print("PREDICTBASE MARKETS (Recent)")
        print("=" * 70)
        for m in pb_raw[:20]:
            title = m.get('title') or m.get('question') or m.get('name', 'N/A')
            print(f"  {title}")
        
        print(f"\nTotal recent: {len(pb_raw)}")
        print(f"Total resolved: {len(pb_resolved)}")
        
        # Get Polymarket sports markets
        r = await client.get(
            'https://gamma-api.polymarket.com/markets',
            params={"limit": 100, "active": "true", "closed": "false"}
        )
        poly = r.json()
        
        # Filter for sports
        sports_poly = [m for m in poly if _is_sports_question(m.get('question', ''))]
        
        print("\n" + "=" * 70)
        print("POLYMARKET SPORTS MARKETS")
        print("=" * 70)
        for m in sports_poly[:20]:
            print(f"  {m.get('question', 'N/A')[:70]}")
        
        print(f"\nTotal sports: {len(sports_poly)}")
        
        # Try matching
        print("\n" + "=" * 70)
        print("MATCHING ATTEMPTS (threshold=50)")
        print("=" * 70)
        
        matches_found = 0
        for pb in pb_raw[:30]:
            pb_q = pb.get('title') or pb.get('question') or pb.get('name', '')
            pb_clean = clean_question(pb_q)
            
            for poly in sports_poly:
                poly_q = poly.get('question', '')
                poly_clean = clean_question(poly_q)
                
                score = calculate_match_score(poly_clean, pb_clean)
                
                if score >= 50:
                    matches_found += 1
                    print(f"\n  PB: {pb_q[:60]}")
                    print(f"  Poly: {poly_q[:60]}")
                    print(f"  Score: {score}")
        
        if not matches_found:
            print("  NO MATCHES FOUND!")
            
            print("\n  Sample cleaned questions:")
            for i, pb in enumerate(pb_raw[:5]):
                pb_q = pb.get('title') or pb.get('question') or pb.get('name', '')
                print(f"    PB[{i}]: {clean_question(pb_q)}")
            
            for i, poly in enumerate(sports_poly[:5]):
                poly_q = poly.get('question', '')
                print(f"    Poly[{i}]: {clean_question(poly_q)}")

asyncio.run(main())
