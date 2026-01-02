#!/usr/bin/env python3
"""Deep analysis focusing on ACTIONABLE arbitrage opportunities."""

import json
from pathlib import Path
from collections import defaultdict

data = json.loads(Path('analysis/market_data.json').read_text())

print("=" * 70)
print("ACTIONABLE ARB ANALYSIS")
print("Filtering for markets with VALID prices on BOTH platforms")
print("=" * 70)

# Filter for valid prices (both > 0.01 and < 0.99)
valid_matches = []
for m in data['matches']:
    poly_p = m['poly_yes_price']
    pb_p = m['pb_yes_price']
    
    # Both must have valid prices
    if 0.01 < poly_p < 0.99 and 0.01 < pb_p < 0.99:
        # Calculate real spread
        real_spread = abs(poly_p - pb_p) * 100
        m['real_spread'] = real_spread
        valid_matches.append(m)

print(f"\nTotal matches with valid prices: {len(valid_matches)}")

# Sort by real spread
valid_matches.sort(key=lambda x: -x['real_spread'])

print("\n" + "=" * 70)
print("TOP 30 POTENTIAL ARB OPPORTUNITIES")
print("(Both platforms have prices between 1%-99%)")
print("=" * 70)

for m in valid_matches[:30]:
    print(f"\n📊 Similarity: {m['similarity']:.0f}% | Spread: {m['real_spread']:.1f}%")
    print(f"   Poly: {m['poly_question'][:60]}")
    print(f"   PB:   {m['pb_question'][:60]}")
    print(f"   Poly YES: ${m['poly_yes_price']:.3f}")
    print(f"   PB YES:   ${m['pb_yes_price']:.3f}")
    
    # Determine direction
    if m['poly_yes_price'] > m['pb_yes_price']:
        print(f"   → Buy PB YES, Sell Poly YES (PB cheaper)")
    else:
        print(f"   → Buy Poly YES, Sell PB YES (Poly cheaper)")

# Category analysis for valid matches
print("\n" + "=" * 70)
print("VALID MATCHES BY CATEGORY")
print("=" * 70)

cats = defaultdict(list)
for m in valid_matches:
    q = m['poly_question'].lower()
    if 'nba' in q or 'nfl' in q or 'nhl' in q or 'mlb' in q or 'soccer' in q or 'premier' in q:
        cats['Sports'].append(m)
    elif 'bitcoin' in q or 'btc' in q or 'eth' in q or 'crypto' in q or 'ethereum' in q:
        cats['Crypto'].append(m)
    elif 'trump' in q or 'biden' in q or 'election' in q or 'president' in q or 'democrat' in q or 'republican' in q:
        cats['Politics'].append(m)
    else:
        cats['Other'].append(m)

for cat, matches in sorted(cats.items(), key=lambda x: -len(x[1])):
    avg_spread = sum(m['real_spread'] for m in matches) / len(matches) if matches else 0
    high_sim = len([m for m in matches if m['similarity'] >= 80])
    print(f"\n{cat}: {len(matches)} valid matches")
    print(f"  Avg spread: {avg_spread:.1f}%")
    print(f"  High similarity (>80%): {high_sim}")
    
    # Show best from each category
    if matches:
        best = max(matches, key=lambda x: x['real_spread'])
        print(f"  Best opportunity: {best['poly_question'][:50]}")
        print(f"    Spread: {best['real_spread']:.1f}% | Sim: {best['similarity']:.0f}%")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
high_spread = [m for m in valid_matches if m['real_spread'] >= 5]
high_sim_high_spread = [m for m in valid_matches if m['real_spread'] >= 3 and m['similarity'] >= 80]

print(f"Matches with spread >= 5%: {len(high_spread)}")
print(f"Matches with spread >= 3% AND similarity >= 80%: {len(high_sim_high_spread)}")

if high_sim_high_spread:
    print("\n🎯 GOLD CANDIDATES (high sim + good spread):")
    for m in high_sim_high_spread[:10]:
        print(f"  • {m['poly_question'][:50]} | {m['real_spread']:.1f}% spread")
