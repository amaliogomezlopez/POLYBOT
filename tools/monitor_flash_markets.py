#!/usr/bin/env python3
"""
Monitor Flash Markets en Tiempo Real
Busca mercados flash (15min, 1h, 4h) con orderbook activo
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

CLOB_URL = "https://clob.polymarket.com"

def get_current_flash_markets():
    """Buscar mercados flash actuales directamente desde el CLOB"""
    
    print("\n" + "="*70)
    print("🔍 BUSCANDO MERCADOS FLASH ACTIVOS EN TIEMPO REAL")
    print("="*70)
    print(f"⏰ Hora actual: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Obtener todos los mercados
    all_markets = []
    cursor = None
    
    print("\n📊 Escaneando mercados...")
    
    for batch in range(20):  # Solo primeros 2000 mercados (los más recientes)
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
                
            all_markets.extend(markets)
            cursor = data.get("next_cursor")
            
            # Buscar flash markets en este lote
            for m in markets:
                question = m.get("question", "").lower()
                if any(x in question for x in ["up or down", "up/down", "15 min", "15min", "hourly", "4 hour"]):
                    enable_orderbook = m.get("enable_order_book", False)
                    accepting_orders = m.get("accepting_orders", False)
                    active = m.get("active", False)
                    
                    status = "🟢 ACTIVO" if (enable_orderbook and accepting_orders and active) else "🔴 Cerrado"
                    
                    tokens = m.get("tokens", [])
                    prices_info = ""
                    for t in tokens:
                        outcome = t.get("outcome", "?")
                        price = t.get("price", 0)
                        if price:
                            prices_info += f"{outcome}=${price:.2f} "
                    
                    print(f"\n   {status} | {m.get('question', 'N/A')[:60]}")
                    print(f"      ID: {m.get('condition_id', 'N/A')[:20]}...")
                    print(f"      OrderBook={enable_orderbook} | AcceptingOrders={accepting_orders} | Active={active}")
                    if prices_info:
                        print(f"      Precios: {prices_info}")
                    
                    # Si está activo, mostrar detalles completos
                    if enable_orderbook and accepting_orders and active:
                        print(f"\n      🎯 ¡MERCADO TRADEABLE ENCONTRADO!")
                        print(f"      Tokens:")
                        for t in tokens:
                            print(f"         - {t.get('outcome')}: token_id={t.get('token_id', 'N/A')[:20]}...")
                        
                        # Obtener orderbook
                        for t in tokens:
                            token_id = t.get("token_id")
                            if token_id:
                                try:
                                    book_resp = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id})
                                    book = book_resp.json()
                                    
                                    bids = book.get("bids", [])
                                    asks = book.get("asks", [])
                                    
                                    print(f"\n      📖 OrderBook para {t.get('outcome')}:")
                                    print(f"         Bids: {len(bids)} órdenes")
                                    print(f"         Asks: {len(asks)} órdenes")
                                    
                                    if bids:
                                        best_bid = max(bids, key=lambda x: float(x.get("price", 0)))
                                        print(f"         Mejor Bid: ${float(best_bid.get('price', 0)):.3f} ({best_bid.get('size', 0)} unidades)")
                                    
                                    if asks:
                                        best_ask = min(asks, key=lambda x: float(x.get("price", 0)))
                                        print(f"         Mejor Ask: ${float(best_ask.get('price', 0)):.3f} ({best_ask.get('size', 0)} unidades)")
                                    
                                    if bids and asks:
                                        spread = float(best_ask.get("price", 0)) - float(best_bid.get("price", 0))
                                        print(f"         Spread: ${spread:.3f}")
                                        
                                except Exception as e:
                                    print(f"         Error obteniendo orderbook: {e}")
            
            if not cursor:
                break
                
        except Exception as e:
            print(f"Error en batch {batch}: {e}")
            break
    
    print(f"\n📊 Total mercados escaneados: {len(all_markets)}")
    
    return all_markets

def search_by_slug():
    """Buscar mercados flash específicos por slug conocido"""
    
    print("\n" + "="*70)
    print("🔍 BUSCANDO MERCADOS FLASH POR SLUG/CONDITION")
    print("="*70)
    
    # Los slugs típicos de mercados flash
    flash_patterns = [
        "btc-updown-15m",
        "eth-updown-15m",
        "btc-updown-hourly",
        "eth-updown-hourly",
        "btc-updown-4h",
        "eth-updown-4h",
        "sol-updown-15m",
        "xrp-updown-15m",
    ]
    
    # Intentar obtener mercados recientes con timestamps
    current_time = int(time.time())
    
    # Los timestamps de los mercados flash están en el nombre
    # Ejemplo: btc-updown-15m-1767119400
    # 1767119400 es aproximadamente Dec 30, 2024
    
    print(f"\n⏰ Timestamp actual: {current_time}")
    print(f"   Fecha: {datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Buscar en Gamma API mercados con "up or down" en diferentes categorías
    gamma_url = "https://gamma-api.polymarket.com/events"
    
    try:
        # Buscar por tag "crypto" con límite alto
        resp = requests.get(gamma_url, params={
            "tag": "crypto",
            "limit": 500,
            "active": True
        })
        
        data = resp.json()
        
        flash_found = []
        for event in data:
            title = event.get("title", "").lower()
            if "up or down" in title or "15 min" in title or "15min" in title:
                markets = event.get("markets", [])
                for m in markets:
                    flash_found.append({
                        "title": event.get("title"),
                        "slug": event.get("slug"),
                        "condition_id": m.get("conditionId"),
                        "active": m.get("active"),
                        "closed": m.get("closed"),
                    })
        
        print(f"\n📊 Mercados flash encontrados en Gamma API: {len(flash_found)}")
        for f in flash_found[:10]:
            print(f"\n   {f['title']}")
            print(f"   Slug: {f['slug']}")
            print(f"   Active: {f['active']} | Closed: {f['closed']}")
            
    except Exception as e:
        print(f"Error consultando Gamma: {e}")
    
    # Buscar directamente en CLOB por condition_id conocidos
    print("\n\n🔍 Intentando URLs directas de mercados flash actuales...")
    
    # Obtener hora actual ET
    from datetime import timedelta
    
    # Calcular próximo intervalo de 15 minutos
    now_utc = datetime.now(timezone.utc)
    # ET es UTC-5 o UTC-4 dependiendo de horario de verano
    et_offset = timedelta(hours=-5)  # EST
    now_et = now_utc + et_offset
    
    # Redondear a próximo intervalo de 15 min
    minutes = now_et.minute
    next_interval = 15 * ((minutes // 15) + 1)
    if next_interval >= 60:
        next_et = now_et.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_et = now_et.replace(minute=next_interval % 60, second=0, microsecond=0)
    
    print(f"\n   Hora actual ET: {now_et.strftime('%H:%M')}")
    print(f"   Próximo intervalo 15-min: {next_et.strftime('%H:%M')}")

def check_live_orderbook():
    """Verificar si hay orderbooks activos con liquidez"""
    
    print("\n" + "="*70)
    print("📖 VERIFICANDO ORDERBOOKS CON LIQUIDEZ")
    print("="*70)
    
    # Obtener primeros 500 mercados y verificar sus orderbooks
    url = f"{CLOB_URL}/markets"
    resp = requests.get(url, params={"limit": 500})
    markets = resp.json().get("data", [])
    
    active_count = 0
    with_orders_count = 0
    
    for m in markets:
        if m.get("enable_order_book") and m.get("accepting_orders") and m.get("active"):
            active_count += 1
            
            # Verificar si tiene órdenes
            tokens = m.get("tokens", [])
            for t in tokens:
                token_id = t.get("token_id")
                if token_id:
                    try:
                        book_resp = requests.get(f"{CLOB_URL}/book", params={"token_id": token_id})
                        book = book_resp.json()
                        
                        bids = book.get("bids", [])
                        asks = book.get("asks", [])
                        
                        if bids or asks:
                            with_orders_count += 1
                            print(f"\n   🟢 {m.get('question', 'N/A')[:50]}")
                            print(f"      Bids: {len(bids)} | Asks: {len(asks)}")
                            
                            if bids and asks:
                                best_bid = max(bids, key=lambda x: float(x.get("price", 0)))
                                best_ask = min(asks, key=lambda x: float(x.get("price", 0)))
                                spread = float(best_ask.get("price", 0)) - float(best_bid.get("price", 0))
                                
                                print(f"      Mejor Bid: ${float(best_bid.get('price', 0)):.3f}")
                                print(f"      Mejor Ask: ${float(best_ask.get('price', 0)):.3f}")
                                print(f"      Spread: ${spread:.3f}")
                                
                                # Oportunidad de arbitraje?
                                if spread < 0.05:
                                    print(f"      ⚡ SPREAD BAJO - Posible oportunidad!")
                            
                            break  # Solo necesitamos verificar un token
                            
                    except Exception as e:
                        pass
    
    print(f"\n\n📊 RESUMEN:")
    print(f"   Mercados con orderbook activo: {active_count}")
    print(f"   Mercados con órdenes reales: {with_orders_count}")

def main():
    print("\n" + "="*70)
    print("   MONITOR DE MERCADOS FLASH - POLYMARKET")
    print("   Buscando oportunidades de trading en tiempo real")
    print("="*70)
    
    # 1. Verificar orderbooks activos
    check_live_orderbook()
    
    # 2. Buscar mercados flash
    get_current_flash_markets()
    
    # 3. Buscar por Gamma API
    search_by_slug()
    
    print("\n\n" + "="*70)
    print("💡 CONCLUSIONES:")
    print("="*70)
    print("""
    Los mercados flash (BTC Up/Down 15-min) funcionan así:
    
    1. Se crean nuevos mercados cada 15 minutos
    2. El trading está activo DURANTE esos 15 minutos
    3. Al finalizar el período, el mercado se cierra y resuelve
    
    Para operar:
    - Necesitas encontrar el mercado del próximo intervalo
    - El orderbook estará activo solo durante ese período
    - La resolución es automática basada en precio Chainlink
    
    @Account88888 compra tokens DOWN a precios bajos (~$0.21)
    esperando que BTC baje en el intervalo de 15 min.
    """)

if __name__ == "__main__":
    main()
