"""
Script to capture Polymarket account activity via network interception.
"""
import asyncio
import csv
import json
import os
import random
from typing import Any, List, Dict
from playwright.async_api import async_playwright, Response

OUTPUT_DIR = "analysis"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "activity_data.json")
CSV_FILE = os.path.join(OUTPUT_DIR, "activity_data.csv")
TARGET_URL = "https://polymarket.com/@Account88888?via=888&tab=activity"

captured_data: List[Dict[str, Any]] = []

async def handle_response(response: Response):
    """Intercept and process network responses."""
    # Filter for likely API endpoints containing activity/trade data
    # Common endpoints: /activity, /trades, /positions, /portfolio
    # We look for JSON responses
    
    url = response.url.lower()
    
    # Check for relevant API calls
    if "activity" in url or "trades" in url or "positions" in url or "portfolio" in url:
        try:
            # Only process JSON responses
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return

            json_data = await response.json()
            
            # Simple heuristic: look for list structures with trade-like keys
            if isinstance(json_data, list) and len(json_data) > 0:
                sample = json_data[0]
                if isinstance(sample, dict) and any(k in sample for k in ["side", "size", "price", "asset", "id"]):
                    print(f"Captured data from: {url}")
                    captured_data.extend(json_data)
            elif isinstance(json_data, dict):
                # Handle paginated responses like {"data": [...], "next_cursor": ...}
                for key in ["data", "results", "trades", "activity"]:
                    if key in json_data and isinstance(json_data[key], list):
                        print(f"Captured data from: {url} (key: {key})")
                        captured_data.extend(json_data[key])
                        
        except Exception as e:
            # Ignore errors parsing non-JSON or other failures
            pass

async def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    async with async_playwright() as p:
        # Launch browser (headless=False to see what's happening if needed, strict stealth mode)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        # Subscribe to network events
        page.on("response", handle_response)
        
        print(f"Navigating to {TARGET_URL}...")
        await page.goto(TARGET_URL, wait_until="networkidle")
        
        # Wait specifically for the 'Activity' tab or button to be visible and click it
        # The user image shows "Activity" as a text tab.
        try:
            # Try to find the Activity tab by text
            activity_tab = page.get_by_text("Activity", exact=True)
            if await activity_tab.is_visible():
                print("Clicking 'Activity' tab...")
                await activity_tab.click()
                # Wait for potential network requests to trigger
                await page.wait_for_timeout(5000) 
            else:
                print("'Activity' tab not found immediately. Looking for buttons...")
                # Fallback selectors
                await page.click("button:has-text('Activity')")
                await page.wait_for_timeout(5000)
                
            # Scroll down to trigger lazy loading if applicable
            for _ in range(3):
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(1000)
                
        except Exception as e:
            print(f"Interaction error: {e}")

        # Save captured data
        print(f"Total records captured: {len(captured_data)}")
        
        if captured_data:
            # Save raw JSON
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(captured_data, f, indent=2)
                
            # Convert to CSV (flattening somewhat)
            # Find all potential keys
            keys = set()
            for item in captured_data:
                keys.update(item.keys())
            
            with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(keys))
                writer.writeheader()
                for item in captured_data:
                    # Handle nested objects loosely by conversion to string if needed
                    row = {}
                    for k, v in item.items():
                        if isinstance(v, (dict, list)):
                            row[k] = json.dumps(v)
                        else:
                            row[k] = v
                    writer.writerow(row)
            
            print(f"Data saved to {CSV_FILE}")
        else:
            print("No relevant activity data captured.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
