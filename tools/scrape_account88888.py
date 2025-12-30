#!/usr/bin/env python3
"""
Scraper completo de actividad de @Account88888
Obtiene TODOS los movimientos disponibles para análisis profundo
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Configuración
ACCOUNT_ADDRESS = "0x88888888dab62c19e25bcfb5add29efea56a0130"
GAMMA_URL = "https://gamma-api.polymarket.com"
OUTPUT_FILE = "analysis/account88888_full_activity.json"
ANALYSIS_FILE = "analysis/account88888_analysis.md"

def fetch_all_activity():
    """Obtener toda la actividad disponible de la cuenta"""
    
    print("\n" + "="*70)
    print("🔍 SCRAPING COMPLETO DE @Account88888")
    print("="*70)
    print(f"Dirección: {ACCOUNT_ADDRESS}")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_activity = []
    offset = 0
    limit = 100  # Máximo por request
    total_fetched = 0
    
    while True:
        try:
            url = f"{GAMMA_URL}/activity"
            params = {
                "user": ACCOUNT_ADDRESS,
                "limit": limit,
                "offset": offset,
            }
            
            resp = requests.get(url, params=params, timeout=30)
            
            if resp.status_code != 200:
                print(f"❌ Error HTTP {resp.status_code}")
                break
            
            data = resp.json()
            
            if not data:
                print(f"✅ Fin de datos en offset {offset}")
                break
            
            all_activity.extend(data)
            total_fetched += len(data)
            offset += limit
            
            print(f"   Descargados: {total_fetched} registros (offset: {offset})")
            
            # Rate limiting
            time.sleep(0.5)
            
            # Safety check - máximo 50,000 registros
            if total_fetched >= 50000:
                print("⚠️ Límite de seguridad alcanzado (50,000 registros)")
                break
                
        except Exception as e:
            print(f"❌ Error: {e}")
            break
    
    print(f"\n📊 Total registros obtenidos: {len(all_activity)}")
    
    return all_activity

def analyze_activity(activity):
    """Analizar la actividad en profundidad"""
    
    print("\n" + "="*70)
    print("📊 ANÁLISIS EN PROFUNDIDAD")
    print("="*70)
    
    if not activity:
        print("❌ No hay actividad para analizar")
        return None
    
    analysis = {
        "total_transactions": len(activity),
        "date_range": {},
        "action_types": defaultdict(int),
        "markets": defaultdict(lambda: {
            "count": 0,
            "total_amount": 0,
            "outcomes_bought": defaultdict(int),
            "prices": [],
            "first_seen": None,
            "last_seen": None,
        }),
        "daily_activity": defaultdict(int),
        "hourly_activity": defaultdict(int),
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
        "outcome_preference": defaultdict(int),
        "total_volume": 0,
        "average_trade_size": 0,
        "trade_sizes": [],
        "market_categories": defaultdict(int),
        "profitable_patterns": [],
        "time_patterns": {
            "weekday": defaultdict(int),
            "hour": defaultdict(int),
        },
    }
    
    timestamps = []
    
    for tx in activity:
        # Tipo de acción
        action = tx.get("action", "unknown")
        analysis["action_types"][action] += 1
        
        # Timestamp
        timestamp_str = tx.get("timestamp") or tx.get("createdAt")
        if timestamp_str:
            try:
                if "T" in str(timestamp_str):
                    ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                else:
                    ts = datetime.fromtimestamp(int(timestamp_str) / 1000, tz=timezone.utc)
                
                timestamps.append(ts)
                
                # Actividad por día
                day_key = ts.strftime("%Y-%m-%d")
                analysis["daily_activity"][day_key] += 1
                
                # Actividad por hora
                hour_key = ts.strftime("%H:00")
                analysis["hourly_activity"][hour_key] += 1
                
                # Patrones de tiempo
                analysis["time_patterns"]["weekday"][ts.strftime("%A")] += 1
                analysis["time_patterns"]["hour"][ts.hour] += 1
                
            except Exception as e:
                pass
        
        # Mercado
        market_slug = tx.get("slug") or tx.get("market", {}).get("slug", "unknown")
        market_title = tx.get("title") or tx.get("market", {}).get("question", market_slug)
        
        analysis["markets"][market_slug]["count"] += 1
        
        # Outcome comprado
        outcome = tx.get("outcome") or tx.get("side", "unknown")
        analysis["markets"][market_slug]["outcomes_bought"][outcome] += 1
        analysis["outcome_preference"][outcome] += 1
        
        # Precio
        price = tx.get("price") or tx.get("avgPrice")
        if price:
            try:
                price_float = float(price)
                analysis["markets"][market_slug]["prices"].append(price_float)
                
                # Clasificar por rango de precio
                for range_key in analysis["price_ranges"]:
                    low, high = map(float, range_key.split("-"))
                    if low <= price_float < high:
                        analysis["price_ranges"][range_key] += 1
                        break
            except:
                pass
        
        # Tamaño del trade
        amount = tx.get("amount") or tx.get("size") or tx.get("usdcSize")
        if amount:
            try:
                amount_float = float(amount)
                analysis["trade_sizes"].append(amount_float)
                analysis["total_volume"] += amount_float
                analysis["markets"][market_slug]["total_amount"] += amount_float
            except:
                pass
        
        # Categorizar mercado
        market_lower = market_title.lower() if market_title else ""
        if "btc" in market_lower or "bitcoin" in market_lower:
            analysis["market_categories"]["BTC/Bitcoin"] += 1
        elif "eth" in market_lower or "ethereum" in market_lower:
            analysis["market_categories"]["ETH/Ethereum"] += 1
        elif "sol" in market_lower or "solana" in market_lower:
            analysis["market_categories"]["SOL/Solana"] += 1
        elif "xrp" in market_lower:
            analysis["market_categories"]["XRP"] += 1
        elif "up or down" in market_lower or "updown" in market_lower or "15m" in market_lower or "15 min" in market_lower:
            analysis["market_categories"]["Flash Markets (15min/1h/4h)"] += 1
        elif "trump" in market_lower:
            analysis["market_categories"]["Politics - Trump"] += 1
        elif "election" in market_lower or "president" in market_lower:
            analysis["market_categories"]["Politics - Elections"] += 1
        elif "nfl" in market_lower or "nba" in market_lower or "sports" in market_lower:
            analysis["market_categories"]["Sports"] += 1
        else:
            analysis["market_categories"]["Other"] += 1
    
    # Calcular estadísticas
    if timestamps:
        analysis["date_range"]["first"] = min(timestamps).isoformat()
        analysis["date_range"]["last"] = max(timestamps).isoformat()
        analysis["date_range"]["days_active"] = (max(timestamps) - min(timestamps)).days
    
    if analysis["trade_sizes"]:
        analysis["average_trade_size"] = sum(analysis["trade_sizes"]) / len(analysis["trade_sizes"])
        analysis["min_trade_size"] = min(analysis["trade_sizes"])
        analysis["max_trade_size"] = max(analysis["trade_sizes"])
        analysis["median_trade_size"] = sorted(analysis["trade_sizes"])[len(analysis["trade_sizes"])//2]
    
    # Top mercados
    top_markets = sorted(
        analysis["markets"].items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )[:50]
    
    analysis["top_markets"] = [
        {
            "slug": slug,
            "count": data["count"],
            "total_amount": data["total_amount"],
            "outcomes": dict(data["outcomes_bought"]),
            "avg_price": sum(data["prices"]) / len(data["prices"]) if data["prices"] else 0,
        }
        for slug, data in top_markets
    ]
    
    # Convertir defaultdicts a dicts para JSON
    analysis["action_types"] = dict(analysis["action_types"])
    analysis["daily_activity"] = dict(analysis["daily_activity"])
    analysis["hourly_activity"] = dict(analysis["hourly_activity"])
    analysis["outcome_preference"] = dict(analysis["outcome_preference"])
    analysis["market_categories"] = dict(analysis["market_categories"])
    analysis["time_patterns"]["weekday"] = dict(analysis["time_patterns"]["weekday"])
    analysis["time_patterns"]["hour"] = dict(analysis["time_patterns"]["hour"])
    
    # Eliminar campos grandes para el JSON
    del analysis["markets"]
    del analysis["trade_sizes"]
    
    return analysis

def generate_report(activity, analysis):
    """Generar reporte detallado en Markdown"""
    
    report = f"""# Análisis Completo de @Account88888

