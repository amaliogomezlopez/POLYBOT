#!/usr/bin/env python3
"""Test the updated fetch_targeted_markets function."""

import asyncio
import sys
sys.path.insert(0, r'c:\Users\amalio\Desktop\PROGRAMACION\01-VS_CODE\32-POLYMARKET-BOT')

from src.scanner.arb_scanner import fetch_targeted_markets

async def main():
    print("=" * 70)
    print("TESTING UPDATED fetch_targeted_markets()")
    print("=" * 70)
    
    # Test the targeted fetch
    markets = await fetch_targeted_markets(limit=500)
    
    print(f"\n📊 RESULTS:")
    print(f"   Total sports markets fetched: {len(markets)}")
    
    if markets:
        print(f"\n🏈 Sample markets:")
        for m in markets[:20]:
            q = m.get('question', 'N/A')[:70]
            yes = m.get('outcomePrices', '').split(',')[0] if m.get('outcomePrices') else 'N/A'
            print(f"   • {q}...")
            print(f"     YES: {yes}")
    
    # Show category breakdown
    print(f"\n📊 SPORTS BREAKDOWN:")
    categories = {}
    for m in markets:
        q = m.get('question', '').lower()
        if 'nfl' in q or 'nfc' in q or 'afc' in q or any(team in q for team in ['chiefs', 'eagles', 'bills', 'ravens', 'cowboys', 'lions', 'packers', 'dolphins', 'bengals', 'jets', 'bears', 'rams', 'chargers', 'vikings', 'seahawks', 'steelers', 'broncos', 'saints', 'cardinals', 'colts', 'falcons', 'panthers', 'commanders', 'texans', 'browns', 'jaguars', 'raiders', 'titans', 'giants', 'patriots', 'buccaneers', '49ers']):
            categories['NFL'] = categories.get('NFL', 0) + 1
        elif 'nba' in q or any(team in q for team in ['lakers', 'celtics', 'warriors', 'bucks', 'suns', 'nuggets', 'heat', 'cavaliers', 'mavericks', 'thunder', 'grizzlies', 'clippers', 'kings', 'rockets', 'nets', 'knicks', 'sixers', 'timberwolves', 'pelicans', 'hawks', 'bulls', 'hornets', 'pistons', 'pacers', 'magic', 'raptors', 'wizards', 'spurs', 'jazz', 'blazers']):
            categories['NBA'] = categories.get('NBA', 0) + 1
        elif 'mlb' in q or 'baseball' in q:
            categories['MLB'] = categories.get('MLB', 0) + 1
        elif 'nhl' in q or 'hockey' in q or 'stanley cup' in q:
            categories['NHL'] = categories.get('NHL', 0) + 1
        elif 'ufc' in q or 'mma' in q or 'boxing' in q:
            categories['MMA/Boxing'] = categories.get('MMA/Boxing', 0) + 1
        elif 'soccer' in q or 'premier league' in q or 'champions league' in q:
            categories['Soccer'] = categories.get('Soccer', 0) + 1
        elif 'golf' in q:
            categories['Golf'] = categories.get('Golf', 0) + 1
        elif 'tennis' in q:
            categories['Tennis'] = categories.get('Tennis', 0) + 1
        elif 'f1' in q or 'formula' in q or 'nascar' in q:
            categories['Racing'] = categories.get('Racing', 0) + 1
        elif 'playoff' in q or 'championship' in q or 'finals' in q:
            categories['Playoffs/Championships'] = categories.get('Playoffs/Championships', 0) + 1
        else:
            categories['Other Sports'] = categories.get('Other Sports', 0) + 1
    
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"   {cat}: {count} markets")
    
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
