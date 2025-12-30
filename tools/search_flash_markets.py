#!/usr/bin/env python3
"""
Buscar mercados flash de crypto (BTC/ETH Up/Down) via CLOB API
"""

import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def search_flash_markets():
    print("=" * 80)
    print("  BÚSQUEDA DE MERCADOS FLASH (BTC/ETH Up/Down)")
    print("=" * 80)
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Obtener todos los mercados de CLOB
    print("\n📊 Obteniendo mercados del CLOB...")
    
    try:
        # Mercados principales
        response = httpx.get(
            "https://clob.polymarket.com/markets",
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            return
        
        data = response.json()
        markets = data.get("data", [])
        
        print(f"✅ Total mercados: {len(markets)}")
        
        # Buscar mercados de crypto/flash
        flash_keywords = ['btc', 'bitcoin', 'eth', 'ethereum', 'up or down', 
                         'higher or lower', 'price', 'crypto', '15m', '30m', '1h']
        
        flash_markets = []
        sports_markets = []
        other_markets = []
        
        for m in markets:
            question = m.get('question', '').lower()
            active = m.get('active', False)
            accepting = m.get('accepting_orders', False)
            enable_book = m.get('enable_order_book', False)
            
            # Clasificar
            is_flash = any(kw in question for kw in flash_keywords)
            is_sports = any(kw in question for kw in ['nba', 'nfl', 'mlb', 'nhl', 'ncaa', 'soccer', 'football', 'basketball'])
            
            market_info = {
                'question': m.get('question', '')[:70],
                'active': active,
                'accepting_orders': accepting,
                'enable_order_book': enable_book,
                'condition_id': m.get('condition_id', '')[:20],
                'tokens': m.get('tokens', [])
            }
            
            if is_flash:
                flash_markets.append(market_info)
            elif is_sports:
                sports_markets.append(market_info)
            else:
                other_markets.append(market_info)
        
        # Mostrar resultados
        print(f"\n📈 MERCADOS FLASH (Crypto): {len(flash_markets)}")
        print(f"🏀 MERCADOS DEPORTES: {len(sports_markets)}")
        print(f"📋 OTROS MERCADOS: {len(other_markets)}")
        
        if flash_markets:
            print("\n" + "─" * 80)
            print("MERCADOS FLASH ENCONTRADOS:")
            print("─" * 80)
            for m in flash_markets[:20]:
                status = "🟢" if m['accepting_orders'] else "🔴"
                print(f"\n{status} {m['question']}...")
                print(f"   Active: {m['active']}, OrderBook: {m['enable_order_book']}")
        
        # Mostrar algunos mercados activos con orderbook
        print("\n" + "─" * 80)
        print("MERCADOS ACTIVOS CON ORDERBOOK:")
        print("─" * 80)
        
        active_with_book = [m for m in markets 
                          if m.get('accepting_orders') and m.get('enable_order_book')]
        
        print(f"Total: {len(active_with_book)}")
        
        for m in active_with_book[:15]:
            print(f"\n🟢 {m.get('question', 'N/A')[:60]}...")
            
            # Obtener precios del orderbook
            tokens = m.get('tokens', [])
            if len(tokens) >= 2:
                token1 = tokens[0].get('token_id', '')
                try:
                    # Obtener precio
                    price_resp = httpx.get(
                        f"https://clob.polymarket.com/price",
                        params={'token_id': token1, 'side': 'BUY'},
                        timeout=5
                    )
                    if price_resp.status_code == 200:
                        price_data = price_resp.json()
                        print(f"   Precio: {price_data}")
                except:
                    pass
        
        # Buscar específicamente en next cursor
        print("\n" + "=" * 80)
        print("BUSCANDO MÁS MERCADOS (paginación)...")
        print("=" * 80)
        
        next_cursor = data.get('next_cursor')
        if next_cursor:
            print(f"Next cursor disponible: {next_cursor[:30]}...")
            
            # Obtener siguiente página
            response2 = httpx.get(
                "https://clob.polymarket.com/markets",
                params={'next_cursor': next_cursor},
                timeout=30
            )
            
            if response2.status_code == 200:
                data2 = response2.json()
                markets2 = data2.get("data", [])
                print(f"Mercados adicionales: {len(markets2)}")
                
                # Buscar flash
                for m in markets2:
                    question = m.get('question', '').lower()
                    if any(kw in question for kw in flash_keywords):
                        print(f"\n🎯 FLASH: {m.get('question', '')[:60]}...")
                        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    search_flash_markets()
