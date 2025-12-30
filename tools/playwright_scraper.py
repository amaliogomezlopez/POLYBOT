#!/usr/bin/env python3
"""
Scraper Profesional de Polymarket usando Playwright
Captura todas las peticiones XHR/fetch de la actividad de @Account88888
Con técnicas anti-detección y scroll infinito
"""

import os
import sys
import json
import time
import random
import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page, Response

# Configuración
TARGET_URL = "https://polymarket.com/@Account88888?tab=activity"
OUTPUT_DIR = Path("analysis")
OUTPUT_FILE = OUTPUT_DIR / "account88888_playwright_data.json"
ACTIVITY_FILE = OUTPUT_DIR / "account88888_activity_full.json"

# Datos capturados
captured_data = {
    "profile": None,
    "activity": [],
    "positions": [],
    "trades": [],
    "raw_responses": [],
    "request_urls": [],
}

# Set para evitar duplicados
seen_activities = set()

async def random_delay(min_sec=0.5, max_sec=2.0):
    """Delay aleatorio para simular comportamiento humano"""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def handle_response(response: Response):
    """Capturar respuestas de las peticiones"""
    try:
        url = response.url
        
        # Filtrar solo peticiones relevantes
        if any(x in url for x in [
            "gamma-api.polymarket",
            "clob.polymarket",
            "/api/",
            "graphql",
            "activity",
            "positions",
            "trades",
            "profile",
            "user",
        ]):
            captured_data["request_urls"].append(url)
            
            # Intentar obtener el JSON de la respuesta
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    data = await response.json()
                    
                    # Clasificar datos
                    if "activity" in url.lower():
                        if isinstance(data, list):
                            for item in data:
                                item_id = str(item.get("id", "") or item.get("transactionHash", "") or json.dumps(item)[:100])
                                if item_id not in seen_activities:
                                    seen_activities.add(item_id)
                                    captured_data["activity"].append(item)
                        print(f"   📊 Activity: {len(captured_data['activity'])} items")
                        
                    elif "position" in url.lower():
                        if isinstance(data, list):
                            captured_data["positions"].extend(data)
                        print(f"   📈 Positions: {len(captured_data['positions'])} items")
                        
                    elif "trade" in url.lower():
                        if isinstance(data, list):
                            captured_data["trades"].extend(data)
                        print(f"   💹 Trades: {len(captured_data['trades'])} items")
                        
                    elif "profile" in url.lower() or "user" in url.lower():
                        captured_data["profile"] = data
                        print(f"   👤 Profile data captured")
                    
                    # Guardar respuesta raw
                    captured_data["raw_responses"].append({
                        "url": url,
                        "status": response.status,
                        "data": data,
                        "timestamp": datetime.now().isoformat(),
                    })
                    
            except Exception as e:
                pass  # Algunas respuestas no son JSON
                
    except Exception as e:
        pass

async def human_like_scroll(page: Page, scroll_count: int = 50):
    """Scroll que simula comportamiento humano"""
    
    print(f"\n🖱️ Iniciando scroll ({scroll_count} iteraciones)...")
    
    last_activity_count = 0
    no_new_data_count = 0
    
    for i in range(scroll_count):
        # Scroll con variación
        scroll_amount = random.randint(500, 1000)
        
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        
        # Delay variable para parecer humano
        await random_delay(1.0, 3.0)
        
        # Verificar si hay nuevos datos
        current_count = len(captured_data["activity"])
        if current_count > last_activity_count:
            print(f"   Scroll {i+1}/{scroll_count}: {current_count} actividades")
            last_activity_count = current_count
            no_new_data_count = 0
        else:
            no_new_data_count += 1
            print(f"   Scroll {i+1}/{scroll_count}: sin nuevos datos ({no_new_data_count})")
        
        # Si no hay nuevos datos después de varios scrolls, probablemente llegamos al final
        if no_new_data_count >= 5:
            print(f"   ⚠️ Sin nuevos datos después de {no_new_data_count} scrolls, esperando más...")
            await random_delay(3.0, 5.0)
            
            # Scroll extra para asegurarnos
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await random_delay(2.0, 4.0)
            
            if no_new_data_count >= 10:
                print(f"   ✅ Parece que llegamos al final de la actividad")
                break
        
        # Ocasionalmente hacer pequeño scroll hacia arriba (comportamiento humano)
        if random.random() < 0.1:
            await page.evaluate(f"window.scrollBy(0, -{random.randint(100, 200)})")
            await random_delay(0.5, 1.0)