## Resumen Ejecutivo

| Métrica | Valor |
|---------|-------|
| **Total Transacciones** | {analysis['total_transactions']:,} |
| **Volumen Total** | ${analysis['total_volume']:,.2f} |
| **Tamaño Promedio Trade** | ${analysis['average_trade_size']:.2f} |
| **Período de Actividad** | {analysis['date_range'].get('days_active', 'N/A')} días |
| **Primera Actividad** | {analysis['date_range'].get('first', 'N/A')[:10]} |
| **Última Actividad** | {analysis['date_range'].get('last', 'N/A')[:10]} |

---

## Tipos de Acciones

| Acción | Cantidad | % del Total |
|--------|----------|-------------|
"""
    
    total = analysis['total_transactions']
    for action, count in sorted(analysis['action_types'].items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        report += f"| {action} | {count:,} | {pct:.1f}% |\n"
    
    report += """
---

## Preferencia de Outcomes

| Outcome | Cantidad | % del Total |
|---------|----------|-------------|
"""
    
    for outcome, count in sorted(analysis['outcome_preference'].items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        report += f"| {outcome} | {count:,} | {pct:.1f}% |\n"
    
    report += """
---

## Categorías de Mercados

| Categoría | Trades | % del Total |
|-----------|--------|-------------|
"""
    
    for category, count in sorted(analysis['market_categories'].items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0
        report += f"| {category} | {count:,} | {pct:.1f}% |\n"
    
    report += """
