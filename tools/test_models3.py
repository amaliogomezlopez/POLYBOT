import os
import requests
from dotenv import load_dotenv

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_PAT")

def test_premium_models():
    print("\n" + "="*60)
    print("💎 TEST DE MODELOS PREMIUM (HIGH-TIER)")
    print("="*60)

    # Lista de los modelos más potentes (Nombres cortos correctos)
    premium_models = [
        "gpt-4o",                      # OpenAI Flagship
        "Meta-Llama-3.1-405B-Instruct", # Meta Flagship (Massive)
        "Mistral-large-2407",          # Mistral Flagship
        "Cohere-command-r-plus"        # Cohere Flagship
    ]

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    for model_id in premium_models:
        print(f"\n🧪 Probando: {model_id}...", end=" ")
        
        try:
            response = requests.post(
                "https://models.inference.ai.azure.com/chat/completions",
                headers=headers,
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": "You are a financial analyst."},
                        {"role": "user", "content": "Analyze: BTC price 90k. Short answer."}
                    ],
                    "max_tokens": 20
                },
                timeout=15
            )
            
            if response.status_code == 200:
                print("✅ DISPONIBLE")
                print(f"   💬 Respuesta: {response.json()['choices'][0]['message']['content']}")
            else:
                print(f"❌ ERROR ({response.status_code})")
                # A veces el error 429 es común en modelos muy grandes en la capa gratuita
                if response.status_code == 429:
                    print("   ⚠️ Rate Limit excedido (Espera unos minutos)")
                    
        except Exception as e:
            print(f"❌ EXCEPCIÓN: {e}")

if __name__ == "__main__":
    test_premium_models()