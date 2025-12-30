#!/usr/bin/env python3
"""Debug: Ver qué mercados hay disponibles"""

import httpx
import json

def debug_markets():
    print("DEPURACIÓN DE MERCADOS POLYMARKET")
    print("=" * 80)
    
    response = httpx.get(
        'https://gamma-api.polymarket.com/markets',
        params={'limit': 50, 'active': True},
        timeout=15
    )
    
    markets = response.json()
    print(f"\nTotal mercados activos: {len(markets)}")
    
    print("\n" + "-" * 80)
    print("PRIMEROS 20 MERCADOS:")
    print("-" * 80)
    
    for i, m in enumerate(markets[:20], 1):
        q = m.get('question', 'N/A')[:60]
        outcomes = m.get('outcomePrices', '')
        enable_book = m.get('enableOrderBook', False)
        
        try:
            prices = json.loads(outcomes) if outcomes else []
        except:
            prices = []
        
        print(f"\n{i}. {q}...")
        print(f"   OrderBook: {enable_book}")
        print(f"   Precios: {prices[:2] if prices else 'N/A'}")
    
    # Buscar mercados de crypto
    print("\n" + "=" * 80)
    print("BUSCANDO MERCADOS DE CRYPTO/FLASH:")
    print("-" * 80)
    
    crypto_keywords = ['btc', 'bitcoin', 'eth', 'ethereum', 'sol', 'solana', 
                      'crypto', 'price', 'up or down', 'higher', 'lower']
    
    crypto_markets = []
    for m in markets:
        q = m.get('question', '').lower()
        if any(kw in q for kw in crypto_keywords):
            crypto_markets.append(m)
    
    print(f"\nMercados de crypto encontrados: {len(crypto_markets)}")
    
    for m in crypto_markets[:15]:
        q = m.get('question', '')[:70]
        outcomes = m.get('outcomePrices', '')
        try:
            prices = json.loads(outcomes) if outcomes else []
            if len(prices) >= 2:
                spread = float(prices[0]) + float(prices[1])
                print(f"\n• {q}...")
                print(f"  Precios: {prices[0]} + {prices[1]} = {spread:.4f}")
        except:
            print(f"\n• {q}...")
            print(f"  Precios: {outcomes[:50]}")

    # Buscar en eventos específicos de crypto
    print("\n" + "=" * 80)
    print("BUSCANDO EVENTOS DE CRYPTO:")
    print("-" * 80)
    
    events_response = httpx.get(
        'https://gamma-api.polymarket.com/events',
        params={'limit': 30, 'active': True},
        timeout=15
    )
    
    events = events_response.json()
    
    for e in events:
        title = e.get('title', '').lower()
        if any(kw in title for kw in ['btc', 'bitcoin', 'eth', 'crypto', 'price']):
            print(f"\n• {e.get('title', 'N/A')}")
            print(f"  Slug: {e.get('slug', 'N/A')}")

if __name__ == "__main__":
    debug_markets()
