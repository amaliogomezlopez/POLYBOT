"""Get sports tag IDs from Polymarket."""
import asyncio
import httpx

async def get_sports_tags():
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get('https://gamma-api.polymarket.com/tags')
        tags = resp.json()
        
        sports_keywords = ['sport', 'nba', 'nfl', 'nhl', 'mlb', 'soccer', 'football', 
                         'basketball', 'baseball', 'hockey', 'esport', 'league', 
                         'olympic', 'ufc', 'boxing', 'tennis', 'golf', 'cricket',
                         'rugby', 'f1', 'formula', 'playoff', 'championship']
        
        print('SPORTS-RELATED TAGS FOUND:')
        print('=' * 70)
        
        sports_tags = []
        for tag in tags:
            label = tag.get('label', '').lower()
            slug = tag.get('slug', '').lower()
            
            for kw in sports_keywords:
                if kw in label or kw in slug:
                    sports_tags.append(tag)
                    tid = tag['id']
                    tlabel = tag['label']
                    tslug = tag['slug']
                    print(f"ID: {tid:5s} | {tlabel:35s} | {tslug}")
                    break
        
        print()
        print(f'Total sports tags found: {len(sports_tags)}')
        print()
        print('PYTHON DICT FORMAT:')
        print('SPORTS_TAG_IDS = {')
        for t in sports_tags:
            print(f"    '{t['slug']}': '{t['id']}',  # {t['label']}")
        print('}')

if __name__ == "__main__":
    asyncio.run(get_sports_tags())
