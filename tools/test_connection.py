#!/usr/bin/env python3
"""
Test de conexión a Polymarket API.
Verifica que las credenciales funcionan correctamente.
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)

def print_result(test: str, success: bool, details: str = ""):
    icon = "✅" if success else "❌"
    print(f"{icon} {test}")
    if details:
        print(f"   └─ {details}")

def main():
    print_header("POLYMARKET CONNECTION TEST")
    
    # 1. Verificar variables de entorno
    print("\n📋 Verificando variables de entorno...")
    
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
    api_key = os.getenv("API_KEY", "")
    secret = os.getenv("SECRET", "")
    passphrase = os.getenv("PASSPHRASE", "")
    signature_type = int(os.getenv("SIGNATURE_TYPE", "1"))
    
    env_checks = [
        ("POLYMARKET_PRIVATE_KEY", bool(private_key), f"{'***' + private_key[-8:] if private_key else 'NO SET'}"),
        ("POLYMARKET_FUNDER_ADDRESS", bool(funder_address), funder_address[:10] + "..." if funder_address else "NOT SET"),
        ("API_KEY", bool(api_key), api_key[:8] + "..." if api_key else "NOT SET"),
        ("SECRET", bool(secret), "***" + secret[-4:] if secret else "NOT SET"),
        ("PASSPHRASE", bool(passphrase), "***" + passphrase[-8:] if passphrase else "NOT SET"),
        ("SIGNATURE_TYPE", signature_type in [0, 1, 2], f"{signature_type} ({'EOA' if signature_type == 0 else 'POLY_PROXY' if signature_type == 1 else 'GNOSIS_SAFE'})"),
    ]
    
    all_env_ok = True
    for name, ok, details in env_checks:
        print_result(name, ok, details)
        if not ok:
            all_env_ok = False
    
    if not all_env_ok:
        print("\n❌ Faltan variables de entorno. Completa el archivo .env")
        return False
    
    # 2. Test de conexión a Gamma API (no requiere auth)
    print_header("TEST GAMMA API (Market Data)")
    
    try:
        import httpx
        
        response = httpx.get(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": 3, "active": True},
            timeout=10
        )
        
        if response.status_code == 200:
            markets = response.json()
            print_result("Conexión a Gamma API", True, f"Obtenidos {len(markets)} mercados")
            
            # Mostrar algunos mercados
            print("\n   📊 Mercados activos:")
            for m in markets[:3]:
                question = m.get("question", "N/A")[:50]
                print(f"      • {question}...")
        else:
            print_result("Conexión a Gamma API", False, f"Status: {response.status_code}")
            
    except Exception as e:
        print_result("Conexión a Gamma API", False, str(e))
    
    # 3. Test de conexión a CLOB API
    print_header("TEST CLOB API (Trading)")
    
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        
        print("   Inicializando cliente CLOB...")
        
        # Crear cliente con credenciales
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,  # Polygon
            signature_type=signature_type,
            funder=funder_address,
        )
        
        print_result("Cliente CLOB inicializado", True)
        
        # Configurar API credentials (Builder Keys)
        api_creds = ApiCreds(
            api_key=api_key,
            api_secret=secret,
            api_passphrase=passphrase,
        )
        client.set_api_creds(api_creds)
        print_result("API Credentials configuradas", True)
        
        # Test: Obtener servidor OK
        print("\n   🔌 Verificando endpoints...")
        
        # Test público: obtener un mercado
        try:
            # Buscar un mercado activo para probar
            markets_response = httpx.get(
                "https://gamma-api.polymarket.com/markets",
                params={"limit": 1, "active": True, "enableOrderBook": True},
                timeout=10
            )
            
            if markets_response.status_code == 200:
                markets = markets_response.json()
                if markets:
                    # Obtener token_id del primer mercado
                    clob_token_ids = markets[0].get("clobTokenIds", "")
                    if clob_token_ids:
                        token_id = clob_token_ids.split(",")[0].strip()
                        
                        # Obtener orderbook
                        book = client.get_order_book(token_id)
                        print_result("GET /book (orderbook)", True, f"Bids: {len(book.bids)}, Asks: {len(book.asks)}")
                    else:
                        print_result("GET /book", False, "No token_id disponible")
        except Exception as e:
            print_result("GET /book", False, str(e))
        
        # Test: Verificar balance/allowances (requiere L2 auth)
        try:
            # Intentar obtener balance
            balance_allowances = client.get_balance_allowance()
            print_result("GET /balance-allowance (L2 Auth)", True, f"Balance verificado")
        except Exception as e:
            error_msg = str(e)
            if "L2" in error_msg or "auth" in error_msg.lower():
                print_result("GET /balance-allowance", False, "Error de autenticación L2")
            else:
                print_result("GET /balance-allowance", False, error_msg[:60])
        
        # Test: Obtener órdenes abiertas
        try:
            open_orders = client.get_orders()
            print_result("GET /orders (órdenes abiertas)", True, f"{len(open_orders)} órdenes")
        except Exception as e:
            print_result("GET /orders", False, str(e)[:60])
            
    except ImportError:
        print_result("py-clob-client", False, "No instalado. Ejecuta: poetry install")
        return False
    except Exception as e:
        print_result("Conexión CLOB", False, str(e))
        return False
    
    # 4. Resumen
    print_header("RESUMEN")
    print("""
    🎯 Si ves checkmarks verdes (✅) en los tests principales,
       tu conexión está funcionando correctamente.
    
    📝 Próximos pasos:
       1. Deposita USDC en tu cuenta Polymarket
       2. Ejecuta: poetry run polybot scan
       3. Inicia dry-run: poetry run polybot dry-run --duration 30
    """)
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nCancelado por el usuario.")
        sys.exit(1)
