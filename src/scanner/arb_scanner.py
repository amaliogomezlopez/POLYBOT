"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         ARB SCANNER                                          ║
║                                                                              ║
║  Cross-exchange arbitrage scanner between Polymarket and PredictBase.        ║
║                                                                              ║
║  Arbitrage Types:                                                            ║
║    1. DIRECT: Same market, different prices                                  ║
║       - Buy YES where cheaper, sell where expensive                          ║
║                                                                              ║
║    2. SYNTHETIC: Hedge across platforms                                      ║
║       - YES_Poly + NO_PB < $1.00 → Guaranteed profit                        ║
║       - NO_Poly + YES_PB < $1.00 → Guaranteed profit                        ║
║                                                                              ║
║  Performance:                                                                ║
║    - TARGETED FETCH: Only Sports markets from Polymarket                     ║
║    - Batch fuzzy matching (not per-market lookup)                            ║
║    - Runs async every 60s without blocking main daemon                       ║
║    - Minimum 2.5% ROI threshold (covers bridging fees)                       ║
║                                                                              ║
║  Strategy ID: ARB_PREDICTBASE_V1                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import httpx
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# POLYMARKET SPORTS CATEGORIES (discovered via tools/list_all_categories.py)
# ─────────────────────────────────────────────────────────────────────────────

POLYMARKET_SPORTS_CATEGORIES = {
    # Parent category
    "sports": "5487",
    
    # Sub-categories (all have parent 5487)
    "basketball": "5488",
    "boxing_mma": "5491",
    "football": "5492",
    "esports": "5493",
    "soccer": "5494",
    "baseball": "5496",
    "hockey": "5498",
    "cricket": "5501",
    "tennis": "5502",
    "olympics": "5505",
    "golf": "5489",
    "racing": "5495",
    "chess": "5490",
    "poker": "5506",
}

# API Configuration
GAMMA_API = "https://gamma-api.polymarket.com"

# ─────────────────────────────────────────────────────────────────────────────
# FUZZY MATCHING
# ─────────────────────────────────────────────────────────────────────────────

try:
    from thefuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logger.warning("⚠️ thefuzz not installed - pip install thefuzz[speedup]")


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MarketPair:
    """A matched pair of markets across exchanges."""
    poly_question: str
    poly_condition_id: str
    poly_token_id: str
    poly_yes_price: float
    poly_no_price: float
    poly_volume: float
    
    pb_question: str
    pb_market_id: str
    pb_yes_price: float
    pb_no_price: float
    pb_volume: float
    
    match_score: float  # Fuzzy similarity 0-100
    
    def __repr__(self):
        return (f"MarketPair(score={self.match_score:.0f}, "
                f"poly_yes=${self.poly_yes_price:.3f}, "
                f"pb_yes=${self.pb_yes_price:.3f})")


@dataclass
class ArbSignal:
    """Arbitrage signal ready for execution."""
    signal_id: str
    strategy_id: str = "ARB_PREDICTBASE_V1"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Arbitrage type
    arb_type: str = ""  # "DIRECT" or "SYNTHETIC"
    
    # Market info
    question: str = ""
    poly_condition_id: str = ""
    poly_token_id: str = ""
    pb_market_id: str = ""
    
    # Trade details - Polymarket side
    poly_side: str = ""  # "YES" or "NO"
    poly_price: float = 0.0
    poly_stake: float = 0.0
    
    # Trade details - PredictBase side (hedge)
    pb_side: str = ""  # "YES" or "NO"
    pb_price: float = 0.0
    pb_stake: float = 0.0
    
    # Profit calculation
    total_cost: float = 0.0
    guaranteed_payout: float = 1.0  # Binary markets pay $1
    gross_profit: float = 0.0
    roi_pct: float = 0.0
    
    # Match quality
    match_score: float = 0.0
    confidence: float = 0.0
    
    # Execution status
    executed: bool = False
    paper_mode: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "timestamp": self.timestamp.isoformat(),
            "arb_type": self.arb_type,
            "question": self.question,
            "poly_condition_id": self.poly_condition_id,
            "poly_token_id": self.poly_token_id,
            "pb_market_id": self.pb_market_id,
            "poly_side": self.poly_side,
            "poly_price": self.poly_price,
            "poly_stake": self.poly_stake,
            "pb_side": self.pb_side,
            "pb_price": self.pb_price,
            "pb_stake": self.pb_stake,
            "total_cost": self.total_cost,
            "gross_profit": self.gross_profit,
            "roi_pct": self.roi_pct,
            "match_score": self.match_score,
            "confidence": self.confidence,
            "paper_mode": self.paper_mode,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PRICE NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def normalize_pb_price(micro_units: Any) -> float:
    """
    Convert PredictBase micro-units to decimal price.
    
    PredictBase uses: 1000000 = 100% = $1.00
    Polymarket uses:  1.0 = 100% = $1.00
    
    Args:
        micro_units: Price in micro-units (int, float, or str)
        
    Returns:
        Decimal price 0.0-1.0
    """
    try:
        value = float(micro_units) if micro_units else 0
        # Detect micro-units (> 1000 typically means micro-units)
        if value > 1000:
            return value / 1_000_000
        elif value > 1:
            # Could be percentage (0-100)
            return value / 100
        else:
            # Already decimal
            return value
    except (TypeError, ValueError):
        return 0.0


