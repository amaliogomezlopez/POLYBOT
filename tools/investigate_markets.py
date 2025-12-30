#!/usr/bin/env python3
"""
Investigar por qué no hay mercados con orderbook activo
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

CLOB_URL = "https://clob.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"

def investigate_market_states():
    """Analizar estados de mercados"""
    
    print("\n" + "="*70)
    print("🔬 INVESTIGACIÓN DE ESTADOS DE MERCADOS")
    print("="*70)
    
    # Estadísticas
    stats = {
        "total": 0,
        "active": 0,
        "enable_order_book_true": 0,
        "accepting_orders_true": 0,
        "all_three_true": 0,
        "has_tokens": 0,
    }
    
    cursor = None
    sample_markets = []
    
    for batch in range(100):  # 10000 mercados
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
                stats["total"] += 1
                
                if m.get("active"):
                    stats["active"] += 1
                
                if m.get("enable_order_book"):
                    stats["enable_order_book_true"] += 1
                
                if m.get("accepting_orders"):
                    stats["accepting_orders_true"] += 1
                
                if m.get("active") and m.get("enable_order_book") and m.get("accepting_orders"):
                    stats["all_three_true"] += 1
                
                if m.get("tokens"):
                    stats["has_tokens"] += 1
                
                # Guardar algunos ejemplos de mercados "activos" 
                if m.get("active") and m.get("accepting_orders") and len(sample_markets) < 5:
                    sample_markets.append(m)
            
            cursor = data.get("next_cursor")
            if not cursor:
                break
                
        except Exception as e:
            print(f"Error: {e}")
            break
    
    print(f"\n📊 ESTADÍSTICAS DE {stats['total']} MERCADOS:")
    print(f"   - Active=True: {stats['active']}")
    print(f"   - enable_order_book=True: {stats['enable_order_book_true']}")
    print(f"   - accepting_orders=True: {stats['accepting_orders_true']}")
    print(f"   - TODOS TRUE: {stats['all_three_true']}")
    print(f"   - Con tokens: {stats['has_tokens']}")
    
    print(f"\n📋 EJEMPLOS DE MERCADOS ACTIVOS (accepting_orders=True):")
    for m in sample_markets:
        print(f"\n   Question: {m.get('question', 'N/A')[:60]}")
        print(f"   active={m.get('active')} | enable_order_book={m.get('enable_order_book')} | accepting_orders={m.get('accepting_orders')}")
        print(f"   end_date_iso: {m.get('end_date_iso', 'N/A')}")
        
        tokens = m.get("tokens", [])
        for t in tokens:
            print(f"      Token {t.get('outcome')}: price={t.get('price', 'N/A')}")
        
        # Verificar orderbook de este mercado
        if tokens:
            token_id = tokens[0].get("token_id")
            if token_id:
                try:
                    book_resp = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id})
                    book = book_resp.json()
                    bids = book.get("bids", [])
                    asks = book.get("asks", [])
                    print(f"      📖 OrderBook: {len(bids)} bids, {len(asks)} asks")
                    
                    if bids:
                        print(f"         Ejemplo bid: {bids[0]}")
                    if asks:
                        print(f"         Ejemplo ask: {asks[0]}")
                        
                except Exception as e:
                    print(f"      ❌ Error orderbook: {e}")

def check_specific_flash_market():
    """Verificar mercado flash específico visible en la web"""
    
    print("\n" + "="*70)
    print("🔍 VERIFICANDO MERCADO FLASH ESPECÍFICO")
    print("="*70)
    
    # El mercado que vi en la web: btc-updown-15m-1767119400
    # Timestamp 1767119400 ≈ Dec 30, 2024 18:30:00 UTC
    
    # Intentar diferentes endpoints
    endpoints_to_try = [
        # Buscar por slug en Gamma
        f"{GAMMA_URL}/events?slug=btc-updown-15m-1767119400",
        f"{GAMMA_URL}/events?slug=btc-updown-15m",
        f"{GAMMA_URL}/markets?slug=btc-up-or-down",
        
        # Buscar eventos por título
        f"{GAMMA_URL}/events?title_contains=Bitcoin%20Up%20or%20Down",
        f"{GAMMA_URL}/events?active=true&limit=50",
    ]
    
    for endpoint in endpoints_to_try:
        print(f"\n📡 Probando: {endpoint}")
        try:
            resp = requests.get(endpoint, timeout=10)
            data = resp.json()
            
            if isinstance(data, list):
                print(f"   Resultados: {len(data)}")
                for item in data[:3]:
                    title = item.get("title", item.get("question", "N/A"))
                    print(f"   - {title[:60]}")
            elif isinstance(data, dict):
                if "error" in data:
                    print(f"   Error: {data.get('error')}")
                else:
                    print(f"   Keys: {list(data.keys())[:5]}")
                    
        except Exception as e:
            print(f"   ❌ Error: {e}")

def check_strapi_api():
    """Verificar API de Strapi (otra fuente de datos)"""
    
    print("\n" + "="*70)
    print("🔍 VERIFICANDO STRAPI API (FRONTEND)")
    print("="*70)
    
    # La web usa una API diferente para el frontend
    strapi_url = "https://strapi-matic.polymarket.com"
    
    endpoints = [
        "/markets?active=true&_limit=10",
        "/events?active=true&_limit=10",
    ]
    
    for endpoint in endpoints:
        print(f"\n📡 Probando: {strapi_url}{endpoint}")
        try:
            resp = requests.get(f"{strapi_url}{endpoint}", timeout=10)
            print(f"   Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"   Datos: {type(data)}, items: {len(data) if isinstance(data, list) else 'N/A'}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

def check_frontend_api():
    """Verificar API usada por el frontend"""
    
    print("\n" + "="*70)
    print("🔍 VERIFICANDO API DEL FRONTEND POLYMARKET")
    print("="*70)
    
    # El frontend usa estos endpoints
    endpoints = [
        "https://polymarket.com/api/events?tag=crypto&limit=10",
        "https://polymarket.com/_next/data/en/crypto.json",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    
    for url in endpoints:
        print(f"\n📡 Probando: {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            print(f"   Status: {resp.status_code}")
            if resp.status_code == 200:
                # Mostrar primeros 200 caracteres
                text = resp.text[:300]
                print(f"   Preview: {text}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")

def list_tradeable_markets():
    """Listar TODOS los mercados donde podemos colocar órdenes"""
    
    print("\n" + "="*70)
    print("💰 MERCADOS DONDE PODEMOS COLOCAR ÓRDENES")
    print("="*70)
    
    tradeable = []
    cursor = None
    
    for batch in range(100):
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
                # Criterio: podemos colocar órdenes
                if m.get("accepting_orders") and m.get("active"):
                    tokens = m.get("tokens", [])
                    if tokens:
                        # Verificar que tenga precios
                        has_prices = any(t.get("price") for t in tokens)
                        
                        tradeable.append({
                            "question": m.get("question", "N/A"),
                            "condition_id": m.get("condition_id", "N/A"),
                            "enable_order_book": m.get("enable_order_book"),
                            "tokens": tokens,
                            "end_date": m.get("end_date_iso", "N/A"),
                        })
            
            cursor = data.get("next_cursor")
            if not cursor:
                break
                
        except Exception as e:
            print(f"Error: {e}")
            break
    
    print(f"\n📊 Total mercados tradeables (accepting_orders=True & active=True): {len(tradeable)}")
    
    # Mostrar algunos con precios interesantes
    print("\n📋 Ejemplos de mercados tradeables:")
    
    interesting = []
    for m in tradeable:
        tokens = m["tokens"]
        # Buscar mercados con spreads interesantes
        if len(tokens) == 2:
            prices = [float(t.get("price", 0.5)) for t in tokens]
            if 0.2 < prices[0] < 0.8 and 0.2 < prices[1] < 0.8:
                interesting.append(m)
    
    for m in interesting[:10]:
        print(f"\n   📌 {m['question'][:60]}")
        print(f"      OrderBook: {m['enable_order_book']}")
        for t in m['tokens']:
            print(f"      {t.get('outcome')}: ${float(t.get('price', 0)):.3f}")
        
        # Verificar orderbook
        if m['tokens']:
            token_id = m['tokens'][0].get("token_id")
            if token_id:
                try:
                    book = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id}).json()
                    bids = book.get("bids", [])
                    asks = book.get("asks", [])
                    print(f"      📖 Bids: {len(bids)} | Asks: {len(asks)}")
                except:
                    pass

def main():
    print("\n" + "="*70)
    print("   INVESTIGACIÓN PROFUNDA DE POLYMARKET APIs")
    print("="*70)
    print(f"⏰ Timestamp: {datetime.now().isoformat()}")
    
    # 1. Estadísticas de estados
    investigate_market_states()
    
    # 2. Buscar mercados flash específicos
    check_specific_flash_market()
    
    # 3. Listar mercados tradeables
    list_tradeable_markets()

if __name__ == "__main__":
    main()
