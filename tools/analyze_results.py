#!/usr/bin/env python3
"""Analyze the market data results."""

import json
from pathlib import Path

data = json.loads(Path('analysis/market_data.json').read_text())

print("=" * 70)
print("EXACT MATCHES ANALYSIS (similarity >= 95%)")
print("=" * 70)

exact = [m for m in data['matches'] if m['similarity'] >= 95]
print(f"Total exact matches: {len(exact)}")

# Check for ACTIVE markets with spread
print("\n" + "=" * 70)
print("MARKETS WITH MEANINGFUL SPREAD (>1%)")
print("=" * 70)

with_spread = [m for m in data['matches'] if m['spread'] > 1 and m['similarity'] >= 80]
print(f"Total with spread: {len(with_spread)}")

for m in sorted(with_spread, key=lambda x: -x['spread'])[:20]:
    print(f"\n  Poly: {m['poly_question'][:60]}")
    print(f"  PB:   {m['pb_question'][:60]}")
    print(f"  Similarity: {m['similarity']:.0f}%")
    print(f"  Poly YES: ${m['poly_yes_price']:.3f} | PB YES: ${m['pb_yes_price']:.3f}")
    print(f"  SPREAD: {m['spread']:.1f}%")

# Category breakdown
print("\n" + "=" * 70)
print("HIGH MATCHES BY CATEGORY")
print("=" * 70)

from collections import defaultdict
cats = defaultdict(int)
for m in data['matches']:
    if m['similarity'] >= 80:
        # Detect category from question
        q = m['poly_question'].lower()
        if 'nba' in q or 'nfl' in q or 'nhl' in q or 'mlb' in q:
            cats['Sports'] += 1
        elif 'bitcoin' in q or 'btc' in q or 'eth' in q or 'crypto' in q:
            cats['Crypto'] += 1
        elif 'trump' in q or 'biden' in q or 'election' in q or 'president' in q:
            cats['Politics'] += 1
        else:
            cats['Other'] += 1

for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {count}")

# Check price ranges
print("\n" + "=" * 70)
print("PRICE ANALYSIS FOR EXACT MATCHES")
print("=" * 70)

for m in exact[:15]:
    poly_p = m['poly_yes_price']
    pb_p = m['pb_yes_price']
    diff = abs(poly_p - pb_p)
    print(f"  {m['poly_question'][:45]}")
    print(f"    Poly=${poly_p:.3f} PB=${pb_p:.3f} Diff=${diff:.3f} ({diff*100:.1f}%)")
