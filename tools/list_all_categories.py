"""List all Polymarket categories."""
import httpx

r = httpx.get('https://gamma-api.polymarket.com/categories')
cats = r.json()

print(f'Total: {len(cats)} categories')
print()
print('ALL CATEGORIES:')
print('=' * 80)

for c in sorted(cats, key=lambda x: x['label']):
    parent = c.get('parentCategory', 'N/A')
    print(f"{c['id']:6s} | {c['label']:35s} | parent: {parent}")
