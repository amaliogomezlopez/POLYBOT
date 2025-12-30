#!/usr/bin/env python3
"""
Buscar mercados con SPREADS APROVECHABLES para arbitraje delta-neutral
Los mejores mercados para arbitraje son aquellos donde:
- Yes + No < $1.00 (podemos comprar ambos y ganar)
- O hay spreads significativos en el orderbook
"""

import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CLOB_URL = "https://clob.polymarket.com"

def find_arbitrage_opportunities():
    """Buscar oportunidades de arbitraje delta-neutral"""
    
    print("\n" + "="*70)
    print("🎯 BUSCANDO OPORTUNIDADES DE ARBITRAJE DELTA-NEUTRAL")
    print("="*70)
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    opportunities = []
    balanced_markets = []  # Mercados con probabilidades cerca de 50/50
    cursor = None
    scanned = 0
    
    for batch in range(200):
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
                
                if not (m.get("enable_order_book") and m.get("active") and m.get("accepting_orders")):
                    continue
                
                tokens = m.get("tokens", [])
                if len(tokens) != 2:
                    continue
                
                # Verificar precios de tokens
                yes_token = None
                no_token = None
                
                for t in tokens:
                    outcome = t.get("outcome", "").lower()
                    price = float(t.get("price", 0.5))
                    
                    if outcome == "yes":
                        yes_token = {"token": t, "price": price}
                    elif outcome == "no":
                        no_token = {"token": t, "price": price}
                
                if not yes_token or not no_token:
                    continue
                
                total_price = yes_token["price"] + no_token["price"]
                
                # Buscar:
                # 1. Mercados donde Yes + No < $0.98 (oportunidad de compra)
                # 2. Mercados equilibrados (30-70% probabilidad)
                
                if total_price < 0.98:
                    opportunities.append({
                        "question": m.get("question"),
                        "yes_price": yes_token["price"],
                        "no_price": no_token["price"],
                        "total": total_price,
                        "profit_potential": 1.0 - total_price,
                        "market": m,
                    })
                
                if 0.30 <= yes_token["price"] <= 0.70:
                    balanced_markets.append({
                        "question": m.get("question"),
                        "yes_price": yes_token["price"],
                        "no_price": no_token["price"],
                        "market": m,
                    })
            
            cursor = data.get("next_cursor")
            if not cursor:
                break
                
            if batch % 20 == 0:
                print(f"   Escaneados: {scanned} | Oportunidades: {len(opportunities)} | Balanceados: {len(balanced_markets)}")
                
        except Exception as e:
            print(f"Error: {e}")
            break
    
    print(f"\n📊 RESULTADOS:")
    print(f"   Total escaneados: {scanned}")
    print(f"   Oportunidades arbitraje (Yes+No < $0.98): {len(opportunities)}")
    print(f"   Mercados balanceados (30-70%): {len(balanced_markets)}")
    
    # Analizar oportunidades de arbitraje
    if opportunities:
        print(f"\n" + "="*70)
        print("💰 OPORTUNIDADES DE ARBITRAJE (Yes + No < $0.98)")
        print("="*70)
        
        # Ordenar por profit potencial
        opportunities.sort(key=lambda x: x["profit_potential"], reverse=True)
        
        for opp in opportunities[:20]:
            print(f"\n   📌 {opp['question'][:60]}")
            print(f"      Yes: ${opp['yes_price']:.3f} | No: ${opp['no_price']:.3f}")
            print(f"      Total: ${opp['total']:.3f} | 💰 Profit Potencial: ${opp['profit_potential']:.3f} ({opp['profit_potential']*100:.1f}%)")
            
            # Verificar orderbook real
            market = opp["market"]
            tokens = market.get("tokens", [])
            
            for t in tokens:
                token_id = t.get("token_id")
                if token_id:
                    try:
                        book = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id}).json()
                        bids = book.get("bids", [])
                        asks = book.get("asks", [])
                        
                        if asks:
                            best_ask = min(asks, key=lambda x: float(x.get("price", 0)))
                            print(f"      📖 {t.get('outcome')} - Mejor Ask: ${float(best_ask.get('price', 0)):.3f} x {best_ask.get('size', 0)}")
                    except:
                        pass
    
    # Analizar mercados balanceados
    if balanced_markets:
        print(f"\n" + "="*70)
        print("⚖️ MERCADOS BALANCEADOS (30-70%) - Mejores para trading")
        print("="*70)
        
        for m in balanced_markets[:20]:
            print(f"\n   📌 {m['question'][:60]}")
            print(f"      Yes: ${m['yes_price']:.3f} | No: ${m['no_price']:.3f}")
            
            # Verificar liquidez
            market = m["market"]
            tokens = market.get("tokens", [])
            
            total_ask_yes = 0
            total_ask_no = 0
            best_ask_yes = 0
            best_ask_no = 0
            
            for t in tokens:
                token_id = t.get("token_id")
                outcome = t.get("outcome", "").lower()
                
                if token_id:
                    try:
                        book = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id}).json()
                        bids = book.get("bids", [])
                        asks = book.get("asks", [])
                        
                        if asks:
                            best_ask = min(asks, key=lambda x: float(x.get("price", 0)))
                            total_liq = sum(float(a.get("size", 0)) for a in asks)
                            
                            if outcome == "yes":
                                best_ask_yes = float(best_ask.get("price", 0))
                                total_ask_yes = total_liq
                            else:
                                best_ask_no = float(best_ask.get("price", 0))
                                total_ask_no = total_liq
                            
                            print(f"      📖 {outcome.upper()} - Ask: ${float(best_ask.get('price', 0)):.3f} | Bids: {len(bids)} | Asks: {len(asks)}")
                    except:
                        pass
            
            # Calcular costo total de arbitraje
            if best_ask_yes > 0 and best_ask_no > 0:
                total_cost = best_ask_yes + best_ask_no
                print(f"      💰 Costo total (Best Ask Yes + No): ${total_cost:.3f}")
                
                if total_cost < 1.0:
                    profit = 1.0 - total_cost
                    print(f"      🎯 ¡OPORTUNIDAD! Profit: ${profit:.3f} ({profit*100:.1f}%)")

