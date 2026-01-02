"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    POLYMARKET TAGS EXPLORER                                  ║
║                                                                              ║
║  Descubre todas las categorías/tags disponibles en Polymarket.               ║
║  Útil para filtrar mercados de deportes para ARB scanning.                   ║
║                                                                              ║
║  APIs utilizadas:                                                            ║
║    - Gamma API: https://gamma-api.polymarket.com                             ║
║    - /markets - Lista mercados con tags                                      ║
║    - /events - Lista eventos (agrupación de mercados)                        ║
║                                                                              ║
║  Objetivo: Encontrar tag_ids para Sports, Soccer, Basketball, Esports        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import httpx
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


GAMMA_API = "https://gamma-api.polymarket.com"

# Keywords we're looking for
SPORTS_KEYWORDS = [
    "sports", "sport", "soccer", "football", "basketball", "baseball",
    "hockey", "nhl", "nba", "nfl", "mlb", "mls", "premier league",
    "esports", "lol", "league of legends", "dota", "cs2", "csgo",
    "tennis", "golf", "f1", "formula", "ufc", "mma", "boxing",
    "olympics", "cricket", "rugby", "fifa", "uefa", "champions league"
]


async def explore_tags():
    """
    Explore Polymarket API to find available tags and their IDs.
    """
    print("=" * 70)
    print("          POLYMARKET TAGS EXPLORER")
    print("=" * 70)
    print()
    
    async with httpx.AsyncClient(timeout=30) as client:
        # ─────────────────────────────────────────────────────────────────────
        # 1. Check if there's a dedicated tags/categories endpoint
        # ─────────────────────────────────────────────────────────────────────
        print("🔍 Step 1: Looking for dedicated tags endpoint...")
        
        tag_endpoints = [
            "/tags",
            "/categories", 
            "/markets/tags",
            "/markets/categories",
        ]
        
        for endpoint in tag_endpoints:
            try:
                resp = await client.get(f"{GAMMA_API}{endpoint}")
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"   ✅ Found: {endpoint}")
                    print(f"   Data: {json.dumps(data, indent=2)[:500]}")
                else:
                    print(f"   ❌ {endpoint}: {resp.status_code}")
            except Exception as e:
                print(f"   ❌ {endpoint}: {e}")
        
        print()
        
        # ─────────────────────────────────────────────────────────────────────
        # 2. Extract tags from markets sample
        # ─────────────────────────────────────────────────────────────────────
        print("🔍 Step 2: Extracting tags from market data...")
        
        all_tags = Counter()
        tag_examples = defaultdict(list)
        sports_markets = []
        
        # Fetch multiple pages to get diverse tags
        for offset in [0, 100, 200, 500, 1000]:
            try:
                resp = await client.get(
                    f"{GAMMA_API}/markets",
                    params={
                        "limit": 100,
                        "offset": offset,
                        "active": "true",
                    }
                )
                
                if resp.status_code != 200:
                    continue
                
                markets = resp.json()
                
                for market in markets:
                    # Extract tags (could be in different fields)
                    tags = market.get("tags", [])
                    if isinstance(tags, str):
                        tags = [tags]
                    
                    # Also check category field
                    category = market.get("category")
                    if category:
                        tags.append(category)
                    
                    # Check slug for category hints
                    slug = market.get("slug", "")
                    
                    for tag in tags:
                        if tag:
                            all_tags[tag] += 1
                            if len(tag_examples[tag]) < 3:
                                tag_examples[tag].append(market.get("question", "")[:60])
                    
                    # Check if sports-related
                    question = market.get("question", "").lower()
                    for keyword in SPORTS_KEYWORDS:
                        if keyword in question:
                            sports_markets.append({
                                "question": market.get("question", "")[:80],
                                "tags": tags,
                                "slug": slug[:50],
                                "condition_id": market.get("conditionId", ""),
                            })
                            break
                
            except Exception as e:
                print(f"   Error at offset {offset}: {e}")
        
        print(f"   Found {len(all_tags)} unique tags")
        print()
        
        # ─────────────────────────────────────────────────────────────────────
        # 3. Display all tags found
        # ─────────────────────────────────────────────────────────────────────
        print("📋 Step 3: All Tags Found (sorted by frequency)")
        print("-" * 70)
        
        for tag, count in all_tags.most_common(50):
            examples = tag_examples.get(tag, [])
            example_str = examples[0][:40] if examples else ""
            print(f"   [{count:3d}] {tag:30s} | {example_str}...")
        
        print()
        
        # ─────────────────────────────────────────────────────────────────────
        # 4. Sports-related markets found
        # ─────────────────────────────────────────────────────────────────────
        print("🏀 Step 4: Sports Markets Found")
        print("-" * 70)
        
        if sports_markets:
            for m in sports_markets[:20]:
                print(f"   Tags: {m['tags']}")
                print(f"   Q: {m['question']}")
                print()
        else:
            print("   No sports markets found in sample!")
        
        print()
        
        # ─────────────────────────────────────────────────────────────────────
        # 5. Check events endpoint
        # ─────────────────────────────────────────────────────────────────────
        print("🔍 Step 5: Exploring Events Endpoint...")
        
        try:
            resp = await client.get(
                f"{GAMMA_API}/events",
                params={"limit": 50, "active": "true"}
            )
            
            if resp.status_code == 200:
                events = resp.json()
                print(f"   Found {len(events)} events")
                
                event_tags = Counter()
                sports_events = []
                
                for event in events:
                    # Extract event tags/category
                    tags = event.get("tags", [])
                    category = event.get("category")
                    slug = event.get("slug", "")
                    title = event.get("title", "")
                    
                    if category:
                        event_tags[category] += 1
                    for t in tags if isinstance(tags, list) else [tags]:
                        if t:
                            event_tags[t] += 1
                    
                    # Check for sports
                    search_text = f"{title} {slug}".lower()
                    for keyword in SPORTS_KEYWORDS:
                        if keyword in search_text:
                            sports_events.append({
                                "title": title[:60],
                                "slug": slug,
                                "category": category,
                                "tags": tags,
                            })
                            break
                
                print("\n   Event Categories/Tags:")
                for tag, count in event_tags.most_common(20):
                    print(f"      [{count:3d}] {tag}")
                
                if sports_events:
                    print("\n   Sports Events Found:")
                    for e in sports_events[:10]:
                        print(f"      Category: {e['category']}, Tags: {e['tags']}")
                        print(f"      Title: {e['title']}")
                        print()
                        
        except Exception as e:
            print(f"   Error: {e}")
        
        print()
        
        # ─────────────────────────────────────────────────────────────────────
        # 6. Try tag_id parameter
        # ─────────────────────────────────────────────────────────────────────
        print("🔍 Step 6: Testing tag filtering parameters...")
        
        test_params = [
            {"tag": "sports"},
            {"tag": "Sports"},
            {"tag_id": "sports"},
            {"category": "sports"},
            {"category": "Sports"},
            {"tag_slug": "sports"},
            {"tags": "sports"},
        ]
        
        for params in test_params:
            try:
                full_params = {"limit": 5, "active": "true", **params}
                resp = await client.get(f"{GAMMA_API}/markets", params=full_params)
                
                if resp.status_code == 200:
                    data = resp.json()
                    count = len(data) if isinstance(data, list) else 0
                    if count > 0:
                        print(f"   ✅ {params} → {count} markets")
                        # Show sample
                        if isinstance(data, list) and data:
                            print(f"      Sample: {data[0].get('question', '')[:50]}...")
                    else:
                        print(f"   ⚠️ {params} → 0 markets")
                else:
                    print(f"   ❌ {params} → {resp.status_code}")
                    
            except Exception as e:
                print(f"   ❌ {params} → {e}")
        
        print()
        
        # ─────────────────────────────────────────────────────────────────────
        # 7. Search functionality
        # ─────────────────────────────────────────────────────────────────────
        print("🔍 Step 7: Testing search functionality...")
        
        search_terms = ["NBA", "Lakers", "Premier League", "NHL", "esports"]
        
        for term in search_terms:
            try:
                # Try different search params
                for param_name in ["q", "query", "search", "_q"]:
                    resp = await client.get(
                        f"{GAMMA_API}/markets",
                        params={"limit": 5, param_name: term}
                    )
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and len(data) > 0:
                            # Check if results are relevant
                            first_q = data[0].get("question", "").lower()
                            if term.lower() in first_q:
                                print(f"   ✅ {param_name}='{term}' → {len(data)} results")
                                print(f"      First: {data[0].get('question', '')[:50]}...")
                                break
                else:
                    print(f"   ⚠️ No working search param for '{term}'")
                    
            except Exception as e:
                print(f"   ❌ Search error: {e}")
        
        print()
        print("=" * 70)
        print("EXPLORATION COMPLETE")
        print("=" * 70)
        
        # ─────────────────────────────────────────────────────────────────────
        # 8. Summary and recommendations
        # ─────────────────────────────────────────────────────────────────────
        print("""
SUMMARY:
--------
Based on exploration, here are the discovered tag/category patterns:

RECOMMENDED APPROACH for ARB Scanner:
1. Use text search if API supports it (q=, query=, or _q= parameter)
2. Filter by discovered tag values (if any sports tags found)
3. Keyword-based filtering on question text as fallback

Copy the discovered sports tag_ids to arb_scanner.py
""")


