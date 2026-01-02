"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                       PREDICTBASE API CLIENT                                 ║
║                                                                              ║
║  Client for PredictBase.app - a prediction market on Base chain.             ║
║                                                                              ║
║  IMPORTANT: PredictBase is NOT a Polymarket aggregator!                      ║
║  It's a separate prediction market platform. ARB opportunities exist         ║
║  when similar markets exist on both platforms with different prices.         ║
║                                                                              ║
║  Features:                                                                   ║
║    - REST API client for PredictBase markets                                 ║
║    - Market matching with Polymarket (fuzzy question matching)               ║
║    - Circuit breaker for fault tolerance                                     ║
║    - Caching to reduce requests                                              ║
║                                                                              ║
║  Discovered API endpoints:                                                   ║
║    - /api/get_recent_markets_v2   (newest markets, may have 0 volume)        ║
║    - /api/get_resolved_markets_v2 (historical data with prices)              ║
║                                                                              ║
║  Data format:                                                                ║
║    - optionPrices in micro-units: 1000000 = 100% = $1.00                     ║
║    - status: 0=active, 1=resolved                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import httpx
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from bs4 import BeautifulSoup
from enum import Enum
import json

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CIRCUIT BREAKER
# =============================================================================

class DataSource(Enum):
    """How data was obtained"""
    API = "api"
    SCRAPER = "scraper"
    SSR = "ssr"
    CACHE = "cache"


@dataclass
class CircuitBreaker:
    """Prevents hammering failed endpoints"""
    failures: int = 0
    last_failure: Optional[datetime] = None
    open_until: Optional[datetime] = None
    
    def record_failure(self):
        self.failures += 1
        self.last_failure = datetime.utcnow()
        if self.failures >= 3:
            self.open_until = datetime.utcnow() + timedelta(minutes=5)
            logger.warning(f"Circuit breaker OPEN until {self.open_until}")
    
    def record_success(self):
        self.failures = 0
        self.open_until = None
    
    @property
    def is_open(self) -> bool:
        if self.open_until is None:
            return False
        if datetime.utcnow() > self.open_until:
            self.open_until = None
            self.failures = 0
            return False
        return True

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
    source: DataSource = DataSource.API
    
    @property
    def mid_price(self) -> float:
        return (self.yes_price + self.no_price) / 2 if self.yes_price and self.no_price else 0


@dataclass 
class ArbOpportunity:
    """Arbitrage opportunity comparing PredictBase vs Polymarket."""
    question: str
    market_id: Optional[str]
    polymarket_url: Optional[str]
    
    # Probabilities
    pb_prob_yes: float      # PredictBase's "fair" probability
    poly_prob_yes: float    # Polymarket's current price
    
    # Edge calculation  
    edge_pct: float         # Absolute difference in percentage points
    edge_direction: str     # "BUY_YES" or "BUY_NO"
    
    # Metadata
    category: Optional[str] = None
    volume_24h: Optional[float] = None
    liquidity: Optional[float] = None
    source: DataSource = DataSource.API
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_actionable(self) -> bool:
        """Check if opportunity meets minimum thresholds"""
        return (
            abs(self.edge_pct) >= 5.0 and
            self.poly_prob_yes >= 0.05 and
            self.poly_prob_yes <= 0.95
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "market_id": self.market_id,
            "polymarket_url": self.polymarket_url,
            "pb_prob_yes": self.pb_prob_yes,
            "poly_prob_yes": self.poly_prob_yes,
            "edge_pct": self.edge_pct,
            "edge_direction": self.edge_direction,
            "category": self.category,
            "source": self.source.value,
            "is_actionable": self.is_actionable,
        }

# =============================================================================
# PREDICTBASE CLIENT
# =============================================================================

