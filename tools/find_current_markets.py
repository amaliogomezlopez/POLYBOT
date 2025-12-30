#!/usr/bin/env python3
"""Buscar mercados ACTUALES de Polymarket (2025)"""

import httpx
import json
from datetime import datetime

def find_current_markets():
    print("BUSCANDO MERCADOS ACTUALES DE POLYMARKET")
    print("=" * 80)
    print(f"Fecha actual: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Buscar con diferentes parámetros
    endpoints = [
        ("markets?closed=false&active=true", "Mercados activos"),
        ("markets?closed=false", "Mercados no cerrados"),
        ("events?active=true", "Eventos activos"),
    ]
    
    for endpoint, name in endpoints:
        print(f"\n{'='*80}")
        print(f"ENDPOINT: {name}")
        print("-" * 80)
        
        try:
            response = httpx.get(
                f'https://gamma-api.polymarket.com/{endpoint}',
                params={'limit': 30},
                timeout=15
            )
            
            data = response.json()
            print(f"Resultados: {len(data)}")
            
            # Mostrar algunos
            for item in data[:5]:
                if 'question' in item:
                    print(f"  • {item.get('question', 'N/A')[:60]}...")
                    print(f"    endDate: {item.get('endDate', 'N/A')}")
                elif 'title' in item:
                    print(f"  • {item.get('title', 'N/A')[:60]}...")
                    
        except Exception as e:
            print(f"Error: {e}")
    
    # Buscar específicamente mercados de BTC/ETH Up/Down (flash markets)
    print("\n" + "=" * 80)
    print("BUSCANDO MERCADOS FLASH (BTC/ETH Up/Down)")
    print("-" * 80)
    
    # Los mercados flash suelen tener slug específico
    flash_slugs = [
        "btc-updown",
        "eth-updown", 
        "bitcoin-up-or-down",
        "ethereum-up-or-down"
    ]
    
    for slug in flash_slugs:
        try:
            response = httpx.get(
                f'https://gamma-api.polymarket.com/events',
                params={'slug': slug, 'limit': 10},
                timeout=10
            )
            
            events = response.json()
            if events:
                print(f"\n✅ Encontrado: {slug}")
                for e in events[:3]:
                    print(f"   • {e.get('title', 'N/A')}")
        except Exception as e:
            print(f"❌ {slug}: {e}")
    
    # Buscar en CLOB API directamente
    print("\n" + "=" * 80)
    print("BUSCANDO EN CLOB API (Trading)")
    print("-" * 80)
    
    try:
        # CLOB sampling endpoint
        response = httpx.get(
            'https://clob.polymarket.com/sampling-markets',
            timeout=10
        )
        
        if response.status_code == 200:
            markets = response.json()
            print(f"Mercados en CLOB: {len(markets)}")
            
            for m in markets[:10]:
                print(f"\n  Token: {m.get('condition_id', 'N/A')[:20]}...")
                print(f"  Question: {m.get('question', 'N/A')[:50]}")
        else:
            print(f"Status: {response.status_code}")
            
    except Exception as e:
        print(f"Error CLOB: {e}")
    
    # Buscar mercados con orderbook activo
    print("\n" + "=" * 80)
    print("MERCADOS CON ORDERBOOK ACTIVO")
    print("-" * 80)
    
    try:
        response = httpx.get(
            'https://gamma-api.polymarket.com/markets',
            params={'limit': 200, 'enableOrderBook': True},
            timeout=15
        )
        
        markets = response.json()
        active_orderbook = [m for m in markets if m.get('enableOrderBook')]
        
        print(f"Mercados con orderbook: {len(active_orderbook)}")
        
        # Ver cuáles tienen precios recientes
        for m in active_orderbook[:15]:
            q = m.get('question', '')[:50]
            end_date = m.get('endDate', 'N/A')
            outcomes = m.get('outcomePrices', '')
            
            try:
                prices = json.loads(outcomes) if outcomes else []
                if len(prices) >= 2 and float(prices[0]) > 0:
                    spread = float(prices[0]) + float(prices[1])
                    print(f"\n  {q}...")
                    print(f"    Spread: ${spread:.4f}")
                    print(f"    End: {end_date}")
            except:
                pass
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_current_markets()