async def scrape_account():
    """Scraper principal"""
    
    print("\n" + "="*70)
    print("🔍 SCRAPER PROFESIONAL DE POLYMARKET")
    print("="*70)
    print(f"Target: {TARGET_URL}")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with async_playwright() as p:
        # Configurar navegador con opciones anti-detección
        browser = await p.chromium.launch(
            headless=False,  # Visible para debugging (cambiar a True para producción)
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
            ]
        )
        
        # Crear contexto con configuración realista
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        
        # Añadir scripts para evadir detección
        await context.add_init_script("""
            // Override webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        page = await context.new_page()
        
        # Interceptar respuestas
        page.on("response", handle_response)
        
        print("\n📡 Navegando a la página...")
        
        try:
            # Navegar a la página
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            print("   ✅ Página cargada")
            
            # Esperar a que cargue el contenido
            await random_delay(3.0, 5.0)
            
            # Verificar que estamos en la pestaña de actividad
            try:
                # Intentar hacer clic en la pestaña de actividad si existe
                activity_tab = page.locator('text="Activity"').first
                if await activity_tab.is_visible():
                    await activity_tab.click()
                    await random_delay(2.0, 3.0)
                    print("   ✅ Tab de Activity clickeado")
            except:
                print("   ℹ️ Ya estamos en la pestaña de actividad")
            
            # Esperar a que cargue la actividad inicial
            await random_delay(2.0, 4.0)
            
            # Realizar scroll para cargar más datos
            await human_like_scroll(page, scroll_count=100)  # Muchos scrolls para obtener todo
            
            # Scroll final al fondo
            print("\n🔄 Scroll final para asegurar todos los datos...")
            for _ in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await random_delay(2.0, 4.0)
            
        except Exception as e:
            print(f"❌ Error durante navegación: {e}")
        
        finally:
            # Guardar datos antes de cerrar
            print("\n💾 Guardando datos capturados...")
            
            OUTPUT_DIR.mkdir(exist_ok=True)
            
            # Guardar todo
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(captured_data, f, indent=2, default=str)
            
            # Guardar solo actividad limpia
            with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
                json.dump(captured_data["activity"], f, indent=2, default=str)
            
            print(f"   ✅ Datos guardados en {OUTPUT_FILE}")
            print(f"   ✅ Actividad guardada en {ACTIVITY_FILE}")
            
            # Estadísticas
            print("\n" + "="*70)
            print("📊 ESTADÍSTICAS FINALES")
            print("="*70)
            print(f"   Actividades capturadas: {len(captured_data['activity'])}")
            print(f"   Posiciones capturadas: {len(captured_data['positions'])}")
            print(f"   Trades capturados: {len(captured_data['trades'])}")
            print(f"   Respuestas totales: {len(captured_data['raw_responses'])}")
            print(f"   URLs interceptadas: {len(captured_data['request_urls'])}")
            
            # Mostrar algunas URLs capturadas
            unique_base_urls = set()
            for url in captured_data["request_urls"]:
                base = url.split("?")[0]
                unique_base_urls.add(base)
            
            print(f"\n📡 URLs base únicas interceptadas:")
            for url in list(unique_base_urls)[:20]:
                print(f"   - {url}")
            
            await browser.close()
    
    return captured_data

def main():
    """Punto de entrada"""
    asyncio.run(scrape_account())

if __name__ == "__main__":
    main()
