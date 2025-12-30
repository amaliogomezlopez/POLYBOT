"""
Test GitHub Models API Access - Version 2
Prueba diferentes endpoints y formatos para GitHub Copilot/Models
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_PAT")

def test_github_models_v2():
    """Prueba el endpoint correcto de GitHub Models para Copilot"""
    
    print("\n" + "="*70)
    print("🔍 TEST GITHUB MODELS - MÚLTIPLES ENDPOINTS")
    print("="*70)
    
    # Diferentes endpoints a probar
    endpoints = [
        # GitHub Models (nuevo)
        {
            "name": "GitHub Models (inference.ai.azure.com)",
            "url": "https://models.inference.ai.azure.com/chat/completions",
            "model": "gpt-4o-mini"
        },
        # GitHub Copilot API (diferente)
        {
            "name": "GitHub API Models",
            "url": "https://api.github.com/models/gpt-4o-mini/chat/completions",
            "model": "gpt-4o-mini"
        },
        # Azure OpenAI style
        {
            "name": "Azure OpenAI Style",
            "url": "https://models.inference.ai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-02-15-preview",
            "model": "gpt-4o-mini"
        }
    ]
    
    for ep in endpoints:
        print(f"\n📡 Probando: {ep['name']}")
        print(f"   URL: {ep['url']}")
        
        try:
            response = requests.post(
                ep["url"],
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28"
                },
                json={
                    "model": ep["model"],
                    "messages": [
                        {"role": "user", "content": "Say UP or DOWN"}
                    ],
                    "max_tokens": 5
                },
                timeout=30
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ SUCCESS: {result}")
                return ep
            else:
                print(f"   ❌ Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
    
    return None


def check_token_permissions():
    """Verifica los permisos del token"""
    print("\n" + "="*70)
    print("🔐 VERIFICANDO PERMISOS DEL TOKEN")
    print("="*70)
    
    response = requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    )
    
    if response.status_code == 200:
        user = response.json()
        print(f"✅ Usuario: {user.get('login')}")
        print(f"   Plan: {user.get('plan', {}).get('name', 'N/A')}")
        
        # Verificar scopes
        scopes = response.headers.get("X-OAuth-Scopes", "No scopes")
        print(f"   Scopes: {scopes}")
        
        return True
    else:
        print(f"❌ Error verificando token: {response.status_code}")
        print(f"   {response.text[:200]}")
        return False


def check_copilot_access():
    """Verifica acceso a Copilot"""
    print("\n" + "="*70)
    print("🤖 VERIFICANDO ACCESO A GITHUB COPILOT")
    print("="*70)
    
    # Verificar si tiene Copilot
    response = requests.get(
        "https://api.github.com/copilot/seats",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
    )
    
    print(f"Copilot Seats Status: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Copilot access confirmed")
    
    # Verificar modelos disponibles vía API GitHub
    response = requests.get(
        "https://api.github.com/marketplace_listing/plans",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
    )
    
    print(f"Marketplace Status: {response.status_code}")


def generate_new_token_instructions():
    """Instrucciones para generar token con permisos correctos"""
    print("\n" + "="*70)
    print("📝 INSTRUCCIONES PARA GENERAR TOKEN CON PERMISOS")
    print("="*70)
    print("""
Para usar GitHub Models necesitas un Personal Access Token con permisos específicos:

1. Ve a: https://github.com/settings/tokens?type=beta
   (Fine-grained personal access tokens)

2. Click "Generate new token"

3. Configura:
   - Name: "polymarket-ai-bot"
   - Expiration: 90 días o más
   - Repository access: "All repositories" o específico
   
4. Permisos requeridos:
   ✅ Copilot (Read) - Para usar Copilot
   ✅ Models (Read and Write) - Para GitHub Models API
   
5. O usa un Classic Token con:
   ✅ copilot
   ✅ read:user
   
Después actualiza GITHUB_PAT en tu .env
""")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 GITHUB MODELS COMPREHENSIVE TEST")
    print("="*70)
    
    # 1. Verificar token
    check_token_permissions()
    
    # 2. Verificar Copilot
    check_copilot_access()
    
    # 3. Probar endpoints
    working_endpoint = test_github_models_v2()
    
    if working_endpoint:
        print(f"\n✅ ENDPOINT FUNCIONAL: {working_endpoint['name']}")
    else:
        print("\n❌ Ningún endpoint funcionó")
        generate_new_token_instructions()
    
    print("\n" + "="*70)
    print("TEST COMPLETADO")
    print("="*70)
