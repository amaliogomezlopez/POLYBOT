#!/usr/bin/env python3
"""
Test de conexión mejorado a Polymarket API.
"""

import os
from dotenv import load_dotenv
import httpx

load_dotenv()

def main():
    print("\n" + "="*60)
    print("  POLYMARKET CONNECTION TEST v2")
    print("="*60)
    
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
    api_key = os.getenv("API_KEY", "")
    secret = os.getenv("SECRET", "")
    passphrase = os.getenv("PASSPHRASE", "")
    signature_type = int(os.getenv("SIGNATURE_TYPE", "1"))
    
    print(f"\n📋 Configuración:")
    print(f"   Private Key: ***{private_key[-8:]}")
    print(f"   Funder: {funder_address}")
    print(f"   Signature Type: {signature_type}")
    
    # Test 1: Gamma API
    print("\n" + "-"*60)
    print("TEST 1: Gamma API (datos de mercado)")
    print("-"*60)
    
    try:
        response = httpx.get(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": 5, "active": True, "closed": False},
            timeout=15
        )
        
        if response.status_code == 200:
            markets = response.json()
            print(f"✅ Gamma API OK - {len(markets)} mercados obtenidos")
            
            # Buscar mercados con orderbook activo
            markets_with_book = [m for m in markets if m.get("enableOrderBook")]
            print(f"   Mercados con orderbook: {len(markets_with_book)}")
            
            if markets_with_book:
                market = markets_with_book[0]
                print(f"\n   📊 Mercado de ejemplo:")
                print(f"      Pregunta: {market.get('question', 'N/A')[:60]}...")
                print(f"      Token IDs: {market.get('clobTokenIds', 'N/A')[:40]}...")
                
                # Guardar para test CLOB
                return market
        else:
            print(f"❌ Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None
    
    return None

def test_clob(market):
    print("\n" + "-"*60)
    print("TEST 2: CLOB API (trading)")
    print("-"*60)
    
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
    api_key = os.getenv("API_KEY", "")
    secret = os.getenv("SECRET", "")
    passphrase = os.getenv("PASSPHRASE", "")
    signature_type = int(os.getenv("SIGNATURE_TYPE", "1"))
    
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        
        # Método 1: Crear cliente y derivar credenciales
        print("\n   🔌 Método 1: Inicializar con private key...")
        
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=signature_type,
            funder=funder_address,
        )
        print("   ✅ Cliente creado")
        
        # Intentar derivar/crear API credentials
        print("\n   🔑 Derivando API credentials desde private key...")
        try:
            derived_creds = client.derive_api_key()
            print(f"   ✅ Credentials derivadas:")
            print(f"      API Key: {derived_creds.api_key[:12]}...")
            client.set_api_creds(derived_creds)
        except Exception as e:
            print(f"   ⚠️  No se pudieron derivar: {e}")
            print("\n   🔑 Usando credentials manuales (Builder Keys)...")
            
            # Usar las credenciales del .env
            manual_creds = ApiCreds(
                api_key=api_key,
                api_secret=secret,
                api_passphrase=passphrase,
            )
            client.set_api_creds(manual_creds)
            print("   ✅ Credentials manuales configuradas")
        
        # Test: Obtener precio de un mercado
        if market:
            token_ids = market.get("clobTokenIds", "").split(",")
            if token_ids and token_ids[0]:
                token_id = token_ids[0].strip()
                print(f"\n   📈 Obteniendo precio para token: {token_id[:20]}...")
                
                try:
                    price = client.get_price(token_id, "BUY")
                    print(f"   ✅ Precio BUY: ${price}")
                except Exception as e:
                    print(f"   ❌ Error obteniendo precio: {e}")
                    
                try:
                    book = client.get_order_book(token_id)
                    print(f"   ✅ Orderbook: {len(book.bids)} bids, {len(book.asks)} asks")
                except Exception as e:
                    print(f"   ❌ Error orderbook: {e}")
        
        # Test: Balance
        print("\n   💰 Verificando balance...")
        try:
            # El balance está en el funder address
            # Usamos la API de datos para verificar
            balance_response = httpx.get(
                f"https://data-api.polymarket.com/value",
                params={"user": funder_address},
                timeout=10
            )
            if balance_response.status_code == 200:
                data = balance_response.json()
                print(f"   ✅ Portfolio value: ${data.get('value', 0):.2f}")
            else:
                print(f"   ⚠️  No se pudo obtener balance: {balance_response.status_code}")
        except Exception as e:
            print(f"   ⚠️  Error balance: {e}")
        
        # Test: Órdenes abiertas
        print("\n   📋 Verificando órdenes abiertas...")
        try:
            orders = client.get_orders()
            print(f"   ✅ Órdenes abiertas: {len(orders)}")
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                print(f"   ❌ Error de autenticación (401)")
                print(f"      Esto puede indicar que las Builder Keys no están")
                print(f"      asociadas correctamente con tu wallet.")
            else:
                print(f"   ❌ Error: {error_msg[:80]}")
        
        return True
        
    except ImportError:
        print("❌ py-clob-client no instalado")
        print("   Ejecuta: pip install py-clob-client")
        return False
    except Exception as e:
        print(f"❌ Error general: {e}")
        return False

def test_alternative():
    """Test alternativo usando create_or_derive_api_creds"""
    print("\n" + "-"*60)
    print("TEST 3: Crear/Derivar API Keys (L1 Auth)")
    print("-"*60)
    
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS", "")
    signature_type = int(os.getenv("SIGNATURE_TYPE", "1"))
    
    try:
        from py_clob_client.client import ClobClient
        
        # Solo con private key (L1)
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=signature_type,
            funder=funder_address,
        )
        
        print("   🔐 Intentando create_or_derive_api_creds()...")
        creds = client.create_or_derive_api_creds()
        
        print(f"   ✅ ¡Credenciales obtenidas!")
        print(f"      API Key: {creds.api_key}")
        print(f"      Secret: ***{creds.api_secret[-8:]}")
        print(f"      Passphrase: ***{creds.api_passphrase[-8:]}")
        
        print("\n   💡 Estas son tus credenciales derivadas de tu wallet.")
        print("      Pueden ser diferentes a las Builder Keys que creaste manualmente.")
        
        # Ahora probar con estas credenciales
        client.set_api_creds(creds)
        
        orders = client.get_orders()
        print(f"\n   ✅ GET /orders funciona: {len(orders)} órdenes")
        
        return creds
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

if __name__ == "__main__":
    market = main()
    test_clob(market)
    
    print("\n" + "="*60)
    derived = test_alternative()
    
    if derived:
        print("\n" + "="*60)
        print("  💡 RECOMENDACIÓN")
        print("="*60)
        print("""
   Las credenciales DERIVADAS de tu private key son diferentes
   a las Builder Keys que creaste manualmente.
   
   Para el bot, deberías usar las credenciales derivadas.
   Actualiza tu .env con:
   """)
        print(f"   API_KEY={derived.api_key}")
        print(f"   SECRET={derived.api_secret}")
        print(f"   PASSPHRASE={derived.api_passphrase}")
    
    print("\n")