class PredictBaseClient:
    """
    Client for PredictBase market data and arbitrage opportunities.
    
    PredictBase URL: https://predictbase.app (NOT .com)
    
    Data fetching priority:
    1. JSON API endpoints (fastest)
    2. SSR embedded data (Next.js __NEXT_DATA__)
    3. HTML scraping (fallback)
    
    Usage:
        async with PredictBaseClient() as client:
            # Get raw markets
            markets = await client.get_markets(limit=100)
            
            # Get arb opportunities (compares PB vs Poly prices)
            opps = await client.get_arb_opportunities(min_edge=5.0)
    """
    
    # CORRECT URL - predictbase.app NOT .com
    BASE_URL = "https://predictbase.app"
    
    # DISCOVERED API ENDPOINTS (via tools/find_predictbase_api.py)
    # PredictBase is its OWN prediction market on Base chain, NOT a Polymarket aggregator
    API_ENDPOINTS = [
        "/api/get_recent_markets_v2",      # Active markets (score: 55)
        "/api/get_resolved_markets_v2",    # Resolved markets (score: 75)  
        "/api/get_recent_claims_v2",       # Recent claims
    ]
    
    # Cache TTL in seconds
    CACHE_TTL = 120  # 2 minutes for arb opportunities
    
    # Rate limiting
    MIN_REQUEST_INTERVAL = 2.0  # seconds
    
    def __init__(self, timeout: float = 30.0, custom_api_url: Optional[str] = None):
        """
        Initialize client.
        
        Args:
            timeout: Request timeout in seconds
            custom_api_url: Override API URL (from discovery tool)
        """
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._api_endpoint: Optional[str] = custom_api_url
        self._use_scraper = False
        self._circuit_breaker = CircuitBreaker()
        self._last_request = 0.0
        
        # Headers to avoid blocks - NOTE: Don't request br encoding, httpx doesn't auto-decompress
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",  # NO brotli - httpx doesn't auto-decompress it
            "Referer": "https://predictbase.app/",
        }
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True
        )
        if not self._api_endpoint:
            await self._discover_api()
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    async def _rate_limit(self):
        """Enforce minimum request interval"""
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request = time.time()
    
    # -------------------------------------------------------------------------
    # API DISCOVERY
    # -------------------------------------------------------------------------
    
    async def _discover_api(self):
        """Try to discover a working API endpoint."""
        logger.info("🔍 Discovering PredictBase API...")
        
        for endpoint in self.API_ENDPOINTS:
            try:
                await self._rate_limit()
                url = f"{self.BASE_URL}{endpoint}"
                resp = await self._client.get(url)
                
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    
                    # Check if it's JSON
                    is_json = "json" in content_type or resp.text.strip().startswith(("[", "{"))
                    
                    if is_json:
                        try:
                            data = resp.json()
                            # PredictBase returns arrays of market objects
                            if isinstance(data, list) and len(data) > 0:
                                first_item = data[0]
                                if isinstance(first_item, dict) and "question" in first_item:
                                    self._api_endpoint = endpoint
                                    self._use_scraper = False
                                    logger.info(f"✅ Found API endpoint: {endpoint} ({len(data)} items)")
                                    self._circuit_breaker.record_success()
                                    return
                        except Exception as e:
                            logger.debug(f"JSON parse error: {e}")
            except Exception as e:
                logger.debug(f"API endpoint {endpoint} failed: {e}")
        
        # No API found, will use scraper/SSR
        self._use_scraper = True
        logger.warning("⚠️ No JSON API found, using SSR extraction + scraper")
    
    # -------------------------------------------------------------------------
    # MARKET FETCHING
    # -------------------------------------------------------------------------
    
    async def get_markets(self, limit: int = 100, include_resolved: bool = False) -> List[PredictBaseMarket]:
        """
        Fetch markets from PredictBase.
        
        Args:
            limit: Maximum markets to fetch
            include_resolved: Include resolved markets (have price history)
        
        Returns:
            List of PredictBaseMarket objects
        """
        # Check circuit breaker
        if self._circuit_breaker.is_open:
            logger.warning("Circuit breaker open - returning cached markets")
            cached = self._get_cached("markets")
            return cached if cached else []
        
        cache_key = f"markets_{limit}_{include_resolved}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        try:
            markets = []
            
            # Strategy 1: API
            if not self._use_scraper:
                markets = await self._fetch_api_markets(limit, include_resolved)
            
            # Strategy 2: SSR extraction
            if not markets:
                markets = await self._extract_ssr_markets(limit)
            
            # Strategy 3: HTML scraping
            if not markets:
                markets = await self._scrape_markets(limit)
            
            if markets:
                self._set_cached(cache_key, markets)
                self._circuit_breaker.record_success()
            else:
                self._circuit_breaker.record_failure()
                
            return markets
            
        except Exception as e:
            logger.error(f"Failed to fetch PredictBase markets: {e}")
            self._circuit_breaker.record_failure()
            return []
    
    async def get_arb_opportunities(
        self,
        min_edge: float = 5.0,
        polymarket_prices: Optional[Dict[str, float]] = None,
    ) -> List[ArbOpportunity]:
        """
        Get arbitrage opportunities comparing PredictBase vs Polymarket.
        
        Args:
            min_edge: Minimum edge in percentage points
            polymarket_prices: Optional dict of {market_id: yes_price}
                             If not provided, uses PredictBase's listed Poly prices
        
        Returns:
            List of ArbOpportunity objects sorted by edge
        """
        cache_key = f"arb_{min_edge}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached
        
        markets = await self.get_markets(limit=200)
        opportunities = []
        
        for market in markets:
            # Get Polymarket price
            if polymarket_prices and market.market_id in polymarket_prices:
                poly_price = polymarket_prices[market.market_id]
            else:
                # Use PredictBase's listed Poly price if available
                poly_price = market.raw_data.get("poly_price") or market.raw_data.get("polymarket_price")
                if poly_price is None:
                    continue
                poly_price = float(poly_price)
            
            # PredictBase's "fair" probability
            pb_prob = market.yes_price
            if pb_prob <= 0:
                continue
            
            # Calculate edge
            edge = (pb_prob - poly_price) * 100
            direction = "BUY_YES" if edge > 0 else "BUY_NO"
            edge_abs = abs(edge)
            
            if edge_abs >= min_edge:
                opp = ArbOpportunity(
                    question=market.question,
                    market_id=market.market_id,
                    polymarket_url=market.url,
                    pb_prob_yes=pb_prob,
                    poly_prob_yes=poly_price,
                    edge_pct=edge_abs,
                    edge_direction=direction,
                    category=market.category,
                    volume_24h=market.volume,
                    source=market.source,
                )
                opportunities.append(opp)
        
        # Sort by edge descending
        opportunities.sort(key=lambda x: x.edge_pct, reverse=True)
        
        if opportunities:
            self._set_cached(cache_key, opportunities)
        
        return opportunities
    
    async def _fetch_api_markets(self, limit: int, include_resolved: bool = False) -> List[PredictBaseMarket]:
        """Fetch markets from discovered API endpoints."""
        await self._rate_limit()
        
        # Build list of endpoints to try
        endpoints_to_try = []
        if self._api_endpoint:
            endpoints_to_try.append(self._api_endpoint)
        
        # Add resolved markets endpoint if requested (has more price data)
        if include_resolved:
            endpoints_to_try.append("/api/get_resolved_markets_v2")
        
        # Always try recent markets
        if "/api/get_recent_markets_v2" not in endpoints_to_try:
            endpoints_to_try.append("/api/get_recent_markets_v2")
        
        all_markets = []
        
        for endpoint in endpoints_to_try:
            if len(all_markets) >= limit:
                break
                
            try:
                url = f"{self.BASE_URL}{endpoint}"
                resp = await self._client.get(url)
                
                if resp.status_code != 200:
                    continue
                    
                data = resp.json()
                items = data if isinstance(data, list) else data.get("markets", data.get("data", []))
                
                for item in items:
                    if len(all_markets) >= limit:
                        break
                    market = self._parse_predictbase_market(item, skip_resolved=not include_resolved)
                    if market:
                        all_markets.append(market)
                
                if all_markets:
                    logger.info(f"📥 Fetched {len(all_markets)} markets from {endpoint}")
                    self._api_endpoint = endpoint
                    
            except Exception as e:
                logger.debug(f"API {endpoint} failed: {e}")
                continue
        
        return all_markets
    
    def _parse_predictbase_market(self, item: dict, skip_resolved: bool = True) -> Optional[PredictBaseMarket]:
        """
        Parse PredictBase API response.
        
        PredictBase market structure:
        {
            "id": "11666",
            "question": "Premier League: Bournemouth vs. Arsenal",
            "status": 0,  # 0=active, 1=resolved
            "optionTitles": ["Bournemouth", "Draw", "Arsenal"] or ["Yes", "No"],
            "optionPrices": ["662857", "942500", "269285"],  # in micro-units (1000000 = 100%)
            "volume": "1234567",
            "endsAt": "2026-01-03T17:30:00Z"
        }
        """
        try:
            market_id = str(item.get("id", ""))
            question = item.get("question", "")
            status = item.get("status", 0)
            
            if not question:
                return None
            
            # Skip resolved markets if requested
            # status: 0=active, 1=resolved
            if skip_resolved and status != 0:
                return None
            
            # Parse option prices (stored as strings in micro-units)
            option_titles = item.get("optionTitles", [])
            option_prices_raw = item.get("optionPrices", [])
            
            yes_price = 0.0
            no_price = 0.0
            
            if option_prices_raw and len(option_prices_raw) >= 2:
                # Convert from micro-units: 1000000 = 100% = $1.00
                try:
                    prices = [int(p) / 1000000 for p in option_prices_raw]
                    
                    # For binary markets ["Yes", "No"]
                    if len(option_titles) == 2:
                        titles_lower = [t.lower() for t in option_titles]
                        if "yes" in titles_lower:
                            yes_idx = titles_lower.index("yes")
                            no_idx = 1 - yes_idx
                            yes_price = prices[yes_idx]
                            no_price = prices[no_idx]
                        else:
                            # Team vs Team - first option is "Yes" equivalent
                            yes_price = prices[0]
                            no_price = prices[1]
                    
                    # For 3+ options (e.g., sports with Draw)
                    elif len(option_titles) >= 3:
                        # Use first option as the main "bet"
                        yes_price = prices[0]
                        # Sum of other options as "no" equivalent  
                        no_price = sum(prices[1:]) / (len(prices) - 1) if len(prices) > 1 else 0
                        
                except (ValueError, IndexError) as e:
                    logger.debug(f"Price parse error: {e}")
            
            # Skip markets with no price activity (all zeros)
            if yes_price == 0 and no_price == 0:
                return None
            
            # Volume in micro-units
            volume = 0.0
            try:
                volume = int(item.get("volume", 0)) / 1000000
            except:
                pass
            
            # Categories
            categories = item.get("categories", [])
            category = categories[0] if categories else ""
            
            return PredictBaseMarket(
                market_id=market_id,
                question=question,
                url=f"{self.BASE_URL}/market/{market_id}",
                yes_price=yes_price,
                no_price=no_price,
                volume=volume,
                category=category,
                raw_data=item,
                source=DataSource.API,
            )
        except Exception as e:
            logger.debug(f"Failed to parse PredictBase market: {e}")
            return None
    
    async def _extract_ssr_markets(self, limit: int) -> List[PredictBaseMarket]:
        """Extract markets from SSR-embedded JSON (Next.js pattern)."""
        await self._rate_limit()
        
        try:
            resp = await self._client.get(self.BASE_URL)
            if resp.status_code != 200:
                return []
            
            html = resp.text
            markets = []
            
            # Next.js __NEXT_DATA__ pattern
            nextjs_match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                html,
                re.DOTALL,
            )
            
            if nextjs_match:
                try:
                    data = json.loads(nextjs_match.group(1))
                    page_props = data.get("props", {}).get("pageProps", {})
                    
                    # Try common data keys
                    for key in ["markets", "opportunities", "data", "items"]:
                        if key in page_props and isinstance(page_props[key], list):
                            for item in page_props[key][:limit]:
                                market = self._parse_api_market(item, DataSource.SSR)
                                if market:
                                    markets.append(market)
                            break
                    
                    if markets:
                        logger.info(f"📥 Extracted {len(markets)} markets from SSR data")
                        return markets
                        
                except Exception as e:
                    logger.debug(f"Failed to parse __NEXT_DATA__: {e}")
            
            # Nuxt.js pattern
            nuxt_match = re.search(r'window\.__NUXT__\s*=\s*({.*?});?\s*</script>', html, re.DOTALL)
            if nuxt_match:
                try:
                    # Extract arrays from Nuxt data
                    array_matches = re.findall(r'\[{[^]]+}\]', nuxt_match.group(1))
                    for arr_str in array_matches:
                        try:
                            items = json.loads(arr_str)
                            for item in items[:limit]:
                                market = self._parse_api_market(item, DataSource.SSR)
                                if market:
                                    markets.append(market)
                        except:
                            continue
                except:
                    pass
            
            return markets
            
        except Exception as e:
            logger.debug(f"SSR extraction error: {e}")
            return []
    
    def _parse_api_market(self, item: dict, source: DataSource = DataSource.API) -> Optional[PredictBaseMarket]:
        """Parse API response into PredictBaseMarket."""
        try:
            # Try common field names for ID
            market_id = (
                item.get("id") or 
                item.get("market_id") or 
                item.get("condition_id") or
                item.get("slug", "")
            )
            
            # Question/title
            question = (
                item.get("question") or 
                item.get("title") or 
                item.get("name") or
                item.get("market", {}).get("question", "")
            )
            
            if not question:
                return None
            
            # Extract probabilities/prices
            yes_price = 0.0
            no_price = 0.0
            
            # Try structured outcomes
            if "outcomes" in item:
                for outcome in item["outcomes"]:
                    name = str(outcome.get("name", "")).lower()
                    if name == "yes":
                        yes_price = float(outcome.get("price", outcome.get("probability", 0)))
                    elif name == "no":
                        no_price = float(outcome.get("price", outcome.get("probability", 0)))
            else:
                # Try flat fields - PredictBase "fair" probability
                yes_price = float(
                    item.get("probability") or
                    item.get("fair_price") or
                    item.get("pb_price") or
                    item.get("yes_price") or 
                    item.get("yesPrice") or 
                    0
                )
                no_price = float(
                    item.get("no_price") or 
                    item.get("noPrice") or 
                    (1 - yes_price if yes_price > 0 else 0)
                )
            
            # Normalize prices (might be percentage or decimal)
            if yes_price > 1:
                yes_price /= 100
            if no_price > 1:
                no_price /= 100
            
            # Extract URL
            url = (
                item.get("polymarket_url") or
                item.get("url") or
                item.get("market_url") or
                f"{self.BASE_URL}/market/{market_id}"
            )
            
            return PredictBaseMarket(
                market_id=str(market_id),
                question=question,
                url=url,
                yes_price=yes_price,
                no_price=no_price,
                volume=float(item.get("volume", item.get("volume_24h", 0))),
                category=item.get("category", ""),
                raw_data=item,
                source=source,
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
        
        This is a fallback when no API/SSR data is available.
        May break if website structure changes.
        """
        markets = []
        
        # Pages to try
        pages_to_try = [
            "/",
            "/markets",
            "/opportunities",
            "/explore",
            "/trending",
        ]
        
        for page in pages_to_try:
            if len(markets) >= limit:
                break
                
            try:
                await self._rate_limit()
                url = f"{self.BASE_URL}{page}"
                resp = await self._client.get(url)
                
                if resp.status_code != 200:
                    continue
                
                html = resp.text
                soup = BeautifulSoup(html, 'html.parser')
                
                found_markets = self._extract_markets_from_html(soup, url)
                
                if found_markets:
                    markets.extend(found_markets)
                    logger.info(f"📥 Scraped {len(found_markets)} markets from {page}")
                    
            except Exception as e:
                logger.debug(f"Scrape error on {page}: {e}")
        
        return markets[:limit]
    
    def _extract_markets_from_html(self, soup: BeautifulSoup, base_url: str) -> List[PredictBaseMarket]:
        """Extract market data from HTML."""
        markets = []
        
        # Common selectors for market cards
        selectors = [
            '[class*="market"]',
            '[class*="opportunity"]',
            '[class*="card"]',
            '[data-market-id]',
            '[data-market]',
            'article',
            'tr[class*="market"]',
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            
            for elem in elements:
                try:
                    market = self._parse_market_element(elem, base_url)
                    if market and market.question and len(market.question) > 10:
                        # Avoid duplicates
                        if not any(m.question == market.question for m in markets):
                            markets.append(market)
                except:
                    pass
        
        return markets
    
    def _parse_market_element(self, elem, base_url: str) -> Optional[PredictBaseMarket]:
        """Parse a market element from HTML."""
        # Try to extract question
        question = ""
        for tag in ['h2', 'h3', 'h4', 'h5', 'p[class*="title"]', 'span[class*="title"]', 'a']:
            title_elem = elem.select_one(tag) if isinstance(tag, str) and '[' in tag else elem.find(tag)
            if title_elem:
                text = title_elem.get_text(strip=True)
                if len(text) > 15:  # Minimum reasonable question length
                    question = text
                    break
        
        if not question:
            return None
        
        # Try to extract prices from text
        text = elem.get_text()
        yes_price = 0.0
        
        # Multiple price patterns
        price_patterns = [
            r'(?:Yes|YES)[:\s]*\$?(\d+\.?\d*)[%¢]?',
            r'(\d+\.?\d*)\s*%?\s*(?:Yes|YES)',
            r'(?:Fair|fair)[:\s]*(\d+\.?\d*)',
            r'(?:PB|pb)[:\s]*(\d+\.?\d*)',
            r'(\d{1,2}(?:\.\d+)?)\s*[%¢]',  # Generic percentage
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price = float(match.group(1))
                yes_price = price / 100 if price > 1 else price
                break
        
        # Extract Polymarket URL if present
        poly_link = elem.select_one('a[href*="polymarket"]')
        url = poly_link.get("href") if poly_link else ""
        
        if not url:
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
            url=url or base_url,
            yes_price=yes_price,
            no_price=1 - yes_price if yes_price > 0 else 0,
            source=DataSource.SCRAPER,
        )
    
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
    # HEALTH CHECK
    # -------------------------------------------------------------------------
    
    async def health_check(self) -> Dict[str, Any]:
        """Check client health and connectivity."""
        result = {
            "status": "unknown",
            "base_url": self.BASE_URL,
            "api_endpoint": self._api_endpoint,
            "using_scraper": self._use_scraper,
            "circuit_breaker": "open" if self._circuit_breaker.is_open else "closed",
            "cache_size": len(self._cache),
            "latency_ms": None,
        }
        
        try:
            start = time.time()
            resp = await self._client.head(self.BASE_URL)
            latency = (time.time() - start) * 1000
            result["latency_ms"] = round(latency, 1)
            result["status"] = "healthy" if resp.status_code < 400 else "degraded"
        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
        
        return result
    
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
# CONVENIENCE FUNCTIONS
# =============================================================================

async def fetch_arb_opportunities(min_edge: float = 5.0) -> List[Dict[str, Any]]:
    """
    One-shot function to fetch arbitrage opportunities.
    
    Returns:
        List of opportunity dicts
    """
    async with PredictBaseClient() as client:
        opportunities = await client.get_arb_opportunities(min_edge=min_edge)
        return [o.to_dict() for o in opportunities]


# =============================================================================
# TESTING
# =============================================================================

async def test_client():
    """Test the PredictBase client."""
    print("=" * 70)
    print("          PREDICTBASE CLIENT TEST")
    print("=" * 70)
    print(f"Target: https://predictbase.app")
    print()
    print("NOTE: PredictBase is a SEPARATE prediction market on Base chain,")
    print("      NOT a Polymarket price aggregator. ARB opportunities exist")
    print("      when similar markets exist on BOTH platforms.")
    
    async with PredictBaseClient() as client:
        # Health check
        print("\n📡 Health Check...")
        health = await client.health_check()
        print(f"   Status: {health['status']}")
        print(f"   API Endpoint: {health['api_endpoint']}")
        print(f"   Latency: {health['latency_ms']}ms")
        print(f"   Circuit Breaker: {health['circuit_breaker']}")
        
        # Fetch markets - try both recent and resolved
        print("\n🔍 Fetching recent markets...")
        markets = await client.get_markets(limit=10)
        print(f"   Found {len(markets)} active markets with prices")
        
        if not markets:
            # Try resolved markets to show data format
            print("\n   (Recent markets have 0 volume - fetching resolved markets)")
            markets = await client.get_markets(limit=10, include_resolved=True)
            print(f"   Found {len(markets)} markets with price history")
        
        if markets:
            print("\n📊 Sample Markets:")
            print("-" * 70)
            for m in markets[:5]:
                print(f"\n   📈 {m.question[:55]}...")
                print(f"      Option 1 Price: {m.yes_price:.1%}")
                print(f"      Option 2 Price: {m.no_price:.1%}")
                print(f"      Volume: ${m.volume:.2f}")
                print(f"      Source: {m.source.value}")
        
        # Cross-exchange arbitrage section
        print("\n" + "=" * 70)
        print("          CROSS-EXCHANGE ARBITRAGE")
        print("=" * 70)
        print("""
To find ARB opportunities between PredictBase and Polymarket:
1. Fetch markets from both platforms
2. Match similar questions using fuzzy matching
3. Compare prices - if PB says 60% and Poly says 45%, that's 15% edge
4. Execute trades on the underpriced platform

Example matching markets:
- PB: "Bitcoin above $100,000 by March 2026?"
- Poly: "Will BTC exceed $100K by Q1 2026?"

The strategy module should:
1. client.get_markets() -> List[PredictBaseMarket]
2. polymarket_client.get_markets() -> List[PolyMarket]
3. match_markets(pb_markets, poly_markets) -> List[(pb, poly, similarity)]
4. calculate_edge(pb_price, poly_price) -> edge_pct
        """)


if __name__ == "__main__":
    asyncio.run(test_client())
