"""List all Polymarket tags."""
import httpx

r = httpx.get('https://gamma-api.polymarket.com/tags')
tags = r.json()

print(f'Total: {len(tags)} tags')
print()
print('ALL TAGS (sorted):')
print('=' * 60)

for t in sorted(tags, key=lambda x: x['label'].lower()):
    print(f"{t['id']:6s} | {t['label']}")