def check_specific_market():
    """Verificar un mercado específico con detalle"""
    
    print("\n" + "="*70)
    print("🔍 VERIFICANDO MERCADO ESPECÍFICO CON DETALLE")
    print("="*70)
    
    # Buscar el mercado "Will xAI have the top AI model on December 31?"
    # que tenía buenos spreads
    
    url = f"{CLOB_URL}/markets"
    cursor = None
    target_market = None
    
    for batch in range(200):
        resp = requests.get(url, params={"limit": 100, "next_cursor": cursor} if cursor else {"limit": 100})
        data = resp.json()
        markets = data.get("data", [])
        
        for m in markets:
            if "xAI" in m.get("question", ""):
                target_market = m
                break
        
        if target_market:
            break
            
        cursor = data.get("next_cursor")
        if not cursor:
            break
    
    if target_market:
        print(f"\n   📌 {target_market.get('question')}")
        print(f"   Condition ID: {target_market.get('condition_id')}")
        
        tokens = target_market.get("tokens", [])
        
        for t in tokens:
            token_id = t.get("token_id")
            outcome = t.get("outcome")
            price = t.get("price")
            
            print(f"\n   Token: {outcome}")
            print(f"   Price (mid): ${float(price):.3f}")
            print(f"   Token ID: {token_id}")
            
            # Obtener orderbook completo
            book = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id}).json()
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            
            print(f"\n   📖 ORDERBOOK {outcome}:")
            print(f"   BIDS ({len(bids)}):")
            for b in sorted(bids, key=lambda x: -float(x.get("price", 0)))[:5]:
                print(f"      ${float(b.get('price', 0)):.3f} x {b.get('size', 0)}")
            
            print(f"   ASKS ({len(asks)}):")
            for a in sorted(asks, key=lambda x: float(x.get("price", 0)))[:5]:
                print(f"      ${float(a.get('price', 0)):.3f} x {a.get('size', 0)}")

def main():
    find_arbitrage_opportunities()
    # check_specific_market()

if __name__ == "__main__":
    main()
