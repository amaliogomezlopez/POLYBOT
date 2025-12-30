#!/usr/bin/env python3
"""
Captura y análisis de actividad de @Account88888
Este trader tiene +$372k de profit - analizamos su estrategia
"""

import httpx
import json
import time
from datetime import datetime
from pathlib import Path

# La dirección del wallet de @Account88888 (podemos obtenerla de Polygonscan)
# Por ahora usamos la API de datos de Polymarket

ACCOUNT_ADDRESS = None  # Lo obtendremos de los txs

def fetch_account_activity(username: str = "Account88888"):
    """Fetch activity data from Polymarket Data API"""
    
    print(f"\n{'='*60}")
    print(f"  ANÁLISIS DE @{username}")
    print(f"{'='*60}")
    
    # La API de datos de Polymarket
    base_url = "https://data-api.polymarket.com"
    
    # Intentar obtener trades públicos
    try:
        # Buscar la dirección del usuario en su perfil
        profile_url = f"https://polymarket.com/api/users/{username}"
        
        # Usar la API gamma para buscar mercados activos de crypto flash
        print("\n📊 Buscando mercados flash de BTC/ETH...")
        
        gamma_response = httpx.get(
            "https://gamma-api.polymarket.com/markets",
            params={
                "limit": 50,
                "active": True,
                "closed": False,
            },
            timeout=15
        )
        
        if gamma_response.status_code == 200:
            markets = gamma_response.json()
            
            # Filtrar mercados de BTC/ETH Up/Down (flash markets)
            flash_markets = []
            for m in markets:
                question = m.get("question", "").lower()
                if ("up or down" in question and 
                    ("bitcoin" in question or "btc" in question or 
                     "ethereum" in question or "eth" in question)):
                    flash_markets.append(m)
            
            print(f"✅ Encontrados {len(flash_markets)} mercados flash activos")
            
            if flash_markets:
                print("\n📈 MERCADOS FLASH ACTIVOS:")
                print("-" * 60)
                
                for i, m in enumerate(flash_markets[:10]):
                    question = m.get("question", "N/A")[:60]
                    outcomes = m.get("outcomePrices", "")
                    volume = m.get("volume", "0")
                    
                    # Parsear precios
                    try:
                        prices = json.loads(outcomes) if outcomes else []
                        if len(prices) >= 2:
                            up_price = float(prices[0])
                            down_price = float(prices[1])
                            spread = up_price + down_price
                            profit_pct = ((1 - spread) / spread) * 100 if spread < 1 else 0
                            
                            print(f"\n{i+1}. {question}...")
                            print(f"   UP: ${up_price:.2f} | DOWN: ${down_price:.2f}")
                            print(f"   Spread: ${spread:.4f} | Profit potencial: {profit_pct:.2f}%")
                            print(f"   Volume: ${float(volume):,.0f}")
                    except:
                        pass
                        
            return flash_markets
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def analyze_strategy():
    """Analiza la estrategia basada en los datos capturados"""
    
    print(f"\n{'='*60}")
    print("  ANÁLISIS DE ESTRATEGIA @Account88888")
    print(f"{'='*60}")
    
    print("""
    📊 DATOS OBSERVADOS (de la captura web):
    
    PERFIL:
    ├── Profit Total: $372,147.62
    ├── Positions Value: $44.1k
    ├── Biggest Win: $42.3k
    ├── Predictions: 8,036
    └── Joined: Dec 2025
    
    ACTIVIDAD RECIENTE (últimos minutos):
    ┌─────────────────────────────────────────────────────────────┐
    │ Mercado                          │ Lado  │ Precio │ Shares  │
    ├─────────────────────────────────────────────────────────────┤
    │ BTC Up/Down 1:30-1:45PM         │ DOWN  │ $0.21  │ 1.3     │
    │ ETH Up/Down 1:30-1:45PM         │ DOWN  │ $0.42  │ 22.2    │
    │ BTC Up/Down 1:30-1:45PM         │ DOWN  │ $0.22  │ 31.9    │
    │ BTC Up/Down 1:30-1:45PM         │ DOWN  │ $0.21  │ 20.0    │
    │ BTC Up/Down 1:30-1:45PM         │ DOWN  │ $0.22  │ 42.0    │
    └─────────────────────────────────────────────────────────────┘
    
    🔍 PATRONES IDENTIFICADOS:
    
    1. MERCADOS PREFERIDOS:
       ├── BTC Up/Down 15-min flash markets
       └── ETH Up/Down 15-min flash markets
    
    2. ESTRATEGIA:
       ├── Compra agresiva de DOWN cuando precio bajo (~$0.21-0.22)
       ├── Múltiples órdenes pequeñas en el mismo mercado
       ├── Parece apostar DIRECCIONALMENTE, no delta-neutral
       └── Alta frecuencia: múltiples trades por minuto
    
    3. SIZING:
       ├── Órdenes pequeñas: $4-$10 por trade
       ├── Pero muchas órdenes simultáneas
       └── Total expuesto: $44k en posiciones
    
    4. TIMING:
       ├── Opera en mercados de 15 minutos
       ├── Entra en los últimos minutos antes del cierre
       └── Posible estrategia de momentum/predicción
    
    ⚠️  IMPORTANTE:
    
    Esta cuenta NO usa estrategia delta-neutral.
    Está haciendo PREDICCIONES direccionales (apuesta a DOWN).
    
    Su profit puede venir de:
    ├── Análisis técnico de BTC/ETH
    ├── Bots de trading con señales
    ├── Información privilegiada sobre movimientos
    └── Simplemente suerte + alto volumen
    
    🎯 PARA NUESTRO BOT (Delta-Neutral):
    
    Nuestra estrategia es DIFERENTE:
    ├── Compramos AMBOS lados (UP + DOWN)
    ├── Profit viene del spread < $1.00
    ├── Sin riesgo direccional
    └── Profit más pequeño pero consistente
    """)