---

## Distribución de Precios de Compra

| Rango de Precio | Cantidad | % del Total |
|-----------------|----------|-------------|
"""
    
    for range_key, count in analysis['price_ranges'].items():
        pct = (count / total * 100) if total > 0 else 0
        if count > 0:
            report += f"| ${range_key} | {count:,} | {pct:.1f}% |\n"
    
    report += """
---

## Patrones Temporales

### Actividad por Día de la Semana

| Día | Trades | % del Total |
|-----|--------|-------------|
"""
    
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for day in weekday_order:
        count = analysis['time_patterns']['weekday'].get(day, 0)
        pct = (count / total * 100) if total > 0 else 0
        if count > 0:
            report += f"| {day} | {count:,} | {pct:.1f}% |\n"
    
    report += """
### Actividad por Hora (UTC)

| Hora | Trades | % del Total |
|------|--------|-------------|
"""
    
    for hour in sorted(analysis['time_patterns']['hour'].keys()):
        count = analysis['time_patterns']['hour'][hour]
        pct = (count / total * 100) if total > 0 else 0
        if count > 0:
            report += f"| {hour:02d}:00 | {count:,} | {pct:.1f}% |\n"
    
    report += """
---

## Top 20 Mercados Más Operados

| # | Mercado | Trades | Volumen | Outcome Principal |
|---|---------|--------|---------|-------------------|
"""
    
    for i, market in enumerate(analysis['top_markets'][:20], 1):
        slug = market['slug'][:40] + "..." if len(market['slug']) > 40 else market['slug']
        outcomes = market['outcomes']
        main_outcome = max(outcomes.items(), key=lambda x: x[1])[0] if outcomes else "N/A"
        report += f"| {i} | {slug} | {market['count']:,} | ${market['total_amount']:,.2f} | {main_outcome} |\n"
    
    report += f"""
---

## Estadísticas de Tamaño de Trades

| Métrica | Valor |
|---------|-------|
| Tamaño Mínimo | ${analysis.get('min_trade_size', 0):.2f} |
| Tamaño Máximo | ${analysis.get('max_trade_size', 0):.2f} |
| Tamaño Promedio | ${analysis['average_trade_size']:.2f} |
| Tamaño Mediano | ${analysis.get('median_trade_size', 0):.2f} |

---

## Insights Clave

### 1. Estrategia Principal
"""
    
    # Determinar estrategia principal
    categories = analysis['market_categories']
    flash_count = categories.get("Flash Markets (15min/1h/4h)", 0)
    btc_count = categories.get("BTC/Bitcoin", 0)
    eth_count = categories.get("ETH/Ethereum", 0)
    
    if flash_count > total * 0.3 or btc_count > total * 0.3 or eth_count > total * 0.3:
        report += """
**Trading de Alta Frecuencia en Mercados Flash de Crypto**

@Account88888 se especializa en mercados flash de criptomonedas (BTC/ETH Up/Down).
Estos mercados resuelven en 15 minutos a 4 horas, permitiendo múltiples trades por día.
"""
    else:
        report += """
**Trading Diversificado**

@Account88888 opera en múltiples categorías de mercados sin una concentración clara.
"""
    
    # Preferencia de outcome
    down_count = analysis['outcome_preference'].get('Down', 0) + analysis['outcome_preference'].get('No', 0)
    up_count = analysis['outcome_preference'].get('Up', 0) + analysis['outcome_preference'].get('Yes', 0)
    
    report += f"""
