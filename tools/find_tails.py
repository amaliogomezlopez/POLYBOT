"""Quick tail market finder"""
import requests
import json
import os

# Get markets from CLOB with token prices
url = 'https://clob.polymarket.com/sampling-markets'
r = requests.get(url)
data = r.json()
markets = data.get('data', [])

# Filter for active markets
active = [m for m in markets if m.get('enable_order_book') and m.get('active') and not m.get('closed')]
print(f'Active markets: {len(active)}')

# Find tail markets from token prices
tail = []
for m in active:
    tokens = m.get('tokens', [])
    for t in tokens:
        outcome = t.get('outcome', '').lower()
        price = float(t.get('price', 1) or 1)
        
        if 'yes' in outcome and price < 0.05 and price > 0.001:
            tail.append({
                'question': m.get('question', '')[:80],
                'price': price,
                'outcome': outcome,
                'condition_id': m.get('condition_id', ''),
                'token_id': t.get('token_id', ''),
                'potential_return': 2.0 / price  # $2 stake
            })
            break

# Sort by price (lowest first)
tail.sort(key=lambda x: x['price'])

print(f'\nTail markets (YES < 5c): {len(tail)}')
print('-' * 80)

for i, t in enumerate(tail[:30]):
    print(f"{i+1:2d}. ${t['price']:.3f} | {t['potential_return']:6.0f}x | {t['question']}")

# Save results
os.makedirs('analysis/spon', exist_ok=True)
with open('analysis/spon/tail_markets_found.json', 'w', encoding='utf-8') as f:
    json.dump(tail, f, indent=2)
    
print(f'\nSaved {len(tail)} tail markets to analysis/spon/tail_markets_found.json')
