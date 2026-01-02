#!/usr/bin/env python3
"""Test fuzzy matching between different market formats."""

import sys
sys.path.insert(0, r'c:\Users\amalio\Desktop\PROGRAMACION\01-VS_CODE\32-POLYMARKET-BOT')

from src.scanner.arb_scanner import clean_question, calculate_match_score

# Test markets
poly_markets = [
    {'question': 'Will the Ravens win Super Bowl 2026?'},
    {'question': 'Will the Eagles beat the Panthers?'},
    {'question': 'Will the Lakers beat the Celtics?'},
    {'question': 'Will Arsenal win the Premier League?'},
    {'question': 'Will the Broncos win the NFC Championship?'},
]

pb_markets = [
    'NFL: Ravens vs. Chiefs',
    'NFL: Eagles vs. Panthers', 
    'NBA: Lakers vs. Celtics',
    'Premier League: Arsenal vs. Man City',
    'NHL: Kings vs. Wild',
]

print('='*60)
print('FUZZY MATCHING TEST')
print('='*60)

for poly in poly_markets:
    pq = clean_question(poly['question'])
    print(f"\nPoly: {poly['question']}")
    print(f"  Cleaned: {pq}")
    
    best_score = 0
    best_match = None
    
    for pb in pb_markets:
        pbq = clean_question(pb)
        score = calculate_match_score(pq, pbq)
        if score > best_score:
            best_score = score
            best_match = pb
        if score > 30:
            print(f"  vs '{pb}' => score={score}")
    
    print(f"  BEST: {best_match} (score={best_score})")