### 2. Sesgo Direccional

| Dirección | Trades | % |
|-----------|--------|---|
| DOWN/NO | {down_count:,} | {(down_count/total*100):.1f}% |
| UP/YES | {up_count:,} | {(up_count/total*100):.1f}% |

"""
    
    if down_count > up_count * 1.5:
        report += "**Fuerte preferencia por posiciones BAJISTAS (Down/No)**\n"
    elif up_count > down_count * 1.5:
        report += "**Fuerte preferencia por posiciones ALCISTAS (Up/Yes)**\n"
    else:
        report += "**Estrategia balanceada entre Up y Down**\n"
    
    # Precios de entrada
    low_price_count = sum(analysis['price_ranges'].get(k, 0) for k in ["0.00-0.10", "0.10-0.20", "0.20-0.30"])
    
    report += f"""
### 3. Estrategia de Precios

Trades con precio < $0.30: {low_price_count:,} ({(low_price_count/total*100):.1f}%)

"""
    
    if low_price_count > total * 0.5:
        report += """**Estrategia de "Long Shot"**

Compra tokens baratos (< $0.30) con alto potencial de ganancia.
ROI típico si gana: 200-400%
"""
    else:
        report += """**Estrategia Mixta de Precios**

Opera en diferentes rangos de precio según la oportunidad.
"""
    
    report += f"""
---

## Recomendaciones Basadas en el Análisis

### Para Replicar esta Estrategia:

1. **Mercados Objetivo**: Flash markets de crypto (BTC/ETH Up/Down 15-min)
2. **Precio de Entrada**: Buscar tokens < $0.25 para maximizar ROI
3. **Tamaño de Posición**: ${analysis['average_trade_size']:.2f} promedio
4. **Frecuencia**: {analysis['total_transactions']} trades en {analysis['date_range'].get('days_active', 1)} días = ~{analysis['total_transactions'] // max(analysis['date_range'].get('days_active', 1), 1)} trades/día
5. **Horarios Activos**: Verificar patrones horarios arriba

### Riesgos a Considerar:

- Alto volumen de trades puede generar pérdidas acumuladas
- Mercados flash son volátiles y difíciles de predecir
- Requiere capital suficiente para absorber rachas perdedoras

---

*Análisis generado el {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
*Datos: {analysis['total_transactions']:,} transacciones analizadas*
"""
    
    return report

def main():
    print("\n" + "="*70)
    print("   SCRAPER COMPLETO DE @Account88888")
    print("="*70)
    
    # 1. Obtener toda la actividad
    activity = fetch_all_activity()
    
    if not activity:
        print("❌ No se pudo obtener actividad")
        return
    
    # 2. Guardar datos crudos
    print(f"\n💾 Guardando datos en {OUTPUT_FILE}...")
    os.makedirs("analysis", exist_ok=True)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(activity, f, indent=2, default=str)
    
    print(f"   ✅ Guardados {len(activity)} registros")
    
    # 3. Analizar
    analysis = analyze_activity(activity)
    
    if not analysis:
        print("❌ Error en análisis")
        return
    
    # 4. Guardar análisis
    analysis_json_file = "analysis/account88888_analysis.json"
    with open(analysis_json_file, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"   ✅ Análisis guardado en {analysis_json_file}")
    
    # 5. Generar reporte
    report = generate_report(activity, analysis)
    
    with open(ANALYSIS_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"   ✅ Reporte guardado en {ANALYSIS_FILE}")
    
    # 6. Mostrar resumen
    print("\n" + "="*70)
    print("📊 RESUMEN DEL ANÁLISIS")
    print("="*70)
    print(f"   Total transacciones: {analysis['total_transactions']:,}")
    print(f"   Volumen total: ${analysis['total_volume']:,.2f}")
    print(f"   Tamaño promedio: ${analysis['average_trade_size']:.2f}")
    print(f"   Período: {analysis['date_range'].get('days_active', 'N/A')} días")
    
    print("\n📈 TOP CATEGORÍAS:")
    for cat, count in sorted(analysis['market_categories'].items(), key=lambda x: -x[1])[:5]:
        print(f"   {cat}: {count:,} trades")
    
    print("\n🎯 PREFERENCIA OUTCOMES:")
    for outcome, count in sorted(analysis['outcome_preference'].items(), key=lambda x: -x[1])[:5]:
        print(f"   {outcome}: {count:,} trades")
    
    print("\n✅ Análisis completo guardado en /analysis/")

if __name__ == "__main__":
    main()
