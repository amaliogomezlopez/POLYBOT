"""
Test GitHub Models API Access
Verifica qué modelos están disponibles con tu suscripción de GitHub Copilot
"""

import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_PAT")

def list_available_models():
    """Lista todos los modelos disponibles en GitHub Models"""
    print("\n" + "="*60)
    print("🔍 LISTANDO MODELOS DISPONIBLES EN GITHUB MODELS")
    print("="*60)
    
    if not GITHUB_TOKEN:
        print("❌ ERROR: GITHUB_PAT no encontrado en .env")
        return []
    
    print(f"✅ Token encontrado: {GITHUB_TOKEN[:20]}...")
    
    try:
        response = requests.get(
            "https://models.inference.ai.azure.com/models",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        print(f"\n📡 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            models = data if isinstance(data, list) else data.get("data", data.get("models", []))
            
            print(f"\n✅ MODELOS DISPONIBLES ({len(models)}):")
            print("-"*60)
            
            model_ids = []
            for m in models:
                if isinstance(m, dict):
                    model_id = m.get("id") or m.get("name") or m.get("model")
                    model_ids.append(model_id)
                    owned_by = m.get("owned_by", m.get("publisher", "unknown"))
                    print(f"  • {model_id:<40} ({owned_by})")
                else:
                    model_ids.append(str(m))
                    print(f"  • {m}")
            
            return model_ids
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return []
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return []


def test_model_inference(model: str = "gpt-4o-mini"):
    """Prueba una inferencia simple con un modelo"""
    print("\n" + "="*60)
    print(f"🧪 PROBANDO INFERENCIA CON: {model}")
    print("="*60)
    
    if not GITHUB_TOKEN:
        print("❌ ERROR: GITHUB_PAT no encontrado")
        return None
    
    try:
        response = requests.post(
            "https://models.inference.ai.azure.com/chat/completions",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a crypto trader. Respond only: UP or DOWN"},
                    {"role": "user", "content": "BTC price increased 2% in last 15 min. Direction?"}
                ],
                "max_tokens": 10,
                "temperature": 0
            },
            timeout=30
        )
        
        print(f"📡 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            
            print(f"✅ Respuesta: {content}")
            print(f"📊 Tokens usados: {usage.get('total_tokens', 'N/A')}")
            return content
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return None
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None


def test_market_bias(btc_data: dict, model: str = "gpt-4o-mini") -> str:
    """
    Obtiene sesgo del mercado usando GitHub Models.
    Esta es la función que usaremos en producción.
    """
    print("\n" + "="*60)
    print(f"📈 TEST: ANÁLISIS DE SESGO DE MERCADO")
    print("="*60)
    print(f"📊 Datos BTC: {btc_data}")
    print(f"🤖 Modelo: {model}")
    
    try:
        response = requests.post(
            "https://models.inference.ai.azure.com/chat/completions",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "model": model, 
                "messages": [
                    {
                        "role": "system", 
                        "content": """You are a professional crypto trader analyzing 15-minute BTC flash markets.
Based on the data provided, predict the direction for the next 15 minutes.
Respond with ONLY one word: UP or DOWN
No explanations, no punctuation, just UP or DOWN."""
                    },
                    {
                        "role": "user", 
                        "content": f"BTC data for last 15 minutes: {btc_data}. What's your prediction?"
                    }
                ],
                "max_tokens": 5,
                "temperature": 0
            },
            timeout=30
        )
        
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip().upper()
        
        # Normalizar respuesta
        if "UP" in content:
            bias = "UP"
        elif "DOWN" in content:
            bias = "DOWN"
        else:
            bias = content
        
        print(f"\n✅ SESGO PREDICHO: {bias}")
        return bias
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            print("⚠️ Rate Limit alcanzado")
            return "RATE_LIMIT"
        print(f"❌ HTTP Error: {e}")
        return "ERROR"
    except Exception as e:
        print(f"❌ Exception: {e}")
        return "ERROR"


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 GITHUB MODELS API TEST")
    print("="*60)
    
    # 1. Listar modelos disponibles
    models = list_available_models()
    
    # 2. Probar inferencia básica
    if models:
        # Probar con diferentes modelos
        test_models = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"]
        
        for model in test_models:
            if model in models or True:  # Probar aunque no esté en lista
                result = test_model_inference(model)
                if result:
                    break
    else:
        # Probar directamente aunque no tengamos lista
        print("\n⚠️ No se pudo listar modelos, probando directamente...")
        test_model_inference("gpt-4o-mini")
    
    # 3. Test de análisis de mercado
    test_data = {
        "price_change": "+1.8%",
        "volume": "high",
        "trend": "bullish",
        "last_candle": "green"
    }
    test_market_bias(test_data)
    
    print("\n" + "="*60)
    print("✅ TEST COMPLETADO")
    print("="*60)
