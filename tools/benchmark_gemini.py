"""
Benchmark de modelos Gemini para trading
Compara latencia y calidad de respuesta
"""

import os
import time
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Modelos candidatos para producción
CANDIDATE_MODELS = [
    "gemini-2.5-flash",      # Estable, rápido, buen precio
    "gemini-2.5-pro",        # Más inteligente, más lento
    "gemini-2.0-flash",      # Muy rápido
    "gemini-2.0-flash-lite", # Ultra rápido, menos inteligente
    "gemini-3-flash-preview" # Más nuevo, puede ser inestable
]

# Prompt de trading (el que usaremos en producción)
TRADING_PROMPT = """You are a professional crypto trader analyzing 15-minute BTC flash markets on Polymarket.

RULES:
1. Respond with ONLY one word: UP or DOWN
2. No explanations, no punctuation
3. Base your decision on the provided data

BTC DATA (last 15 minutes):
{data}

YOUR PREDICTION:"""

def benchmark_models():
    """Benchmark de todos los modelos candidatos"""
    
    print("\n" + "="*70)
    print("📊 BENCHMARK DE MODELOS GEMINI PARA TRADING")
    print("="*70)
    
    # Datos de prueba variados
    test_cases = [
        {"price_change": "+2.1%", "volume": "high", "trend": "bullish", "rsi": 65},
        {"price_change": "-1.5%", "volume": "medium", "trend": "bearish", "rsi": 35},
        {"price_change": "+0.3%", "volume": "low", "trend": "sideways", "rsi": 50},
        {"price_change": "-3.2%", "volume": "very_high", "trend": "crash", "rsi": 22},
        {"price_change": "+4.5%", "volume": "extreme", "trend": "pump", "rsi": 78},
    ]
    
    results = {}
    
    for model_name in CANDIDATE_MODELS:
        print(f"\n{'='*70}")
        print(f"🤖 MODELO: {model_name}")
        print("="*70)
        
        try:
            model = genai.GenerativeModel(model_name)
            latencies = []
            responses = []
            errors = 0
            
            for i, data in enumerate(test_cases):
                try:
                    prompt = TRADING_PROMPT.format(data=data)
                    
                    start_time = time.time()
                    response = model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=5,
                            temperature=0
                        )
                    )
                    latency = (time.time() - start_time) * 1000
                    
                    result = response.text.strip().upper()
                    # Normalizar
                    if "UP" in result:
                        result = "UP"
                    elif "DOWN" in result:
                        result = "DOWN"
                    else:
                        result = f"?({result[:10]})"
                    
                    latencies.append(latency)
                    responses.append(result)
                    
                    expected = "UP" if float(data["price_change"].replace("%", "").replace("+", "")) > 0 else "DOWN"
                    match = "✅" if result == expected else "⚠️"
                    
                    print(f"   Test {i+1}: {data['price_change']:>6} → {result:<4} {match} ({latency:.0f}ms)")
                    
                except Exception as e:
                    errors += 1
                    print(f"   Test {i+1}: ❌ Error - {str(e)[:50]}")
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                min_latency = min(latencies)
                max_latency = max(latencies)
                
                # Calcular precisión (asumiendo tendencia = dirección)
                correct = sum(1 for i, r in enumerate(responses) 
                             if (r == "UP" and "+" in test_cases[i]["price_change"]) or
                                (r == "DOWN" and "-" in test_cases[i]["price_change"]))
                accuracy = correct / len(responses) * 100 if responses else 0
                
                results[model_name] = {
                    "avg_latency": avg_latency,
                    "min_latency": min_latency,
                    "max_latency": max_latency,
                    "accuracy": accuracy,
                    "errors": errors
                }
                
                print(f"\n   📈 Resumen:")
                print(f"      Latencia promedio: {avg_latency:.0f}ms")
                print(f"      Latencia mín/máx: {min_latency:.0f}ms / {max_latency:.0f}ms")
                print(f"      Precisión: {accuracy:.0f}%")
                print(f"      Errores: {errors}")
            
        except Exception as e:
            print(f"   ❌ Error inicializando modelo: {e}")
            results[model_name] = {"error": str(e)}
    
    # ===========================================
    # RESUMEN FINAL
    # ===========================================
    print("\n" + "="*70)
    print("📊 RESUMEN COMPARATIVO")
    print("="*70)
    print(f"\n{'Modelo':<30} {'Latencia':<12} {'Precisión':<12} {'Estado'}")
    print("-"*70)
    
    for model_name, data in results.items():
        if "error" in data:
            print(f"{model_name:<30} {'N/A':<12} {'N/A':<12} ❌ Error")
        else:
            latency_str = f"{data['avg_latency']:.0f}ms"
            accuracy_str = f"{data['accuracy']:.0f}%"
            status = "✅" if data['errors'] == 0 else f"⚠️ {data['errors']} err"
            print(f"{model_name:<30} {latency_str:<12} {accuracy_str:<12} {status}")
    
    # Recomendación
    print("\n" + "="*70)
    print("🎯 RECOMENDACIÓN")
    print("="*70)
    
    valid_results = {k: v for k, v in results.items() if "error" not in v and v["errors"] == 0}
    
    if valid_results:
        # Mejor por latencia
        best_latency = min(valid_results.items(), key=lambda x: x[1]["avg_latency"])
        print(f"\n⚡ Más rápido: {best_latency[0]} ({best_latency[1]['avg_latency']:.0f}ms)")
        
        # Mejor por precisión
        best_accuracy = max(valid_results.items(), key=lambda x: x[1]["accuracy"])
        print(f"🎯 Más preciso: {best_accuracy[0]} ({best_accuracy[1]['accuracy']:.0f}%)")
        
        # Balance (latencia < 600ms y mejor precisión)
        balanced = {k: v for k, v in valid_results.items() if v["avg_latency"] < 700}
        if balanced:
            best_balanced = max(balanced.items(), key=lambda x: x[1]["accuracy"])
            print(f"⚖️  Mejor balance: {best_balanced[0]} ({best_balanced[1]['avg_latency']:.0f}ms, {best_balanced[1]['accuracy']:.0f}%)")


if __name__ == "__main__":
    benchmark_models()
