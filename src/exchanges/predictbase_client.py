"""
🔄 PREDICTBASE CLIENT
======================
Client for fetching market data from PredictBase for cross-exchange arbitrage.

Features:
- REST API discovery (if available)
- Fallback web scraper
- Market matching with Polymarket
- Caching to reduce requests
- Robust error handling

Note: PredictBase may change their structure. This client is designed
to fail gracefully and log issues for debugging.
"""

import asyncio
import httpx
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from bs4 import BeautifulSoup
import json

logger = logging.getLogger(__name__)

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PredictBaseMarket:
    """Market data from PredictBase."""
    market_id: str
    question: str
    url: str
    yes_price: float = 0.0
    no_price: float = 0.0
    volume: float = 0.0
    end_date: Optional[datetime] = None
    category: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def mid_price(self) -> float:
        return (self.yes_price + self.no_price) / 2 if self.yes_price and self.no_price else 0

# =============================================================================
# PREDICTBASE CLIENT
# =============================================================================

class PredictBaseClient:
    """
    Client for PredictBase market data.
    
    Attempts API discovery first, falls back to scraping.
    Implements caching to minimize requests.
    """
    
    BASE_URL = "https://predictbase.com"
    API_ENDPOINTS = [
        "/api/markets",
        "/api/v1/markets", 
        "/api/public/markets",
    ]
    
    # Cache TTL in seconds
    CACHE_TTL = 300  # 5 minutes
    
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple] = {}  # {key: (data, timestamp)}
        self._api_endpoint: Optional[str] = None
        self._use_scraper = False
        
        # User agent to avoid blocks
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html",
            "Accept-Language": "en-US,en;q=0.9",
        }
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True
        )
        await self._discover_api()
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    # -------------------------------------------------------------------------
    # API DISCOVERY
    # -------------------------------------------------------------------------
    
    async def _discover_api(self):
        """Try to discover a working API endpoint."""
        logger.info("🔍 Discovering PredictBase API...")
        
        for endpoint in self.API_ENDPOINTS:
            try:
                url = f"{self.BASE_URL}{endpoint}"
                resp = await self._client.get(url)
                
                if resp.status_code == 200:
                    # Check if it's JSON
                    try:
                        data = resp.json()
                        if isinstance(data, (list, dict)):
                            self._api_endpoint = endpoint
                            self._use_scraper = False
                            logger.info(f"✅ Found API endpoint: {endpoint}")
                            return
                    except:
                        pass
            except Exception as e:
                logger.debug(f"API endpoint {endpoint} failed: {e}")
        
        # No API found, use scraper
        self._use_scraper = True
        logger.warning("⚠️ No API found, using web scraper")
    
    # -------------------------------------------------------------------------
    # MARKET FETCHING
    # -------------------------------------------------------------------------
    
    async def get_markets(self, limit: int = 100) -> List[PredictBaseMarket]:
        """
        Fetch markets from PredictBase.
        
        Args:
            limit: Maximum markets to fetch
        
        Returns:
            List of PredictBaseMarket objects
        """
        cache_key = f"markets_{limit}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            if self._use_scraper:
                markets = await self._scrape_markets(limit)
            else:
                markets = await self._fetch_api_markets(limit)
            
            self._set_cached(cache_key, markets)
            return markets
            
        except Exception as e:
            logger.error(f"Failed to fetch PredictBase markets: {e}")
            return []
    
    async def _fetch_api_markets(self, limit: int) -> List[PredictBaseMarket]:
        """Fetch markets from API endpoint."""
        if not self._api_endpoint:
            return []
        
        url = f"{self.BASE_URL}{self._api_endpoint}"
        params = {"limit": limit, "status": "active"}
        
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            markets = []
            items = data if isinstance(data, list) else data.get("markets", data.get("data", []))
            
            for item in items[:limit]:
                market = self._parse_api_market(item)
                if market:
                    markets.append(market)
            
            logger.info(f"📥 Fetched {len(markets)} markets from PredictBase API")
            return markets
            
        except Exception as e:
            logger.error(f"API fetch error: {e}")
            # Fallback to scraper
            self._use_scraper = True
            return await self._scrape_markets(limit)
    
    def _parse_api_market(self, item: dict) -> Optional[PredictBaseMarket]:
        """Parse API response into PredictBaseMarket."""
        try:
            # Try common field names
            market_id = item.get("id") or item.get("market_id") or item.get("slug", "")
            question = item.get("question") or item.get("title") or item.get("name", "")
            
            # Prices might be in different formats
            yes_price = 0.0
            no_price = 0.0
            
            if "outcomes" in item:
                for outcome in item["outcomes"]:
                    if outcome.get("name", "").lower() == "yes":
                        yes_price = float(outcome.get("price", 0))
                    elif outcome.get("name", "").lower() == "no":
                        no_price = float(outcome.get("price", 0))
            else:
                yes_price = float(item.get("yes_price", item.get("yesPrice", 0)))
                no_price = float(item.get("no_price", item.get("noPrice", 0)))
            
            # Normalize prices (might be percentage or decimal)
            if yes_price > 1:
                yes_price /= 100
            if no_price > 1:
                no_price /= 100
            
            return PredictBaseMarket(
                market_id=str(market_id),
                question=question,
                url=f"{self.BASE_URL}/market/{market_id}",
                yes_price=yes_price,
                no_price=no_price,
                volume=float(item.get("volume", 0)),
                category=item.get("category", ""),
                raw_data=item
            )
        except Exception as e:
            logger.debug(f"Failed to parse market: {e}")
            return None
    
    # -------------------------------------------------------------------------
    # WEB SCRAPER (FALLBACK)
    # -------------------------------------------------------------------------
    
    async def _scrape_markets(self, limit: int) -> List[PredictBaseMarket]:
        """
        Scrape markets from PredictBase website.
        
        This is a fallback when no API is available.
        May break if website structure changes.
        """
        markets = []
        
        # Try different pages
        pages_to_try = [
            "/markets",
            "/explore",
            "/",
            "/trending"
        ]
        
        for page in pages_to_try:
            try:
                url = f"{self.BASE_URL}{page}"
                resp = await self._client.get(url)
                
                if resp.status_code != 200:
                    continue
                
                html = resp.text
                soup = BeautifulSoup(html, 'html.parser')
                
                # Try to find markets in the page
                found_markets = self._extract_markets_from_html(soup, url)
                
                if found_markets:
                    markets.extend(found_markets)
                    logger.info(f"📥 Scraped {len(found_markets)} markets from {page}")
                
                if len(markets) >= limit:
                    break
                    
            except Exception as e:
                logger.debug(f"Scrape error on {page}: {e}")
        
        # Also try to find embedded JSON data
        try:
            json_markets = await self._extract_embedded_json()
            if json_markets:
                markets.extend(json_markets)
        except:
            pass
        
        return markets[:limit]
    
    def _extract_markets_from_html(self, soup: BeautifulSoup, base_url: str) -> List[PredictBaseMarket]:
        """Extract market data from HTML."""
        markets = []
        
        # Common selectors for market cards
        selectors = [
            'div[class*="market"]',
            'a[class*="market"]',
            'div[class*="card"]',
            'article',
            '[data-market-id]',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            
            for elem in elements:
                try:
                    market = self._parse_market_element(elem, base_url)
                    if market and market.question:
                        markets.append(market)
                except:
                    pass
        
        return markets
    
    def _parse_market_element(self, elem, base_url: str) -> Optional[PredictBaseMarket]:
        """Parse a market element from HTML."""
        # Try to extract question
        question = ""
        for tag in ['h2', 'h3', 'h4', 'p', 'span', 'a']:
            title_elem = elem.find(tag)
            if title_elem and len(title_elem.text.strip()) > 10:
                question = title_elem.text.strip()
                break
        
        if not question:
            return None
        
        # Try to extract prices
        yes_price = 0.0
        no_price = 0.0
        
        # Look for price patterns
        text = elem.get_text()
        price_patterns = [
            r'Yes[:\s]+\$?(\d+\.?\d*)[%¢]?',
            r'(\d+\.?\d*)[%¢]?\s*Yes',
            r'YES[:\s]+(\d+\.?\d*)',
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price = float(match.group(1))
                yes_price = price / 100 if price > 1 else price
                break
        
        # Try to get URL
        url = base_url
        link = elem.find('a', href=True)
        if link:
            href = link['href']
            if href.startswith('/'):
                url = f"{self.BASE_URL}{href}"
            elif href.startswith('http'):
                url = href
        
        # Generate ID from question
        market_id = re.sub(r'[^a-z0-9]', '-', question.lower())[:50]
        
        return PredictBaseMarket(
            market_id=market_id,
            question=question,
            url=url,
            yes_price=yes_price,
            no_price=1 - yes_price if yes_price > 0 else 0,
        )
    
    async def _extract_embedded_json(self) -> List[PredictBaseMarket]:
        """Try to find embedded JSON data in the page (Next.js, etc.)."""
        markets = []
        
        try:
            resp = await self._client.get(self.BASE_URL)
            html = resp.text
            
            # Look for __NEXT_DATA__ or similar
            patterns = [
                r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>',
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.markets\s*=\s*(\[.+?\]);',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        # Navigate to markets data
                        if isinstance(data, dict):
                            markets_data = (
                                data.get("props", {}).get("pageProps", {}).get("markets") or
                                data.get("markets") or
                                data.get("data", {}).get("markets") or
                                []
                            )
                            for item in markets_data:
                                market = self._parse_api_market(item)
                                if market:
                                    markets.append(market)
                    except:
                        pass
        except:
            pass
        
        return markets
    
    # -------------------------------------------------------------------------
    # CACHING
    # -------------------------------------------------------------------------
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached data if not expired."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.utcnow() - timestamp < timedelta(seconds=self.CACHE_TTL):
                return data
        return None
    
    def _set_cached(self, key: str, data: Any):
        """Set cache data."""
        self._cache[key] = (data, datetime.utcnow())
    
    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
    
    # -------------------------------------------------------------------------
    # UTILITY
    # -------------------------------------------------------------------------
    
    async def get_market_by_question(self, question: str, threshold: float = 0.8) -> Optional[PredictBaseMarket]:
        """
        Find a market by question using fuzzy matching.
        
        Args:
            question: Question to search for
            threshold: Minimum similarity (0-1)
        
        Returns:
            Best matching market or None
        """
        try:
            from thefuzz import fuzz
        except ImportError:
            logger.warning("thefuzz not installed, using basic matching")
            return await self._basic_match(question)
        
        markets = await self.get_markets(limit=200)
        
        best_match = None
        best_score = 0
        
        for market in markets:
            score = fuzz.ratio(question.lower(), market.question.lower()) / 100
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = market
        
        if best_match:
            logger.debug(f"Matched '{question[:50]}' to '{best_match.question[:50]}' (score={best_score:.0%})")
        
        return best_match
    
    async def _basic_match(self, question: str) -> Optional[PredictBaseMarket]:
        """Basic string matching fallback."""
        markets = await self.get_markets(limit=200)
        question_words = set(question.lower().split())
        
        best_match = None
        best_overlap = 0
        
        for market in markets:
            market_words = set(market.question.lower().split())
            overlap = len(question_words & market_words) / max(len(question_words), 1)
            
            if overlap > best_overlap and overlap >= 0.5:
                best_overlap = overlap
                best_match = market
        
        return best_match


# =============================================================================
# TESTING
# =============================================================================

async def test_client():
    """Test the PredictBase client."""
    print("🧪 Testing PredictBase Client...")
    
    async with PredictBaseClient() as client:
        print(f"   Using scraper: {client._use_scraper}")
        
        markets = await client.get_markets(limit=10)
        print(f"   Found {len(markets)} markets")
        
        for m in markets[:5]:
            print(f"   - {m.question[:60]}...")
            print(f"     Yes: ${m.yes_price:.2f}, No: ${m.no_price:.2f}")

if __name__ == "__main__":
    asyncio.run(test_client())