def get_live_flash_markets():
    """Obtiene mercados flash en vivo con spreads"""
    
    print(f"\n{'='*60}")
    print("  MERCADOS FLASH EN VIVO - OPORTUNIDADES")
    print(f"{'='*60}\n")
    
    try:
        response = httpx.get(
            "https://gamma-api.polymarket.com/markets",
            params={
                "limit": 100,
                "active": True,
                "closed": False,
            },
            timeout=15
        )
        
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            return
        
        markets = response.json()
        
        # Filtrar mercados con orderbook activo y tipo flash
        opportunities = []
        
        for m in markets:
            question = m.get("question", "").lower()
            enable_book = m.get("enableOrderBook", False)
            
            # Solo mercados Up/Down de crypto
            if not enable_book:
                continue
            if "up or down" not in question:
                continue
            if not any(x in question for x in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol"]):
                continue
            
            # Calcular spread
            outcomes = m.get("outcomePrices", "")
            try:
                prices = json.loads(outcomes) if outcomes else []
                if len(prices) >= 2:
                    up_price = float(prices[0])
                    down_price = float(prices[1])
                    spread = up_price + down_price
                    
                    if spread < 1.0:  # Oportunidad de arbitraje
                        profit_pct = ((1 - spread) / spread) * 100
                        opportunities.append({
                            "question": m.get("question", "")[:50],
                            "up": up_price,
                            "down": down_price,
                            "spread": spread,
                            "profit_pct": profit_pct,
                            "volume": float(m.get("volume", 0)),
                            "end_date": m.get("endDate", ""),
                            "token_ids": m.get("clobTokenIds", ""),
                        })
            except:
                continue
        
        # Ordenar por profit potencial
        opportunities.sort(key=lambda x: x["profit_pct"], reverse=True)
        
        if opportunities:
            print(f"🎯 OPORTUNIDADES DE ARBITRAJE ENCONTRADAS: {len(opportunities)}\n")
            print(f"{'Mercado':<50} {'UP':>6} {'DOWN':>6} {'Spread':>8} {'Profit':>8}")
            print("-" * 80)
            
            for opp in opportunities[:15]:
                print(f"{opp['question']:<50} "
                      f"${opp['up']:.2f}  ${opp['down']:.2f}  "
                      f"${opp['spread']:.4f}  {opp['profit_pct']:>6.2f}%")
        else:
            print("⚠️  No se encontraron oportunidades de arbitraje en este momento")
            print("   (spread UP + DOWN >= $1.00 en todos los mercados)")
        
        return opportunities
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def save_analysis():
    """Guarda el análisis en archivo"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    analysis = {
        "timestamp": timestamp,
        "target_account": "Account88888",
        "observed_data": {
            "profit_total": 372147.62,
            "positions_value": 44100,
            "biggest_win": 42300,
            "predictions_count": 8036,
            "joined": "Dec 2025"
        },
        "strategy_analysis": {
            "type": "DIRECTIONAL (not delta-neutral)",
            "markets": ["BTC Up/Down 15min", "ETH Up/Down 15min"],
            "preferred_side": "DOWN",
            "order_size": "$4-$10 per trade",
            "frequency": "Multiple trades per minute",
            "timing": "Last minutes before market close"
        },
        "our_strategy_comparison": {
            "type": "Delta-Neutral Arbitrage",
            "risk": "Low (buy both sides)",
            "profit_source": "Spread < $1.00",
            "expected_roi": "1-5% per trade"
        }
    }
    
    output_path = Path("analysis/account88888_strategy.json")
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2)
    
    print(f"\n💾 Análisis guardado en: {output_path}")

if __name__ == "__main__":
    # 1. Buscar mercados flash activos
    flash_markets = fetch_account_activity()
    
    # 2. Analizar la estrategia del competidor
    analyze_strategy()
    
    # 3. Buscar oportunidades de arbitraje en vivo
    opportunities = get_live_flash_markets()
    
    # 4. Guardar análisis
    save_analysis()
    
    print(f"\n{'='*60}")
    print("  RESUMEN")
    print(f"{'='*60}")
    print("""
    @Account88888 usa estrategia DIRECCIONAL (apuesta a un lado).
    
    Nosotros usamos DELTA-NEUTRAL (compramos ambos lados).
    
    Para validar nuestra estrategia:
    1. Buscar mercados con spread < $1.00
    2. Comprar UP + DOWN simultáneamente
    3. Profit garantizado = $1.00 - spread
    
    Próximo paso: Ejecutar dry-run con trades mínimos ($2-5)
    """)