async def test_specific_queries():
    """
    Test specific API queries that might work for sports filtering.
    """
    print("\n" + "=" * 70)
    print("TESTING SPECIFIC SPORTS QUERIES")
    print("=" * 70 + "\n")
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Test various query patterns
        queries = [
            # Direct text search
            {"_q": "NBA"},
            {"_q": "Lakers"},
            {"_q": "Soccer"},
            {"_q": "Premier League"},
            {"_q": "NHL"},
            # Slug-based
            {"slug_contains": "nba"},
            {"slug_contains": "sports"},
            # Order by different criteria
            {"_sort": "liquidity:desc", "limit": 100},
        ]
        
        for params in queries:
            try:
                full_params = {"limit": 10, "active": "true", **params}
                resp = await client.get(f"{GAMMA_API}/markets", params=full_params)
                
                if resp.status_code == 200:
                    data = resp.json()
                    count = len(data) if isinstance(data, list) else 0
                    
                    # Check how many are sports-related
                    sports_count = 0
                    if isinstance(data, list):
                        for m in data:
                            q = m.get("question", "").lower()
                            if any(kw in q for kw in SPORTS_KEYWORDS):
                                sports_count += 1
                    
                    print(f"Query: {params}")
                    print(f"   Results: {count}, Sports-related: {sports_count}")
                    if isinstance(data, list) and data:
                        print(f"   Sample: {data[0].get('question', '')[:60]}...")
                    print()
                    
            except Exception as e:
                print(f"Query {params}: Error - {e}\n")


if __name__ == "__main__":
    print("\n🚀 Starting Polymarket Tags Exploration...\n")
    asyncio.run(explore_tags())
    asyncio.run(test_specific_queries())
