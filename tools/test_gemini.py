"""
Test Google Gemini API Access
Verifica modelos disponibles y prueba inferencia
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def test_gemini():
    """Prueba completa de Gemini API"""
    
    print("\n" + "="*70)
    print("🚀 GOOGLE GEMINI API TEST")
    print("="*70)
    
    if not GEMINI_API_KEY:
        print("❌ ERROR: GEMINI_API_KEY no encontrada en .env")
        return
    
    print(f"✅ API Key encontrada: {GEMINI_API_KEY[:20]}...")
    
    # Importar después de verificar key
    import google.generativeai as genai
    
    # Configurar API
    genai.configure(api_key=GEMINI_API_KEY)
    
    # ===========================================
    # 1. LISTAR MODELOS DISPONIBLES
    # ===========================================
    print("\n" + "="*70)
    print("📋 MODELOS DISPONIBLES EN GEMINI")
    print("="*70)
    
    try:
        models = genai.list_models()
        
        print("\n✅ Modelos que soportan generateContent:")
        print("-"*70)
        
        available_models = []
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                available_models.append(model.name)
                print(f"  • {model.name}")
                print(f"    - Display: {model.display_name}")
                print(f"    - Input limit: {model.input_token_limit:,} tokens")
                print(f"    - Output limit: {model.output_token_limit:,} tokens")
                print()
        
        print(f"\n📊 Total modelos disponibles: {len(available_models)}")
        
    except Exception as e:
        print(f"❌ Error listando modelos: {e}")
        return
    
    # ===========================================
    # 2. TEST DE INFERENCIA BÁSICA
    # ===========================================
    print("\n" + "="*70)
    print("🧪 TEST DE INFERENCIA")
    print("="*70)
    
    # Probar con Gemini Flash (más rápido y económico)
    test_models = ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
    
    for model_name in test_models:
        print(f"\n📡 Probando: {model_name}")
        
        try:
            model = genai.GenerativeModel(model_name)
            
            start_time = time.time()
            response = model.generate_content(
                "Say only UP or DOWN, nothing else",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=10,
                    temperature=0
                )
            )
            latency = (time.time() - start_time) * 1000
            
            result = response.text.strip()
            print(f"   ✅ Respuesta: {result}")
            print(f"   ⏱️  Latencia: {latency:.0f}ms")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # ===========================================
    # 3. TEST DE ANÁLISIS DE MERCADO
    # ===========================================
    print("\n" + "="*70)
    print("📈 TEST: ANÁLISIS DE SESGO DE MERCADO")
    print("="*70)
    
    test_data = {
        "price_change": "+1.8%",
        "volume": "high", 
        "trend": "bullish",
        "last_candle": "green"
    }
    
    print(f"📊 Datos BTC: {test_data}")
    
    try:
        # Usar Gemini Flash para baja latencia
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        
        prompt = f"""You are a professional crypto trader analyzing 15-minute BTC flash markets.
Based on the data provided, predict the direction for the next 15 minutes.
Respond with ONLY one word: UP or DOWN
No explanations, no punctuation, just UP or DOWN.

BTC data for last 15 minutes: {test_data}
What's your prediction?"""

        start_time = time.time()
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=5,
                temperature=0
            )
        )
        latency = (time.time() - start_time) * 1000
        
        bias = response.text.strip().upper()
        if "UP" in bias:
            bias = "UP"
        elif "DOWN" in bias:
            bias = "DOWN"
        
        print(f"\n✅ SESGO PREDICHO: {bias}")
        print(f"⏱️  Latencia: {latency:.0f}ms")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # ===========================================
    # 4. TEST DE MÚLTIPLES LLAMADAS (Latencia)
    # ===========================================
    print("\n" + "="*70)
    print("⚡ TEST DE LATENCIA (5 llamadas)")
    print("="*70)
    
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        latencies = []
        
        for i in range(5):
            start_time = time.time()
            response = model.generate_content(
                "UP or DOWN?",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=5,
                    temperature=0
                )
            )
            latency = (time.time() - start_time) * 1000
            latencies.append(latency)
            print(f"   Call {i+1}: {latency:.0f}ms - {response.text.strip()}")
        
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        
        print(f"\n📊 Estadísticas de Latencia:")
        print(f"   Promedio: {avg_latency:.0f}ms")
        print(f"   Mínimo: {min_latency:.0f}ms")
        print(f"   Máximo: {max_latency:.0f}ms")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*70)
    print("✅ TEST COMPLETADO")
    print("="*70)


if __name__ == "__main__":
    test_gemini()
