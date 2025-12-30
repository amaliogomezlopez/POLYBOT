#!/usr/bin/env python3
"""
Encontrar TODOS los mercados con orderbook activo
"""

import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CLOB_URL = "https://clob.polymarket.com"

def find_orderbook_markets():
    """Encontrar todos los mercados con orderbook habilitado"""
    
    print("\n" + "="*70)
    print("🎯 BUSCANDO MERCADOS CON ORDERBOOK HABILITADO")
    print("="*70)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    orderbook_markets = []
    cursor = None
    scanned = 0
    
    for batch in range(200):  # 20000 mercados max
        try:
            url = f"{CLOB_URL}/markets"
            params = {"limit": 100}
            if cursor:
                params["next_cursor"] = cursor
            
            resp = requests.get(url, params=params)
            data = resp.json()
            markets = data.get("data", [])
            
            if not markets:
                break
            
            for m in markets:
                scanned += 1
                
                # Buscar mercados con orderbook habilitado
                if m.get("enable_order_book"):
                    orderbook_markets.append(m)
            
            cursor = data.get("next_cursor")
            if not cursor:
                break
                
            # Mostrar progreso
            if batch % 20 == 0:
                print(f"   Escaneados: {scanned} | Encontrados con OB: {len(orderbook_markets)}")
                
        except Exception as e:
            print(f"Error: {e}")
            break
    
    print(f"\n📊 RESULTADOS:")
    print(f"   Total escaneados: {scanned}")
    print(f"   Con enable_order_book=True: {len(orderbook_markets)}")
    
    if not orderbook_markets:
        print("\n❌ NO SE ENCONTRARON MERCADOS CON ORDERBOOK")
        return
    
    # Analizar los mercados encontrados
    print(f"\n📋 MERCADOS CON ORDERBOOK ({len(orderbook_markets)}):")
    
    with_liquidity = []
    
    for m in orderbook_markets[:50]:  # Primeros 50
        question = m.get("question", "N/A")
        active = m.get("active")
        accepting = m.get("accepting_orders")
        
        print(f"\n   📌 {question[:60]}")
        print(f"      active={active} | accepting_orders={accepting}")
        
        tokens = m.get("tokens", [])
        for t in tokens:
            print(f"      {t.get('outcome')}: ${float(t.get('price', 0)):.3f}")
        
        # Verificar liquidez real
        if tokens:
            token_id = tokens[0].get("token_id")
            if token_id:
                try:
                    book = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id}).json()
                    bids = book.get("bids", [])
                    asks = book.get("asks", [])
                    
                    print(f"      📖 Bids: {len(bids)} | Asks: {len(asks)}")
                    
                    if bids or asks:
                        with_liquidity.append({
                            "question": question,
                            "bids": len(bids),
                            "asks": len(asks),
                            "tokens": tokens,
                            "market": m,
                        })
                        
                        # Mostrar mejor bid/ask si hay
                        if bids:
                            best_bid = max(bids, key=lambda x: float(x.get("price", 0)))
                            print(f"      Mejor Bid: ${float(best_bid.get('price', 0)):.3f} x {best_bid.get('size', 0)}")
                        
                        if asks:
                            best_ask = min(asks, key=lambda x: float(x.get("price", 0)))
                            print(f"      Mejor Ask: ${float(best_ask.get('price', 0)):.3f} x {best_ask.get('size', 0)}")
                        
                        if bids and asks:
                            spread = float(best_ask.get("price", 0)) - float(best_bid.get("price", 0))
                            print(f"      💰 SPREAD: ${spread:.4f}")
                        
                except Exception as e:
                    print(f"      ❌ Error: {e}")
    
    print(f"\n" + "="*70)
    print(f"📊 RESUMEN FINAL")
    print("="*70)
    print(f"   Mercados con orderbook: {len(orderbook_markets)}")
    print(f"   Mercados CON LIQUIDEZ: {len(with_liquidity)}")
    
    if with_liquidity:
        print(f"\n🎯 MERCADOS CON LIQUIDEZ REAL:")
        for m in with_liquidity:
            print(f"\n   ✅ {m['question'][:60]}")
            print(f"      Bids: {m['bids']} | Asks: {m['asks']}")

def main():
    find_orderbook_markets()

if __name__ == "__main__":
    main()
