#!/usr/bin/env python3
"""
Scraper directo usando data-api.polymarket.com
Endpoint descubierto con Playwright
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from collections import defaultdict

# Configuración
ACCOUNT_ADDRESS = "0x7f69983eb28245bba0d5083502a78744a8f66162"  # Proxy wallet de Account88888
BASE_URL = "https://data-api.polymarket.com"
OUTPUT_DIR = "analysis"

def fetch_activity(address: str, limit: int = 100, offset: int = 0):
    """Obtener actividad de una cuenta"""
    
    url = f"{BASE_URL}/activity"
    params = {
        "user": address,
        "limit": limit,
        "offset": offset,
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://polymarket.com/",
        "Origin": "https://polymarket.com",
    }
    
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"   Error {resp.status_code}: {resp.text[:200]}")
        return None

def fetch_positions(address: str):
    """Obtener posiciones de una cuenta"""
    
    url = f"{BASE_URL}/positions"
    params = {
        "user": address,
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://polymarket.com/",
    }
    
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"   Error positions {resp.status_code}")
        return None

def fetch_traded(address: str):
    """Obtener mercados tradeados"""
    
    url = f"{BASE_URL}/traded"
    params = {
        "user": address,
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://polymarket.com/",
    }
    
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"   Error traded {resp.status_code}")
        return None

def fetch_profile_stats(address: str):
    """Obtener estadísticas del perfil"""
    
    url = "https://polymarket.com/api/profile/stats"
    params = {
        "address": address,
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://polymarket.com/",
    }
    
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    
    if resp.status_code == 200:
        return resp.json()
    else:
        return None

def fetch_user_pnl(address: str):
    """Obtener PnL del usuario"""
    
    url = "https://user-pnl-api.polymarket.com/user-pnl"
    params = {
        "user": address,
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://polymarket.com/",
    }
    
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    
    if resp.status_code == 200:
        return resp.json()
    else:
        return None

def fetch_all_activity(address: str):
    """Obtener TODA la actividad paginando"""
    
    print(f"\n📡 Obteniendo toda la actividad de {address}...")
    
    all_activity = []
    offset = 0
    limit = 100
    
    while True:
        print(f"   Offset {offset}...", end=" ")
        
        data = fetch_activity(address, limit=limit, offset=offset)
        
        if not data:
            print("Error")
            break
        
        if len(data) == 0:
            print("Fin de datos")
            break
        
        all_activity.extend(data)
        print(f"✓ {len(data)} items (total: {len(all_activity)})")
        
        offset += limit
        
        # Rate limiting
        time.sleep(0.5)
        
        # Safety limit
        if len(all_activity) >= 50000:
            print("   ⚠️ Límite de seguridad alcanzado")
            break
    
    return all_activity

def analyze_activity(activity: list):
    """Analizar la actividad capturada"""
    
    print(f"\n📊 Analizando {len(activity)} transacciones...")
    
    analysis = {
        "total_transactions": len(activity),
        "types": defaultdict(int),
        "outcomes": defaultdict(int),
        "markets": defaultdict(lambda: {"count": 0, "volume": 0, "outcomes": defaultdict(int)}),
        "hourly": defaultdict(int),
        "daily": defaultdict(int),
        "price_ranges": {
            "0.00-0.10": 0,
            "0.10-0.20": 0,
            "0.20-0.30": 0,
            "0.30-0.40": 0,
            "0.40-0.50": 0,
            "0.50-0.60": 0,
            "0.60-0.70": 0,
            "0.70-0.80": 0,
            "0.80-0.90": 0,
            "0.90-1.00": 0,
        },
        "total_volume": 0,
        "trades_by_crypto": defaultdict(int),
        "average_size": 0,
        "win_rate_estimate": 0,
    }
    
    sizes = []
    
    for tx in activity:
        # Tipo de transacción
        tx_type = tx.get("type") or tx.get("action") or "unknown"
        analysis["types"][tx_type] += 1
        
        # Outcome
        outcome = tx.get("outcome") or tx.get("side") or "unknown"
        analysis["outcomes"][outcome] += 1
        
        # Mercado
        market = tx.get("title") or tx.get("market") or tx.get("slug") or "unknown"
        analysis["markets"][market]["count"] += 1
        analysis["markets"][market]["outcomes"][outcome] += 1
        
        # Precio
        price = tx.get("price") or tx.get("avgPrice")
        if price:
            try:
                p = float(price)
                for range_key in analysis["price_ranges"]:
                    low, high = map(float, range_key.split("-"))
                    if low <= p < high:
                        analysis["price_ranges"][range_key] += 1
                        break
            except:
                pass
        
        # Tamaño
        size = tx.get("size") or tx.get("amount") or tx.get("usdcSize")
        if size:
            try:
                s = float(size)
                sizes.append(s)
                analysis["total_volume"] += s
                analysis["markets"][market]["volume"] += s
            except:
                pass
        
        # Categorizar por crypto
        market_lower = str(market).lower()
        if "btc" in market_lower or "bitcoin" in market_lower:
            analysis["trades_by_crypto"]["BTC"] += 1
        elif "eth" in market_lower or "ethereum" in market_lower:
            analysis["trades_by_crypto"]["ETH"] += 1
        elif "sol" in market_lower or "solana" in market_lower:
            analysis["trades_by_crypto"]["SOL"] += 1
        elif "xrp" in market_lower:
            analysis["trades_by_crypto"]["XRP"] += 1
        elif "doge" in market_lower:
            analysis["trades_by_crypto"]["DOGE"] += 1
        else:
            analysis["trades_by_crypto"]["Other"] += 1
        
        # Timestamp
        timestamp = tx.get("timestamp") or tx.get("createdAt")
        if timestamp:
            try:
                if isinstance(timestamp, str):
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                else:
                    dt = datetime.fromtimestamp(float(timestamp))
                
                analysis["hourly"][dt.strftime("%H:00")] += 1
                analysis["daily"][dt.strftime("%Y-%m-%d")] += 1
            except:
                pass
    
    # Calcular promedios
    if sizes:
        analysis["average_size"] = sum(sizes) / len(sizes)
        analysis["min_size"] = min(sizes)
        analysis["max_size"] = max(sizes)
        analysis["median_size"] = sorted(sizes)[len(sizes)//2]
    
    # Convertir defaultdicts para JSON
    analysis["types"] = dict(analysis["types"])
    analysis["outcomes"] = dict(analysis["outcomes"])
    analysis["hourly"] = dict(analysis["hourly"])
    analysis["daily"] = dict(analysis["daily"])
    analysis["trades_by_crypto"] = dict(analysis["trades_by_crypto"])
    
    # Top mercados
    top_markets = sorted(
        analysis["markets"].items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )[:100]
    
    analysis["top_markets"] = [
        {
            "market": k,
            "count": v["count"],
            "volume": v["volume"],
            "outcomes": dict(v["outcomes"]),
        }
        for k, v in top_markets
    ]
    
    del analysis["markets"]
    
    return analysis

def main():
    print("\n" + "="*70)
    print("🔍 SCRAPER DIRECTO DE @Account88888")
    print("="*70)
    print(f"Usando data-api.polymarket.com")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. Obtener toda la actividad
    activity = fetch_all_activity(ACCOUNT_ADDRESS)
    
    if activity:
        # Guardar actividad raw
        activity_file = f"{OUTPUT_DIR}/account88888_activity_complete.json"
        with open(activity_file, "w", encoding="utf-8") as f:
            json.dump(activity, f, indent=2, default=str)
        print(f"\n💾 Actividad guardada: {activity_file}")
    
    # 2. Obtener posiciones
    print("\n📡 Obteniendo posiciones...")
    positions = fetch_positions(ACCOUNT_ADDRESS)
    if positions:
        positions_file = f"{OUTPUT_DIR}/account88888_positions.json"
        with open(positions_file, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=2, default=str)
        print(f"   ✅ {len(positions)} posiciones guardadas")
    
    # 3. Obtener mercados tradeados
    print("\n📡 Obteniendo mercados tradeados...")
    traded = fetch_traded(ACCOUNT_ADDRESS)
    if traded:
        traded_file = f"{OUTPUT_DIR}/account88888_traded.json"
        with open(traded_file, "w", encoding="utf-8") as f:
            json.dump(traded, f, indent=2, default=str)
        print(f"   ✅ {len(traded) if isinstance(traded, list) else 'N/A'} mercados guardados")
    
    # 4. Obtener PnL
    print("\n📡 Obteniendo PnL...")
    pnl = fetch_user_pnl(ACCOUNT_ADDRESS)
    if pnl:
        pnl_file = f"{OUTPUT_DIR}/account88888_pnl.json"
        with open(pnl_file, "w", encoding="utf-8") as f:
            json.dump(pnl, f, indent=2, default=str)
        print(f"   ✅ PnL guardado")
    
    # 5. Analizar
    if activity:
        analysis = analyze_activity(activity)
        
        analysis_file = f"{OUTPUT_DIR}/account88888_deep_analysis.json"
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, default=str)
        print(f"\n💾 Análisis guardado: {analysis_file}")
        
        # Mostrar resumen
        print("\n" + "="*70)
        print("📊 RESUMEN DEL ANÁLISIS")
        print("="*70)
        print(f"   Total transacciones: {analysis['total_transactions']:,}")
        print(f"   Volumen total: ${analysis['total_volume']:,.2f}")
        print(f"   Tamaño promedio: ${analysis.get('average_size', 0):.2f}")
        
        print("\n📈 Por tipo de transacción:")
        for t, c in sorted(analysis["types"].items(), key=lambda x: -x[1])[:5]:
            print(f"   {t}: {c:,}")
        
        print("\n🎯 Por outcome:")
        for o, c in sorted(analysis["outcomes"].items(), key=lambda x: -x[1])[:5]:
            print(f"   {o}: {c:,}")
        
        print("\n💰 Por crypto:")
        for crypto, c in sorted(analysis["trades_by_crypto"].items(), key=lambda x: -x[1]):
            print(f"   {crypto}: {c:,}")
        
        print("\n📊 Distribución de precios de compra:")
        for range_key, count in analysis["price_ranges"].items():
            if count > 0:
                pct = count / analysis["total_transactions"] * 100
                bar = "█" * int(pct / 2)
                print(f"   ${range_key}: {count:,} ({pct:.1f}%) {bar}")
        
        print("\n🏆 Top 10 mercados:")
        for m in analysis["top_markets"][:10]:
            outcomes = m.get("outcomes", {})
            main_outcome = max(outcomes.items(), key=lambda x: x[1])[0] if outcomes else "N/A"
            print(f"   - {m['market'][:50]}")
            print(f"     Trades: {m['count']} | Vol: ${m['volume']:.2f} | Outcome: {main_outcome}")

if __name__ == "__main__":
    main()
