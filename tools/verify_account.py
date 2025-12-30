#!/usr/bin/env python3
"""
Verificar balance y buscar mercados ACTIVOS con OrderBook
"""

import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=" * 80)
    print("  VERIFICACIÓN DE CUENTA Y MERCADOS ACTIVOS")
    print("=" * 80)
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 1. Verificar balance
    print("\n💰 VERIFICANDO BALANCE...")
    
    funder = os.getenv("POLYMARKET_FUNDER_ADDRESS")
    print(f"   Wallet: {funder}")
    
    try:
        from py_clob_client.client import ClobClient
        
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        sig_type = int(os.getenv("SIGNATURE_TYPE", "1"))
        
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=sig_type,
            funder=funder,
        )
        
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        
        print("   ✅ Cliente conectado")
        
        # Verificar órdenes
        orders = client.get_orders()
        print(f"   📋 Órdenes abiertas: {len(orders)}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # 2. Buscar mercados con orderbook ACTIVO ahora
    print("\n" + "=" * 80)
    print("  MERCADOS CON ORDERBOOK ACTIVO")
    print("=" * 80)
    
    try:
        # Paginar todos los mercados
        all_markets = []
        cursor = None
        
        for page in range(10):  # Max 10 páginas
            params = {'limit': 1000}
            if cursor:
                params['next_cursor'] = cursor
            
            response = httpx.get(
                "https://clob.polymarket.com/markets",
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                break
            
            data = response.json()
            markets = data.get("data", [])
            all_markets.extend(markets)
            
            cursor = data.get('next_cursor')
            if not cursor:
                break
        
        print(f"\n📊 Total mercados escaneados: {len(all_markets)}")
        
        # Filtrar mercados activos con orderbook
        active_with_book = [
            m for m in all_markets 
            if m.get('accepting_orders') and m.get('enable_order_book')
        ]
        
        print(f"🟢 Mercados ACTIVOS con OrderBook: {len(active_with_book)}")
        
        if active_with_book:
            print("\n" + "-" * 80)
            for m in active_with_book[:30]:
                q = m.get('question', '')[:60]
                tokens = m.get('tokens', [])
                
                print(f"\n✅ {q}...")
                
                # Intentar obtener precios
                if len(tokens) >= 2:
                    for i, t in enumerate(tokens[:2]):
                        token_id = t.get('token_id', '')
                        outcome = t.get('outcome', f'Outcome {i}')
                        
                        try:
                            price_resp = httpx.get(
                                "https://clob.polymarket.com/price",
                                params={'token_id': token_id, 'side': 'BUY'},
                                timeout=5
                            )
                            if price_resp.status_code == 200:
                                price = price_resp.json().get('price', 'N/A')
                                print(f"   {outcome}: ${price}")
                        except:
                            pass
        
        # Mostrar categorías de mercados activos
        print("\n" + "=" * 80)
        print("  CATEGORÍAS DE MERCADOS ACTIVOS")
        print("=" * 80)
        
        categories = {}
        for m in active_with_book:
            q = m.get('question', '').lower()
            
            if any(x in q for x in ['nba', 'basketball']):
                cat = 'NBA'
            elif any(x in q for x in ['nfl', 'football']):
                cat = 'NFL'
            elif any(x in q for x in ['mlb', 'baseball']):
                cat = 'MLB'
            elif any(x in q for x in ['nhl', 'hockey']):
                cat = 'NHL'
            elif any(x in q for x in ['soccer', 'premier', 'champions']):
                cat = 'Soccer'
            elif any(x in q for x in ['btc', 'bitcoin', 'eth', 'crypto']):
                cat = 'Crypto'
            elif any(x in q for x in ['trump', 'biden', 'election', 'president']):
                cat = 'Politics'
            else:
                cat = 'Other'
            
            categories[cat] = categories.get(cat, 0) + 1
        
        print("\n📊 Distribución:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"   {cat}: {count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