def normalize_poly_price(price: Any) -> float:
    """
    Normalize Polymarket price to decimal.
    
    Polymarket uses decimal 0.0-1.0 already, but sometimes
    API returns strings or percentages.
    """
    try:
        value = float(price) if price else 0
        if value > 1:
            return value / 100  # Was percentage
        return value
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# FUZZY MATCHING
# ─────────────────────────────────────────────────────────────────────────────

# Words that indicate OPPOSITE meanings - skip these matches!
OPPOSITE_INDICATORS = {
    "not", "won't", "doesn't", "isn't", "no", "never", "under", "over",
    "before", "after", "above", "below", "more", "less", "fewer"
}

# Common stopwords to ignore in matching
STOPWORDS = {
    "will", "the", "be", "a", "an", "in", "on", "at", "to", "for", "of", 
    "by", "this", "that", "it", "is", "are", "was", "were", "been", "being"
}


def clean_question(q: str) -> str:
    """Normalize question for better matching."""
    import re
    
    # Lowercase
    q = q.lower()
    
    # Remove dates in various formats (keep the question semantic)
    q = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '', q)
    q = re.sub(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d+\b', '', q, flags=re.IGNORECASE)
    
    # Remove special chars but keep spaces
    q = re.sub(r'[^\w\s]', ' ', q)
    
    # Collapse whitespace
    q = ' '.join(q.split())
    
    return q.strip()


def has_opposite_indicators(q1: str, q2: str) -> bool:
    """
    Check if questions have contradicting indicators.
    
    Example:
    - "Will BTC reach 100k?" vs "Will BTC NOT reach 100k?"
    - These would fuzzy-match high but are OPPOSITE bets!
    """
    words1 = set(q1.lower().split())
    words2 = set(q2.lower().split())
    
    # Check for exclusives (word in one but not other)
    for indicator in OPPOSITE_INDICATORS:
        if (indicator in words1) != (indicator in words2):
            return True
    
    return False


def calculate_match_score(poly_q: str, pb_q: str) -> float:
    """
    Calculate fuzzy match score between two questions.
    
    Uses token_ratio which handles word reordering:
    "Will Trump win 2024?" ≈ "Trump win in 2024?"
    
    Returns:
        Score 0-100 (higher = better match)
    """
    if not FUZZY_AVAILABLE:
        # Fallback: simple word overlap
        poly_words = set(clean_question(poly_q).split()) - STOPWORDS
        pb_words = set(clean_question(pb_q).split()) - STOPWORDS
        
        if not poly_words:
            return 0
        
        overlap = len(poly_words & pb_words)
        return (overlap / max(len(poly_words), len(pb_words))) * 100
    
    # Use token_sort_ratio - handles word reordering
    clean_poly = clean_question(poly_q)
    clean_pb = clean_question(pb_q)
    
    score = fuzz.token_sort_ratio(clean_poly, clean_pb)
    
    return score


def batch_match_markets(
    poly_markets: List[Dict],
    pb_markets: List[Any],
    threshold: int = 85,
    max_matches: int = 100
) -> List[MarketPair]:
    """
    Batch fuzzy match Polymarket and PredictBase markets.
    
    This is much more efficient than per-market lookup because:
    - Single pass through both lists
    - O(n*m) but with early termination
    - Caches cleaned questions
    
    Args:
        poly_markets: List of Polymarket market dicts
        pb_markets: List of PredictBaseMarket objects
        threshold: Minimum fuzzy score (0-100)
        max_matches: Maximum matches to return
        
    Returns:
        List of MarketPair objects sorted by match score
    """
    matches: List[MarketPair] = []
    
    # Pre-clean PB questions
    pb_cleaned = []
    for pb in pb_markets:
        q = getattr(pb, 'question', '') or ''
        pb_cleaned.append((pb, clean_question(q)))
    
    logger.info(f"🔍 Matching {len(poly_markets)} Poly markets vs {len(pb_markets)} PB markets...")
    
    for poly in poly_markets:
        poly_q = poly.get('question', '') or ''
        clean_poly = clean_question(poly_q)
        
        if not clean_poly:
            continue
        
        # Find best PB match for this Poly market
        best_pb = None
        best_score = 0
        
        for pb, clean_pb in pb_cleaned:
            if not clean_pb:
                continue
            
            score = calculate_match_score(clean_poly, clean_pb)
            
            if score > best_score:
                best_score = score
                best_pb = pb
        
        # Check threshold
        if best_score < threshold or best_pb is None:
            continue
        
        # Check for opposite indicators (skip contradicting questions)
        if has_opposite_indicators(poly_q, best_pb.question):
            logger.debug(f"⚠️ Skipping opposite match: '{poly_q[:40]}' vs '{best_pb.question[:40]}'")
            continue
        
        # Extract prices
        poly_yes = normalize_poly_price(poly.get('yes_price') or poly.get('outcomePrices', [0.5])[0])
        poly_no = normalize_poly_price(poly.get('no_price') or (1 - poly_yes))
        
        pb_yes = normalize_pb_price(best_pb.yes_price if hasattr(best_pb, 'yes_price') else 0)
        pb_no = normalize_pb_price(best_pb.no_price if hasattr(best_pb, 'no_price') else 0)
        
        # Skip if no valid prices
        if poly_yes <= 0 or pb_yes <= 0:
            continue
        
        pair = MarketPair(
            poly_question=poly_q,
            poly_condition_id=poly.get('condition_id') or poly.get('conditionId', ''),
            poly_token_id=poly.get('token_id') or '',
            poly_yes_price=poly_yes,
            poly_no_price=poly_no,
            poly_volume=float(poly.get('volume_24h') or poly.get('volume') or 0),
            pb_question=best_pb.question,
            pb_market_id=best_pb.market_id if hasattr(best_pb, 'market_id') else '',
            pb_yes_price=pb_yes,
            pb_no_price=pb_no,
            pb_volume=best_pb.volume if hasattr(best_pb, 'volume') else 0,
            match_score=best_score,
        )
        
        matches.append(pair)
        
        if len(matches) >= max_matches:
            break
    
    # Sort by match score descending
    matches.sort(key=lambda x: x.match_score, reverse=True)
    
    logger.info(f"✅ Found {len(matches)} market pairs with score >= {threshold}")
    
    return matches


# ─────────────────────────────────────────────────────────────────────────────
# TARGETED POLYMARKET FETCHING (Sports Categories)
# ─────────────────────────────────────────────────────────────────────────────

import re as _re

# Sports keywords for filtering (since category param doesn't work)
# Use word boundary matching to avoid false positives like "inflation" matching "nfl"
SPORTS_KEYWORDS = [
    # Leagues (require word boundary)
    r'\bnba\b', r'\bnfl\b', r'\bmlb\b', r'\bnhl\b', r'\bmls\b', r'\bncaa\b', r'\buefa\b', r'\bfifa\b',
    r'\bpremier league\b', r'\bla liga\b', r'\bbundesliga\b', r'\bserie a\b', r'\bligue 1\b',
    r'\bchampions league\b', r'\beuropa league\b', r'\bworld cup\b',
    # Sports
    r'\bbasketball\b', r'\bfootball\b', r'\bsoccer\b', r'\bhockey\b', r'\bbaseball\b',
    r'\btennis\b', r'\bgolf\b', r'\bboxing\b', r'\bmma\b', r'\bufc\b', r'\besports\b',
    r'\bcricket\b', r'\brugby\b', r'\bf1\b', r'\bformula 1\b', r'\bnascar\b',
    # Events
    r'\bsuper bowl\b', r'\bplayoff\b', r'\bplayoffs\b', r'\bchampionship\b',
    r'\bworld series\b', r'\bstanley cup\b', r'\bfinals\b',
    r'\bmvp\b', r'\brookie of the year\b', r'\bscoring leader\b',
    # NFL Teams
    r'\bchiefs\b', r'\beagles\b', r'\bbills\b', r'\bravens\b', r'\b49ers\b', r'\bcowboys\b', r'\blions\b',
    r'\bpackers\b', r'\bdolphins\b', r'\bbengals\b', r'\bjets\b', r'\bbears\b', r'\brams\b', r'\bchargers\b',
    r'\bvikings\b', r'\bseahawks\b', r'\bsteelers\b', r'\bbroncos\b', r'\bsaints\b', r'\bcardinals\b',
    r'\bcolts\b', r'\bfalcons\b', r'\bpanthers\b', r'\bcommanders\b', r'\btexans\b', r'\bbrowns\b',
    r'\bjaguars\b', r'\braiders\b', r'\btitans\b', r'\bgiants\b', r'\bpatriots\b', r'\bbuccaneers\b',
    # NBA Teams  
    r'\blakers\b', r'\bceltics\b', r'\bwarriors\b', r'\bbucks\b', r'\bsuns\b', r'\bnuggets\b', r'\bheat\b',
    r'\bcavaliers\b', r'\bmavericks\b', r'\bthunder\b', r'\bgrizzlies\b', r'\bclippers\b', r'\bkings\b',
    r'\brockets\b', r'\bnets\b', r'\bknicks\b', r'\bsixers\b', r'\btimberwolves\b', r'\bpelicans\b',
    r'\bhawks\b', r'\bbulls\b', r'\bhornets\b', r'\bpistons\b', r'\bpacers\b', r'\bmagic\b', r'\braptors\b',
    r'\bwizards\b', r'\bspurs\b', r'\bjazz\b', r'\bblazers\b',
    # Conferences
    r'\bnfc\b', r'\bafc\b', r'\beastern conference\b', r'\bwestern conference\b',
]

# Compile regex pattern once for efficiency
_SPORTS_PATTERN = _re.compile('|'.join(SPORTS_KEYWORDS), _re.IGNORECASE)

def _is_sports_question(question: str) -> bool:
    """Check if question is sports-related using word boundary matching."""
    return bool(_SPORTS_PATTERN.search(question))

async def fetch_targeted_markets(
    limit: int = 500,
    use_events: bool = True,
    use_keyword_filter: bool = True,
) -> List[Dict]:
    """
    Fetch Polymarket sports markets using WORKING strategies.
    
    NOTE: The category param filter does NOT work in Gamma API.
    This function uses two strategies that DO work:
    1. Events endpoint - fetches events and filters by sports keywords
    2. Keyword filtering - fetches all markets and filters by question text
    
    Args:
        limit: Max markets to fetch
        use_events: Include events-based fetching
        use_keyword_filter: Include keyword-filtered markets
        
    Returns:
        List of sports market dicts ready for ARB matching
    """
    all_markets = []
    seen_ids = set()
    
    async with httpx.AsyncClient(timeout=30) as client:
        
        # STRATEGY 1: Fetch via Events endpoint
        if use_events:
            try:
                logger.info("   📅 Fetching sports via Events endpoint...")
                resp = await client.get(
                    f"{GAMMA_API}/events",
                    params={"limit": 100, "active": "true"}
                )
                
                if resp.status_code == 200:
                    events = resp.json()
                    sports_events = []
                    
                    for event in events:
                        title = event.get('title', '')
                        slug = event.get('slug', '')
                        combined = f"{title} {slug}"
                        
                        if _is_sports_question(combined):
                            sports_events.append(event)
                    
                    logger.info(f"   📅 Found {len(sports_events)} sports events")
                    
                    # Get markets from each sports event
                    for event in sports_events[:30]:  # Limit API calls
                        event_slug = event.get('slug')
                        if event_slug:
                            try:
                                resp = await client.get(
                                    f"{GAMMA_API}/events/{event_slug}"
                                )
                                if resp.status_code == 200:
                                    event_data = resp.json()
                                    markets = event_data.get('markets', [])
                                    for m in markets:
                                        question = m.get('question', '')
                                        # Double-check: only add if question is sports
                                        if _is_sports_question(question):
                                            cid = m.get("conditionId") or m.get("condition_id")
                                            if cid and cid not in seen_ids:
                                                seen_ids.add(cid)
                                                all_markets.append(m)
                                await asyncio.sleep(0.05)
                            except:
                                pass
                    
                    logger.info(f"   📅 Got {len(all_markets)} markets from events")
                    
            except Exception as e:
                logger.warning(f"Events fetch failed: {e}")
        
        # STRATEGY 2: Fetch bulk markets and filter by keywords
        if use_keyword_filter:
            try:
                logger.info("   🔍 Fetching markets with keyword filtering...")
                
                # Fetch in batches (API returns 100 per request)
                offset = 0
                batch_size = 100
                total_fetched = 0
                sports_found = 0
                
                while total_fetched < limit:
                    resp = await client.get(
                        f"{GAMMA_API}/markets",
                        params={
                            "limit": batch_size,
                            "offset": offset,
                            "active": "true",
                            "closed": "false",
                        }
                    )
                    
                    if resp.status_code != 200:
                        break
                    
                    markets = resp.json()
                    if not markets:
                        break
                    
                    for m in markets:
                        question = m.get('question', '')
                        
                        # Check if sports-related using word boundary regex
                        if _is_sports_question(question):
                            cid = m.get("conditionId") or m.get("condition_id")
                            if cid and cid not in seen_ids:
                                seen_ids.add(cid)
                                all_markets.append(m)
                                sports_found += 1
                    
                    total_fetched += len(markets)
                    offset += batch_size
                    await asyncio.sleep(0.1)
                    
                    # Stop if we have enough sports markets
                    if sports_found >= limit // 2:
                        break
                
                logger.info(f"   🔍 Filtered {sports_found} sports from {total_fetched} markets")
                
            except Exception as e:
                logger.warning(f"Keyword filter fetch failed: {e}")
    
    logger.info(f"🏀 TARGETED FETCH COMPLETE: {len(all_markets)} sports markets")
    return all_markets


def extract_pb_keywords(pb_markets: List) -> List[str]:
    """
    Extract team/entity names from PredictBase questions.
    
    These can be used to search Polymarket for matching markets.
    
    Example:
        "NHL: Lakers vs. Celtics" -> ["Lakers", "Celtics"]
        "Premier League: Arsenal vs. Chelsea" -> ["Arsenal", "Chelsea"]
    """
    keywords = set()
    
    # Common team/entity patterns
    import re
    
    for m in pb_markets:
        q = getattr(m, 'question', '') or ''
        
        # Pattern: "X vs. Y" or "X vs Y"
        vs_match = re.search(r':\s*(.+?)\s+vs\.?\s+(.+?)(?:\?|$)', q, re.IGNORECASE)
        if vs_match:
            team1, team2 = vs_match.groups()
            keywords.add(team1.strip())
            keywords.add(team2.strip())
            continue
        
        # Pattern: Team names (capitalized words 4+ chars)
        words = re.findall(r'\b([A-Z][a-z]{3,})\b', q)
        for word in words:
            # Skip common non-team words
            if word.lower() not in ['above', 'below', 'january', 'february', 'march',
                                    'april', 'june', 'july', 'august', 'september',
                                    'october', 'november', 'december', 'bitcoin',
                                    'ethereum', 'will', 'this', 'that']:
                keywords.add(word)
    
    # Return top keywords (most likely to match)
    return list(keywords)[:50]


# ─────────────────────────────────────────────────────────────────────────────
# ARBITRAGE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class ARBScanner:
    """
    Cross-exchange arbitrage scanner.
    
    Usage:
        scanner = ARBScanner(min_roi_pct=2.5, stake_size=50.0)
        async with scanner:
            signals = await scanner.scan()
            for signal in signals:
                print(f"💰 {signal.arb_type}: {signal.roi_pct:.1f}% ROI on {signal.question[:50]}")
    """
    
    STRATEGY_ID = "ARB_PREDICTBASE_V1"
    
    def __init__(
        self,
        min_roi_pct: float = 2.5,       # Minimum ROI (covers bridging fees)
        max_roi_pct: float = 25.0,      # Max ROI (suspicious - stale data?)
        fuzzy_threshold: int = 60,       # Minimum fuzzy match score (lowered for different formats)
        stake_size: float = 50.0,        # USD per trade
        paper_mode: bool = True,
        scan_interval: int = 60,         # Seconds between scans
    ):
        self.min_roi_pct = min_roi_pct
        self.max_roi_pct = max_roi_pct
        self.fuzzy_threshold = fuzzy_threshold
        self.stake_size = stake_size
        self.paper_mode = paper_mode
        self.scan_interval = scan_interval
        
        # Clients (lazy init)
        self._pb_client = None
        self._initialized = False
        
        # Stats
        self._total_scans = 0
        self._total_signals = 0
        self._near_misses = 0
        
        # Cache
        self._pb_markets_cache: List = []
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 120  # 2 minutes
    
    async def __aenter__(self):
        """Initialize clients."""
        try:
            from src.exchanges.predictbase_client import PredictBaseClient
            self._pb_client = PredictBaseClient()
            await self._pb_client.__aenter__()
            self._initialized = True
            logger.info("✅ ARBScanner initialized with PredictBase client")
        except Exception as e:
            logger.warning(f"⚠️ Failed to init PredictBase: {e}")
        return self
    
    async def __aexit__(self, *args):
        """Cleanup."""
        if self._pb_client:
            await self._pb_client.__aexit__(*args)
    
    async def _get_pb_markets(self) -> List:
        """Get PredictBase markets with caching."""
        # Check cache
        if (self._cache_timestamp and 
            self._pb_markets_cache and
            (datetime.utcnow() - self._cache_timestamp).seconds < self._cache_ttl):
            return self._pb_markets_cache
        
        if not self._pb_client:
            return []
        
        try:
            # Get both active and resolved (for price history)
            markets = await self._pb_client.get_markets(
                limit=200, 
                include_resolved=True
            )
            
            self._pb_markets_cache = markets
            self._cache_timestamp = datetime.utcnow()
            
            logger.info(f"📡 Fetched {len(markets)} PredictBase markets")
            return markets
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch PB markets: {e}")
            return self._pb_markets_cache  # Return stale cache
    
    def _detect_synthetic_arb(self, pair: MarketPair) -> Optional[ArbSignal]:
        """
        Detect synthetic arbitrage opportunity.
        
        Synthetic arb = Buy YES on one platform + Buy NO on other
        If combined cost < $1, guaranteed profit regardless of outcome.
        
        Example:
            Poly YES = $0.45
            PB NO = $0.52
            Total = $0.97 → Payout $1.00 → Profit $0.03 (3.1% ROI)
        """
        # Strategy 1: Poly YES + PB NO
        cost_1 = pair.poly_yes_price + pair.pb_no_price
        profit_1 = 1.0 - cost_1
        roi_1 = (profit_1 / cost_1 * 100) if cost_1 > 0 else 0
        
        # Strategy 2: Poly NO + PB YES
        cost_2 = pair.poly_no_price + pair.pb_yes_price
        profit_2 = 1.0 - cost_2
        roi_2 = (profit_2 / cost_2 * 100) if cost_2 > 0 else 0
        
        # Find better strategy
        if roi_1 >= roi_2 and roi_1 > 0:
            best_roi = roi_1
            best_profit = profit_1
            best_cost = cost_1
            poly_side = "YES"
            pb_side = "NO"
            poly_price = pair.poly_yes_price
            pb_price = pair.pb_no_price
        elif roi_2 > 0:
            best_roi = roi_2
            best_profit = profit_2
            best_cost = cost_2
            poly_side = "NO"
            pb_side = "YES"
            poly_price = pair.poly_no_price
            pb_price = pair.pb_yes_price
        else:
            return None
        
        # Check ROI thresholds
        if best_roi < self.min_roi_pct:
            # Near miss logging (> 50% of threshold)
            if best_roi > self.min_roi_pct * 0.5:
                self._near_misses += 1
                logger.info(
                    f"⚠️ NEAR_MISS [SYNTHETIC]: {best_roi:.1f}% ROI (need {self.min_roi_pct:.1f}%) | "
                    f"Poly {poly_side}@${poly_price:.3f} + PB {pb_side}@${pb_price:.3f} = ${best_cost:.3f} | "
                    f"{pair.poly_question[:40]}..."
                )
            return None
        
        if best_roi > self.max_roi_pct:
            logger.warning(f"⚠️ Suspicious ROI {best_roi:.1f}% - possible stale data: {pair.poly_question[:40]}")
            return None
        
        # Generate signal
        signal_id = f"ARB_SYNTH_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(pair.poly_condition_id) % 10000:04d}"
        
        # Calculate stakes (equal weight on both sides for hedging)
        half_stake = self.stake_size / 2
        
        return ArbSignal(
            signal_id=signal_id,
            arb_type="SYNTHETIC",
            question=pair.poly_question,
            poly_condition_id=pair.poly_condition_id,
            poly_token_id=pair.poly_token_id,
            pb_market_id=pair.pb_market_id,
            poly_side=poly_side,
            poly_price=poly_price,
            poly_stake=half_stake / poly_price,  # Shares to buy
            pb_side=pb_side,
            pb_price=pb_price,
            pb_stake=half_stake / pb_price,  # Shares to buy
            total_cost=best_cost * half_stake,
            gross_profit=best_profit * half_stake,
            roi_pct=best_roi,
            match_score=pair.match_score,
            confidence=min(0.95, pair.match_score / 100),
            paper_mode=self.paper_mode,
        )
    
    def _detect_direct_arb(self, pair: MarketPair) -> Optional[ArbSignal]:
        """
        Detect direct arbitrage opportunity.
        
        Direct arb = Same outcome priced differently
        Buy on cheaper platform, sell on expensive.
        
        NOTE: Requires ability to SHORT on one platform, which
        PredictBase may not support. This is more theoretical.
        
        Example:
            Poly YES = $0.50
            PB YES = $0.60
            Edge = 10% (buy Poly, sell PB)
        """
        # YES price difference
        yes_diff = pair.pb_yes_price - pair.poly_yes_price
        yes_diff_pct = abs(yes_diff / pair.poly_yes_price * 100) if pair.poly_yes_price > 0 else 0
        
        # NO price difference
        no_diff = pair.pb_no_price - pair.poly_no_price
        no_diff_pct = abs(no_diff / pair.poly_no_price * 100) if pair.poly_no_price > 0 else 0
        
        # Find better opportunity
        if yes_diff_pct >= no_diff_pct and yes_diff_pct >= self.min_roi_pct:
            outcome = "YES"
            diff_pct = yes_diff_pct
            if yes_diff > 0:
                # PB is expensive, Poly is cheap → Buy Poly
                buy_exchange = "POLY"
                buy_price = pair.poly_yes_price
                sell_price = pair.pb_yes_price
            else:
                # Poly is expensive, PB is cheap → Buy PB
                buy_exchange = "PB"
                buy_price = pair.pb_yes_price
                sell_price = pair.poly_yes_price
        elif no_diff_pct >= self.min_roi_pct:
            outcome = "NO"
            diff_pct = no_diff_pct
            if no_diff > 0:
                buy_exchange = "POLY"
                buy_price = pair.poly_no_price
                sell_price = pair.pb_no_price
            else:
                buy_exchange = "PB"
                buy_price = pair.pb_no_price
                sell_price = pair.poly_no_price
        else:
            return None
        
        # Direct arb is harder to execute (need to short/sell on one side)
        # For now, log but don't generate actionable signal
        logger.info(
            f"📊 DIRECT_ARB: {diff_pct:.1f}% edge on {outcome} | "
            f"Buy {buy_exchange}@${buy_price:.3f}, Sell@${sell_price:.3f} | "
            f"{pair.poly_question[:40]}..."
        )
        
        # Could return signal here if execution supported
        return None
    
    async def scan(self, poly_markets: List[Dict] = None, use_targeted: bool = True) -> List[ArbSignal]:
        """
        Scan for arbitrage opportunities.
        
        Args:
            poly_markets: List of Polymarket market dicts (optional - will fetch if None)
            use_targeted: If True and poly_markets is None, fetch ONLY sports markets
            
        Returns:
            List of actionable ArbSignal objects
        """
        self._total_scans += 1
        signals: List[ArbSignal] = []
        
        logger.info(f"🔀 ARB SCAN #{self._total_scans} starting...")
        
        # Get PredictBase markets first (to extract keywords)
        pb_markets = await self._get_pb_markets()
        
        if not pb_markets:
            logger.warning("⚠️ No PredictBase markets available")
            return signals
        
        # Get Polymarket markets
        if poly_markets is None:
            if use_targeted:
                # SMART FETCH: Only sports markets to maximize overlap
                logger.info("🏀 Using TARGETED sports fetch for Polymarket...")
                
                # Fetch sports markets (keyword filtering only - events endpoint broken)
                poly_markets = await fetch_targeted_markets(
                    limit=500,
                    use_events=False,  # Events endpoint returns 422 errors
                    use_keyword_filter=True,
                )
            else:
                logger.warning("⚠️ No Polymarket markets provided and targeted=False")
                return signals
        
        if not poly_markets:
            logger.warning("⚠️ No Polymarket markets available")
            return signals
        
        logger.info(f"📊 Comparing {len(poly_markets)} Poly vs {len(pb_markets)} PB markets")
        
        # Batch match markets
        pairs = batch_match_markets(
            poly_markets=poly_markets,
            pb_markets=pb_markets,
            threshold=self.fuzzy_threshold,
            max_matches=200  # Limit for performance
        )
        
        if not pairs:
            logger.info("📭 No matching market pairs found")
            return signals
        
        logger.info(f"🔍 Analyzing {len(pairs)} market pairs for arbitrage...")
        
        # Detect arbitrage in each pair
        for pair in pairs:
            # Check synthetic arb (main opportunity)
            synth_signal = self._detect_synthetic_arb(pair)
            if synth_signal:
                signals.append(synth_signal)
                self._total_signals += 1
            
            # Check direct arb (informational)
            self._detect_direct_arb(pair)
        
        # Log results
        if signals:
            logger.info(f"💰 Found {len(signals)} ARB opportunities!")
            for sig in signals[:3]:  # Log top 3
                logger.info(
                    f"   → {sig.arb_type}: {sig.roi_pct:.1f}% ROI | "
                    f"{sig.poly_side}@${sig.poly_price:.3f} + {sig.pb_side}@${sig.pb_price:.3f} | "
                    f"{sig.question[:40]}..."
                )
        else:
            logger.info(f"📭 No ARB opportunities (near misses: {self._near_misses})")
        
        return signals
    
    async def scan_targeted(self) -> List[ArbSignal]:
        """
        Convenience method: Scan using targeted sports fetch.
        
        This is the recommended way to run ARB scanning for maximum
        overlap between Polymarket and PredictBase.
        """
        return await self.scan(poly_markets=None, use_targeted=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scanner statistics."""
        return {
            "total_scans": self._total_scans,
            "total_signals": self._total_signals,
            "near_misses": self._near_misses,
            "pb_markets_cached": len(self._pb_markets_cache),
            "min_roi_pct": self.min_roi_pct,
            "fuzzy_threshold": self.fuzzy_threshold,
            "paper_mode": self.paper_mode,
        }


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────────────

async def test_arb_scanner():
    """Test the ARB scanner standalone with TARGETED sports fetch."""
    
    print("=" * 70)
    print("       ARB SCANNER TEST (TARGETED SPORTS FETCH)")
    print("=" * 70)
    print()
    
    # Run ARB scanner with targeted fetch
    print("🏀 Running ARB scanner with TARGETED sports fetch...")
    print("   This will fetch ONLY sports markets from Polymarket")
    print("   to maximize overlap with PredictBase (sports-heavy)")
    print()
    
    async with ARBScanner(min_roi_pct=2.5, fuzzy_threshold=70, paper_mode=True) as scanner:
        # Use the new targeted scan method
        signals = await scanner.scan_targeted()
        
        print()
        print("=" * 70)
        print(f"RESULTS: {len(signals)} ARB signals")
        print("=" * 70)
        
        for sig in signals:
            print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ {sig.arb_type} ARBITRAGE - {sig.roi_pct:.1f}% ROI
╠══════════════════════════════════════════════════════════════════════════════╣
║ Question: {sig.question[:60]}...
║ 
║ POLYMARKET: {sig.poly_side} @ ${sig.poly_price:.3f}
║ PREDICTBASE: {sig.pb_side} @ ${sig.pb_price:.3f}
║ 
║ Total Cost: ${sig.total_cost:.2f}
║ Gross Profit: ${sig.gross_profit:.2f}
║ Match Score: {sig.match_score:.0f}/100
╚══════════════════════════════════════════════════════════════════════════════╝
""")
        
        print()
        print("Scanner stats:", scanner.get_stats())


async def test_targeted_fetch():
    """Test the targeted sports fetch function."""
    
    print("=" * 70)
    print("       TARGETED SPORTS FETCH TEST")
    print("=" * 70)
    print()
    
    # Test fetching sports markets
    markets = await fetch_targeted_markets(
        categories=["sports", "basketball", "football", "soccer", "hockey", "esports"],
        limit=50,
    )
    
    print(f"\n📊 Fetched {len(markets)} sports markets from Polymarket:\n")
    
    for m in markets[:20]:
        q = m.get('question', '')[:70]
        vol = float(m.get('volume', 0))
        print(f"  [${vol/1000:.0f}k] {q}...")
    
    print(f"\n... and {len(markets) - 20} more")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--fetch-only":
        asyncio.run(test_targeted_fetch())
    else:
        asyncio.run(test_arb_scanner())
