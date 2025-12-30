#!/usr/bin/env python3
"""
Scraper de actividad de @Account88888 usando múltiples fuentes
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
from collections import defaultdict

# Configuración
ACCOUNT_ADDRESS = "0x88888888dab62c19e25bcfb5add29efea56a0130"
POLYMARKET_PROFILE = "Account88888"
OUTPUT_DIR = "analysis"

def fetch_from_polymarket_profile():
    """Obtener datos del perfil de Polymarket"""
    
    print("\n📡 Intentando perfil de Polymarket...")
    
    urls = [
        f"https://polymarket.com/api/profile/{POLYMARKET_PROFILE}",
        f"https://polymarket.com/api/profile/{ACCOUNT_ADDRESS}",
        f"https://gamma-api.polymarket.com/users/{ACCOUNT_ADDRESS}",
        f"https://gamma-api.polymarket.com/users/{POLYMARKET_PROFILE}",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    
    for url in urls:
        try:
            print(f"   Probando: {url}")
            resp = requests.get(url, headers=headers, timeout=10)
            print(f"   Status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"   ✅ Datos obtenidos: {type(data)}")
                return data
        except Exception as e:
            print(f"   Error: {e}")
    
    return None

def fetch_positions():
    """Obtener posiciones del usuario"""
    
    print("\n📡 Obteniendo posiciones...")
    
    url = f"https://gamma-api.polymarket.com/positions"
    params = {
        "user": ACCOUNT_ADDRESS,
        "limit": 1000,
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"   ✅ Posiciones obtenidas: {len(data) if isinstance(data, list) else 'dict'}")
            return data
    except Exception as e:
        print(f"   Error: {e}")
    
    return None

def fetch_orders():
    """Obtener historial de órdenes"""
    
    print("\n📡 Obteniendo órdenes históricas...")
    
    all_orders = []
    
    # Probar diferentes endpoints
    endpoints = [
        f"https://clob.polymarket.com/orders?maker={ACCOUNT_ADDRESS}",
        f"https://clob.polymarket.com/orders?user={ACCOUNT_ADDRESS}",
    ]
    
    for url in endpoints:
        try:
            print(f"   Probando: {url}")
            resp = requests.get(url, timeout=30)
            print(f"   Status: {resp.status_code}")
            
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    all_orders.extend(data)
                elif isinstance(data, dict) and "orders" in data:
                    all_orders.extend(data["orders"])
                print(f"   ✅ Órdenes: {len(all_orders)}")
        except Exception as e:
            print(f"   Error: {e}")
    
    return all_orders

def fetch_trades():
    """Obtener trades ejecutados"""
    
    print("\n📡 Obteniendo trades ejecutados...")
    
    all_trades = []
    cursor = None
    
    for batch in range(100):  # Máximo 10,000 trades
        try:
            url = f"https://clob.polymarket.com/trades"
            params = {
                "maker": ACCOUNT_ADDRESS,
                "limit": 100,
            }
            if cursor:
                params["next_cursor"] = cursor
            
            resp = requests.get(url, params=params, timeout=30)
            
            if resp.status_code != 200:
                print(f"   Status: {resp.status_code}")
                break
            
            data = resp.json()
            trades = data if isinstance(data, list) else data.get("data", [])
            
            if not trades:
                break
            
            all_trades.extend(trades)
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            
            print(f"   Batch {batch+1}: {len(all_trades)} trades totales")
            
            if not cursor:
                break
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"   Error: {e}")
            break
    
    # También probar como taker
    cursor = None
    for batch in range(100):
        try:
            url = f"https://clob.polymarket.com/trades"
            params = {
                "taker": ACCOUNT_ADDRESS,
                "limit": 100,
            }
            if cursor:
                params["next_cursor"] = cursor
            
            resp = requests.get(url, params=params, timeout=30)
            
            if resp.status_code != 200:
                break
            
            data = resp.json()
            trades = data if isinstance(data, list) else data.get("data", [])
            
            if not trades:
                break
            
            all_trades.extend(trades)
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            
            print(f"   Batch taker {batch+1}: {len(all_trades)} trades totales")
            
            if not cursor:
                break
            
            time.sleep(0.3)
            
        except Exception as e:
            break
    
    return all_trades

def fetch_from_web_scrape():
    """Intentar obtener datos scrapeando la web"""
    
    print("\n📡 Scrapeando perfil web de Polymarket...")
    
    url = f"https://polymarket.com/profile/{POLYMARKET_PROFILE}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        print(f"   Status: {resp.status_code}")
        print(f"   Content length: {len(resp.text)} bytes")
        
        # Buscar datos JSON embebidos en la página
        text = resp.text
        
        # Buscar __NEXT_DATA__
        if "__NEXT_DATA__" in text:
            start = text.find('__NEXT_DATA__" type="application/json">')
            if start != -1:
                start += len('__NEXT_DATA__" type="application/json">')
                end = text.find("</script>", start)
                json_str = text[start:end]
                
                try:
                    data = json.loads(json_str)
                    print(f"   ✅ Datos Next.js encontrados")
                    return data
                except:
                    pass
        
        # Buscar otros patrones JSON
        import re
        json_patterns = re.findall(r'\{"props":\{.*?\}\}', text)
        if json_patterns:
            print(f"   Encontrados {len(json_patterns)} patrones JSON")
            
    except Exception as e:
        print(f"   Error: {e}")
    
    return None

def analyze_collected_data(trades, positions, profile_data):
    """Analizar todos los datos recolectados"""
    
    print("\n" + "="*70)
    print("📊 ANALIZANDO DATOS RECOLECTADOS")
    print("="*70)
    
    analysis = {
        "account": ACCOUNT_ADDRESS,
        "profile": POLYMARKET_PROFILE,
        "timestamp": datetime.now().isoformat(),
        "trades": {
            "total": len(trades) if trades else 0,
            "sample": trades[:10] if trades else [],
        },
        "positions": {
            "total": len(positions) if positions else 0,
            "sample": positions[:10] if positions else [],
        },
        "markets_traded": set(),
        "outcomes": defaultdict(int),
        "volume": 0,
    }
    
    if trades:
        print(f"\n📈 Analizando {len(trades)} trades...")
        
        for trade in trades:
            # Extraer información
            market = trade.get("market") or trade.get("asset_id", "unknown")
            outcome = trade.get("outcome") or trade.get("side", "unknown")
            size = float(trade.get("size") or trade.get("amount") or 0)
            price = float(trade.get("price") or 0)
            
            analysis["markets_traded"].add(str(market)[:50])
            analysis["outcomes"][outcome] += 1
            analysis["volume"] += size * price
        
        analysis["markets_traded"] = list(analysis["markets_traded"])[:100]
        analysis["outcomes"] = dict(analysis["outcomes"])
    
    if positions:
        print(f"\n📊 Analizando {len(positions)} posiciones...")
        
        for pos in positions[:20]:
            print(f"   - {pos.get('market', {}).get('question', 'N/A')[:50]}")
            print(f"     Outcome: {pos.get('outcome')} | Size: {pos.get('size')}")
    
    return analysis

def main():
    print("\n" + "="*70)
    print("   SCRAPER MULTI-FUENTE DE @Account88888")
    print("="*70)
    print(f"Cuenta: {POLYMARKET_PROFILE}")
    print(f"Dirección: {ACCOUNT_ADDRESS}")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Recolectar datos de múltiples fuentes
    profile_data = fetch_from_polymarket_profile()
    positions = fetch_positions()
    trades = fetch_trades()
    web_data = fetch_from_web_scrape()
    
    # Guardar datos crudos
    all_data = {
        "profile": profile_data,
        "positions": positions,
        "trades": trades,
        "web_data": web_data,
        "timestamp": datetime.now().isoformat(),
    }
    
    output_file = f"{OUTPUT_DIR}/account88888_raw_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, default=str)
    
    print(f"\n💾 Datos guardados en {output_file}")
    
    # Analizar
    analysis = analyze_collected_data(trades, positions, profile_data)
    
    analysis_file = f"{OUTPUT_DIR}/account88888_analysis_v2.json"
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"💾 Análisis guardado en {analysis_file}")
    
    # Resumen
    print("\n" + "="*70)
    print("📊 RESUMEN")
    print("="*70)
    print(f"   Trades obtenidos: {len(trades) if trades else 0}")
    print(f"   Posiciones obtenidas: {len(positions) if positions else 0}")
    print(f"   Profile data: {'✅' if profile_data else '❌'}")
    print(f"   Web data: {'✅' if web_data else '❌'}")
    
    if not trades and not positions:
        print("\n⚠️ No se pudieron obtener datos de trading.")
        print("   Las APIs de Polymarket no exponen historial de otros usuarios.")
        print("   Alternativa: Usar datos de blockchain (Polygon) directamente.")

if __name__ == "__main__":
    main()
