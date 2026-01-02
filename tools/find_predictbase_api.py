#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    PREDICTBASE API DISCOVERY TOOL                            ║
║                                                                              ║
║  Reverse engineers PredictBase.app to find hidden JSON API endpoints.       ║
║  Uses Playwright to intercept network traffic and identify data sources.    ║
║                                                                              ║
║  Usage:                                                                      ║
║    pip install playwright                                                    ║
║    playwright install chromium                                               ║
║    python tools/find_predictbase_api.py                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs
import hashlib

# Try to import playwright
try:
    from playwright.async_api import async_playwright, Request, Response
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not installed. Run: pip install playwright && playwright install chromium")


# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class InterceptedRequest:
    """Captured network request"""
    url: str
    method: str
    headers: Dict[str, str]
    post_data: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc
    
    @property
    def path(self) -> str:
        return urlparse(self.url).path


@dataclass
class InterceptedResponse:
    """Captured network response with body"""
    url: str
    status: int
    headers: Dict[str, str]
    body: Optional[str] = None
    body_json: Optional[Any] = None
    content_type: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_json(self) -> bool:
        return "application/json" in self.content_type or (
            self.body and self.body.strip().startswith(("{", "["))
        )
    
    @property
    def has_market_data(self) -> bool:
        """Check if response contains market/betting data"""
        if not self.body_json:
            return False
        
        # Convert to string for keyword search
        body_str = json.dumps(self.body_json).lower()
        
        # Keywords that indicate market data
        market_keywords = [
            "probability", "odds", "market", "outcome",
            "yes", "no", "price", "volume", "liquidity",
            "polymarket", "prediction", "bet", "wager",
            "question", "event", "contract"
        ]
        
        matches = sum(1 for kw in market_keywords if kw in body_str)
        return matches >= 3  # At least 3 keywords present


# ==============================================================================
# NETWORK INTERCEPTOR
# ==============================================================================

