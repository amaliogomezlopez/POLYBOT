#!/usr/bin/env python3
"""
Acceder a mercados REALES via CLOB API y py-clob-client
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import httpx

load_dotenv()

def explore_clob_api():
    print("=" * 80)
    print("  EXPLORANDO CLOB API - MERCADOS REALES")
    print("=" * 80)
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 1. Endpoints públicos de CLOB
    clob_endpoints = [
        "/markets",
        "/sampling-markets",
        "/sampling-simplified-markets",
    ]
    
    for endpoint in clob_endpoints:
        print(f"\n{'─'*80}")
        print(f"ENDPOINT: https://clob.polymarket.com{endpoint}")
        print("─" * 80)
        
        try:
            response = httpx.get(
                f"https://clob.polymarket.com{endpoint}",
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, list):
                    print(f"✅ Resultados: {len(data)}")
                    
                    for item in data[:5]:
                        if isinstance(item, dict):
                            print(f"\n  • {json.dumps(item, indent=4)[:300]}...")
                elif isinstance(data, dict):
                    print(f"✅ Respuesta:")
                    print(f"  {json.dumps(data, indent=2)[:500]}...")
            else:
                print(f"❌ Status: {response.status_code}")
                print(f"   {response.text[:200]}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # 2. Usar py-clob-client para ver mercados
    print("\n" + "=" * 80)
    print("  USANDO PY-CLOB-CLIENT")
    print("=" * 80)
    
    try:
        from py_clob_client.client import ClobClient
        
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        funder = os.getenv("POLYMARKET_FUNDER_ADDRESS")
        sig_type = int(os.getenv("SIGNATURE_TYPE", "1"))
        
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=sig_type,
            funder=funder,
        )
        
        # Derivar credenciales
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        
        print("✅ Cliente inicializado")
        
        # Ver mercados disponibles
        print("\n📊 Obteniendo mercados...")
        markets = client.get_markets()
        print(f"   Mercados obtenidos: {len(markets) if markets else 0}")
        
        if markets:
            print("\n   Primeros mercados:")
            for m in markets[:5]:
                print(f"   • {m}")
        
        # Ver órdenes abiertas (para verificar conexión)
        orders = client.get_orders()
        print(f"\n📋 Órdenes abiertas: {len(orders)}")
        
    except Exception as e:
        print(f"❌ Error py-clob-client: {e}")
    
    # 3. Buscar en Strapi/Data API
    print("\n" + "=" * 80)
    print("  DATA API - MERCADOS ACTUALES")
    print("=" * 80)
    
    data_endpoints = [
        "https://strapi-matic.poly.market/markets?active=true&_limit=20",
        "https://strapi-matic.poly.market/markets?_sort=volume:DESC&_limit=20",
    ]
    
    for url in data_endpoints:
        print(f"\n{'─'*80}")
        print(f"URL: {url}")
        print("─" * 80)
        
        try:
            response = httpx.get(url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Resultados: {len(data)}")
                
                for m in data[:3]:
                    print(f"\n  • {m.get('question', 'N/A')[:50]}...")
                    print(f"    active: {m.get('active')}")
                    print(f"    closed: {m.get('closed')}")
                    print(f"    endDate: {m.get('endDate', 'N/A')[:20]}")
            else:
                print(f"❌ Status: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    explore_clob_api()