class PredictBaseInterceptor:
    """
    Intercepts and analyzes network traffic from PredictBase.app
    """
    
    TARGET_URL = "https://predictbase.app/"
    
    # Domains to ignore
    IGNORE_DOMAINS = [
        "google", "facebook", "twitter", "analytics",
        "doubleclick", "adsense", "cloudflare", "cdn",
        "fonts.googleapis", "gstatic", "gravatar",
        "hotjar", "mixpanel", "segment", "amplitude",
        "sentry", "bugsnag", "datadog"
    ]
    
    def __init__(self):
        self.requests: List[InterceptedRequest] = []
        self.responses: List[InterceptedResponse] = []
        self.api_candidates: List[Dict[str, Any]] = []
    
    def _should_ignore(self, url: str) -> bool:
        """Check if URL should be ignored"""
        domain = urlparse(url).netloc.lower()
        return any(ignore in domain for ignore in self.IGNORE_DOMAINS)
    
    async def _on_request(self, request: Request):
        """Handle outgoing request"""
        if self._should_ignore(request.url):
            return
        
        # Capture request details
        intercepted = InterceptedRequest(
            url=request.url,
            method=request.method,
            headers=dict(request.headers),
            post_data=request.post_data,
        )
        self.requests.append(intercepted)
    
    async def _on_response(self, response: Response):
        """Handle incoming response"""
        if self._should_ignore(response.url):
            return
        
        # Get content type
        content_type = response.headers.get("content-type", "")
        
        # Only capture JSON and HTML responses
        if not any(ct in content_type for ct in ["json", "html", "text"]):
            return
        
        # Try to get body
        body = None
        body_json = None
        
        try:
            body = await response.text()
            
            # Try to parse as JSON
            if body and body.strip().startswith(("{", "[")):
                try:
                    body_json = json.loads(body)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        
        intercepted = InterceptedResponse(
            url=response.url,
            status=response.status,
            headers=dict(response.headers),
            body=body,
            body_json=body_json,
            content_type=content_type,
        )
        
        self.responses.append(intercepted)
        
        # Check if this is a potential API endpoint
        if intercepted.is_json and intercepted.has_market_data:
            self._add_api_candidate(intercepted)
    
    def _add_api_candidate(self, response: InterceptedResponse):
        """Add a promising API endpoint to candidates"""
        # Find matching request
        matching_request = None
        for req in self.requests:
            if req.url == response.url:
                matching_request = req
                break
        
        # Analyze the data structure
        data_structure = self._analyze_structure(response.body_json)
        
        candidate = {
            "url": response.url,
            "method": matching_request.method if matching_request else "GET",
            "status": response.status,
            "content_type": response.content_type,
            "headers": matching_request.headers if matching_request else {},
            "data_structure": data_structure,
            "sample_data": self._truncate_sample(response.body_json),
            "score": self._calculate_score(response, data_structure),
        }
        
        self.api_candidates.append(candidate)
    
    def _analyze_structure(self, data: Any, depth: int = 0) -> Dict[str, Any]:
        """Analyze JSON data structure"""
        if depth > 3:
            return {"type": "...truncated..."}
        
        if data is None:
            return {"type": "null"}
        elif isinstance(data, bool):
            return {"type": "bool"}
        elif isinstance(data, int):
            return {"type": "int"}
        elif isinstance(data, float):
            return {"type": "float"}
        elif isinstance(data, str):
            return {"type": "string", "sample": data[:50] if len(data) > 50 else data}
        elif isinstance(data, list):
            if not data:
                return {"type": "array", "items": []}
            # Analyze first item
            return {
                "type": "array",
                "length": len(data),
                "items": self._analyze_structure(data[0], depth + 1),
            }
        elif isinstance(data, dict):
            return {
                "type": "object",
                "keys": list(data.keys())[:20],
                "sample_values": {
                    k: self._analyze_structure(v, depth + 1)
                    for k, v in list(data.items())[:10]
                }
            }
        return {"type": str(type(data))}
    
    def _truncate_sample(self, data: Any, max_items: int = 3) -> Any:
        """Truncate sample data for display"""
        if isinstance(data, list):
            return data[:max_items]
        elif isinstance(data, dict):
            return {k: self._truncate_sample(v, max_items) for k, v in list(data.items())[:max_items]}
        return data
    
    def _calculate_score(self, response: InterceptedResponse, structure: Dict) -> int:
        """
        Calculate a score for how likely this is the main data API.
        Higher = more likely to be what we want.
        """
        score = 0
        body_str = json.dumps(response.body_json).lower() if response.body_json else ""
        
        # URL patterns
        url_lower = response.url.lower()
        if "/api/" in url_lower:
            score += 20
        if "market" in url_lower:
            score += 15
        if "data" in url_lower:
            score += 10
        if "graphql" in url_lower:
            score += 10
        
        # Content patterns
        if "polymarket" in body_str:
            score += 30  # Strong indicator!
        if "probability" in body_str:
            score += 15
        if "yes" in body_str and "no" in body_str:
            score += 10
        if "odds" in body_str:
            score += 10
        if "market" in body_str:
            score += 10
        if "question" in body_str:
            score += 10
        
        # Structure patterns
        if structure.get("type") == "array":
            length = structure.get("length", 0)
            if 10 <= length <= 500:  # Reasonable data set size
                score += 15
        
        return score
    
    async def run_discovery(self, timeout: int = 30, scroll: bool = True):
        """
        Run the discovery process.
        
        Args:
            timeout: How long to wait for page to load (seconds)
            scroll: Whether to scroll the page to trigger lazy loading
        """
        print("=" * 70)
        print("        PREDICTBASE API DISCOVERY TOOL")
        print("=" * 70)
        print(f"Target: {self.TARGET_URL}")
        print(f"Timeout: {timeout}s")
        print("=" * 70)
        
        async with async_playwright() as p:
            # Launch browser
            print("\n🚀 Launching headless browser...")
            browser = await p.chromium.launch(headless=True)
            
            # Create context with realistic user agent
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            
            # Create page and attach interceptors
            page = await context.new_page()
            page.on("request", self._on_request)
            page.on("response", self._on_response)
            
            # Navigate to target
            print(f"\n🌐 Navigating to {self.TARGET_URL}...")
            try:
                await page.goto(self.TARGET_URL, wait_until="networkidle", timeout=timeout * 1000)
            except Exception as e:
                print(f"⚠️  Navigation warning: {e}")
            
            # Wait for dynamic content
            print("\n⏳ Waiting for dynamic content...")
            await asyncio.sleep(5)
            
            # Scroll to trigger lazy loading
            if scroll:
                print("\n📜 Scrolling to trigger lazy loading...")
                for i in range(5):
                    await page.evaluate(f"window.scrollTo(0, {(i+1) * 500})")
                    await asyncio.sleep(1)
                
                # Scroll back to top
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(2)
            
            # Click on any "load more" buttons
            print("\n🔍 Looking for 'Load More' buttons...")
            try:
                load_more_selectors = [
                    "button:has-text('Load More')",
                    "button:has-text('Show More')",
                    "button:has-text('View All')",
                    "[class*='load-more']",
                    "[class*='show-more']",
                ]
                for selector in load_more_selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=1000):
                            await btn.click()
                            await asyncio.sleep(2)
                            print(f"   Clicked: {selector}")
                    except:
                        pass
            except:
                pass
            
            # Take screenshot for debugging
            print("\n📸 Taking screenshot...")
            await page.screenshot(path="predictbase_screenshot.png")
            
            # Get page HTML for fallback parsing
            print("\n📄 Extracting HTML...")
            html = await page.content()
            with open("predictbase_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            
            # Close browser
            await browser.close()
        
        # Analyze results
        self._print_results()
        self._save_results()
    
    def _print_results(self):
        """Print discovery results"""
        print("\n" + "=" * 70)
        print("                    DISCOVERY RESULTS")
        print("=" * 70)
        
        # Summary
        print(f"\n📊 SUMMARY:")
        print(f"   Total requests captured: {len(self.requests)}")
        print(f"   Total responses captured: {len(self.responses)}")
        print(f"   API candidates found: {len(self.api_candidates)}")
        
        # JSON responses
        json_responses = [r for r in self.responses if r.is_json]
        print(f"   JSON responses: {len(json_responses)}")
        
        # Sort candidates by score
        self.api_candidates.sort(key=lambda x: x["score"], reverse=True)
        
        if self.api_candidates:
            print("\n" + "=" * 70)
            print("                 🎯 API CANDIDATES (by score)")
            print("=" * 70)
            
            for i, candidate in enumerate(self.api_candidates[:10], 1):
                print(f"\n{'─' * 70}")
                print(f"#{i} | Score: {candidate['score']} | {candidate['method']} {candidate['status']}")
                print(f"{'─' * 70}")
                print(f"URL: {candidate['url']}")
                print(f"Content-Type: {candidate['content_type']}")
                
                # Headers to replicate
                important_headers = ["authorization", "cookie", "x-api-key", "x-auth-token", "x-csrf-token"]
                auth_headers = {k: v for k, v in candidate['headers'].items() 
                              if k.lower() in important_headers}
                if auth_headers:
                    print(f"\n🔐 AUTH HEADERS:")
                    for k, v in auth_headers.items():
                        # Mask sensitive values
                        masked = v[:20] + "..." if len(v) > 20 else v
                        print(f"   {k}: {masked}")
                
                print(f"\n📊 DATA STRUCTURE:")
                print(json.dumps(candidate['data_structure'], indent=2)[:500])
                
                print(f"\n📝 SAMPLE DATA:")
                print(json.dumps(candidate['sample_data'], indent=2, default=str)[:500])
        
        else:
            print("\n⚠️  No API candidates found!")
            print("   PredictBase may use Server-Side Rendering.")
            print("   Checking HTML for embedded data...")
            
            # Check for embedded JSON in HTML
            self._check_html_for_data()
        
        # Print useful headers for all requests
        print("\n" + "=" * 70)
        print("                 📋 COMMON REQUEST HEADERS")
        print("=" * 70)
        
        # Collect all headers
        all_headers: Dict[str, set] = {}
        for req in self.requests:
            for k, v in req.headers.items():
                if k.lower() not in all_headers:
                    all_headers[k.lower()] = set()
                all_headers[k.lower()].add(v)
        
        # Print useful headers
        useful = ["user-agent", "cookie", "authorization", "x-api-key", "accept", "referer"]
        for h in useful:
            if h in all_headers:
                values = list(all_headers[h])[:2]
                for v in values:
                    masked = v[:80] + "..." if len(v) > 80 else v
                    print(f"   {h}: {masked}")
    
    def _check_html_for_data(self):
        """Check HTML for embedded JSON data (Next.js, Nuxt.js patterns)"""
        try:
            with open("predictbase_page.html", "r", encoding="utf-8") as f:
                html = f.read()
            
            # Look for Next.js data
            nextjs_patterns = [
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                r'<script>self\.__next_f\.push\((.*?)\)</script>',
                r'__NUXT__=(.*?)</script>',
                r'window\.__INITIAL_STATE__\s*=\s*(.*?)</script>',
                r'window\.__DATA__\s*=\s*(.*?)</script>',
            ]
            
            for pattern in nextjs_patterns:
                matches = re.findall(pattern, html, re.DOTALL)
                if matches:
                    print(f"\n🔍 Found embedded data pattern!")
                    print(f"   Pattern: {pattern[:50]}...")
                    print(f"   Matches: {len(matches)}")
                    
                    for i, match in enumerate(matches[:2]):
                        try:
                            data = json.loads(match)
                            print(f"\n   Match {i+1} structure:")
                            print(json.dumps(self._analyze_structure(data), indent=2)[:500])
                        except:
                            print(f"   Match {i+1}: (not valid JSON)")
            
            # Look for inline data
            inline_patterns = [
                r'"markets"\s*:\s*\[(.*?)\]',
                r'"predictions"\s*:\s*\[(.*?)\]',
                r'"opportunities"\s*:\s*\[(.*?)\]',
            ]
            
            for pattern in inline_patterns:
                if re.search(pattern, html, re.DOTALL):
                    print(f"\n🔍 Found inline data: {pattern[:40]}...")
                    
        except Exception as e:
            print(f"Error checking HTML: {e}")
    
    def _save_results(self):
        """Save results to JSON file"""
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "target_url": self.TARGET_URL,
            "total_requests": len(self.requests),
            "total_responses": len(self.responses),
            "api_candidates": self.api_candidates,
            "all_json_urls": [r.url for r in self.responses if r.is_json],
        }
        
        with open("predictbase_discovery.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        print("\n" + "=" * 70)
        print("                    📁 FILES SAVED")
        print("=" * 70)
        print("   predictbase_discovery.json  - Full discovery results")
        print("   predictbase_screenshot.png  - Page screenshot")
        print("   predictbase_page.html       - Full HTML source")


# ==============================================================================
# ALTERNATIVE: Direct HTTP Probe
# ==============================================================================

async def probe_common_endpoints():
    """
    Probe common API endpoint patterns without browser.
    Useful if Playwright can't be installed on VPS.
    """
    import aiohttp
    
    print("\n" + "=" * 70)
    print("          DIRECT API PROBE (No Browser)")
    print("=" * 70)
    
    base_url = "https://predictbase.app"
    
    # Common API patterns to try
    endpoints = [
        "/api/markets",
        "/api/opportunities",
        "/api/predictions",
        "/api/data",
        "/api/v1/markets",
        "/api/v1/opportunities",
        "/_next/data/*/index.json",
        "/markets.json",
        "/data.json",
        "/graphql",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": base_url,
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    status = resp.status
                    content_type = resp.headers.get("content-type", "")
                    
                    if status == 200 and "json" in content_type:
                        body = await resp.text()
                        print(f"\n✓ {url}")
                        print(f"  Status: {status}")
                        print(f"  Type: {content_type}")
                        print(f"  Body preview: {body[:200]}...")
                    else:
                        print(f"✗ {url} ({status})")
                        
            except Exception as e:
                print(f"✗ {url} (Error: {type(e).__name__})")


# ==============================================================================
# MAIN
# ==============================================================================

async def main():
    """Run discovery"""
    if PLAYWRIGHT_AVAILABLE:
        interceptor = PredictBaseInterceptor()
        await interceptor.run_discovery(timeout=30)
    else:
        print("Playwright not available, trying direct probe...")
    
    # Also try direct probe
    await probe_common_endpoints()
    
    print("\n" + "=" * 70)
    print("                    NEXT STEPS")
    print("=" * 70)
    print("""
1. Review predictbase_discovery.json for API candidates
2. Look for the highest-scoring endpoint
3. Copy the URL and headers to src/exchanges/predictbase_client.py
4. If no JSON API found, use the HTML parser fallback
    """)


if __name__ == "__main__":
    asyncio.run(main())
