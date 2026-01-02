#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     MARKET UNIVERSE MAPPER v1.0                               ║
║            Deep Dive Analysis: PredictBase ↔ Polymarket                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

Forensic analysis tool to map the complete intersection between 
PredictBase and Polymarket prediction markets.

Author: PolyBot Team
Date: January 2026
"""

import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
import pandas as pd
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Fuzzy matching
try:
    from thefuzz import fuzz, process
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    print("⚠️ Install thefuzz: pip install thefuzz[speedup]")

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

console = Console()

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    # API Endpoints
    "GAMMA_API": "https://gamma-api.polymarket.com",
    "PREDICTBASE_API": "https://predictbase.app/api",
    
    # Extraction limits (set high for deep dive)
    "POLY_MAX_MARKETS": 10000,
    "POLY_BATCH_SIZE": 100,
    "PB_MAX_PAGES": 100,
    
    # Matching thresholds
    "FUZZY_THRESHOLD_EXACT": 90,     # Very high confidence match
    "FUZZY_THRESHOLD_HIGH": 80,      # Good match
    "FUZZY_THRESHOLD_MEDIUM": 70,    # Possible match
    "FUZZY_THRESHOLD_LOW": 60,       # Weak match
    
    # Date tolerance for same-event detection (hours)
    "DATE_TOLERANCE_HOURS": 48,
    
    # Minimum spread for arbitrage (%)
    "MIN_ARB_SPREAD": 2.0,
    
    # Rate limiting
    "REQUEST_DELAY": 0.1,  # seconds between requests
    
    # Output
    "OUTPUT_DIR": PROJECT_ROOT / "analysis",
    "REPORT_FILE": "market_intersection_report.md",
    "DATA_FILE": "market_data.json",
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Market:
    """Unified market representation."""
    id: str
    question: str
    source: str  # "POLY" or "PB"
    category: str
    yes_price: float
    no_price: float
    volume: float
    end_date: Optional[datetime]
    status: str  # "active", "resolved", "closed"
    raw_data: Dict = field(default_factory=dict)
    
    # Normalized fields for matching
    clean_question: str = ""
    tokens: Set[str] = field(default_factory=set)


@dataclass
class MarketMatch:
    """Matched market pair."""
    poly_market: Market
    pb_market: Market
    similarity_score: float
    match_type: str  # "EXACT", "HIGH", "MEDIUM", "LOW", "MISMATCH_TYPE"
    price_spread: float  # YES price difference
    arb_opportunity: bool
    notes: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

# Stopwords to remove for better matching
STOPWORDS = {
    'will', 'the', 'be', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of',
    'by', 'this', 'that', 'it', 'is', 'are', 'was', 'were', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'but', 'and', 'or', 'if',
    'than', 'more', 'most', 'some', 'any', 'each', 'which', 'who', 'whom',
    'what', 'when', 'where', 'why', 'how', 'all', 'both', 'few', 'other',
    'such', 'only', 'own', 'same', 'so', 'can', 'just', 'should', 'now',
    'vs', 'versus', 'against'
}

# Category mappings
CATEGORY_ALIASES = {
    # PredictBase → Polymarket category mapping
    "sports": ["sports", "nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball"],
    "politics": ["politics", "election", "president", "congress", "senate"],
    "crypto": ["crypto", "bitcoin", "ethereum", "btc", "eth", "defi"],
    "entertainment": ["entertainment", "movies", "tv", "oscars", "emmys"],
    "science": ["science", "space", "ai", "technology"],
    "economics": ["economics", "inflation", "gdp", "fed", "rates"],
}


def clean_text(text: str) -> str:
    """Normalize text for matching."""
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Remove dates in various formats
    text = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '', text)
    text = re.sub(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\d{4}\b', '', text)  # Years
    
    # Remove special chars but keep spaces
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Collapse whitespace
    text = ' '.join(text.split())
    
    return text.strip()


def tokenize(text: str) -> Set[str]:
    """Extract meaningful tokens from text."""
    clean = clean_text(text)
    tokens = set(clean.split()) - STOPWORDS
    # Keep only tokens with 2+ chars
    return {t for t in tokens if len(t) >= 2}


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate fuzzy similarity between two texts."""
    if not FUZZY_AVAILABLE:
        # Fallback: Jaccard similarity
        tokens1 = tokenize(text1)
        tokens2 = tokenize(text2)
        if not tokens1 or not tokens2:
            return 0.0
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        return (intersection / union) * 100 if union > 0 else 0.0
    
    # Use thefuzz token_sort_ratio (handles word reordering)
    clean1 = clean_text(text1)
    clean2 = clean_text(text2)
    
    # Combine multiple similarity metrics
    ratio = fuzz.ratio(clean1, clean2)
    token_sort = fuzz.token_sort_ratio(clean1, clean2)
    token_set = fuzz.token_set_ratio(clean1, clean2)
    
    # Weighted average (token_set best for different lengths)
    return (ratio * 0.2 + token_sort * 0.4 + token_set * 0.4)


def detect_category(question: str) -> str:
    """Detect market category from question text."""
    q_lower = question.lower()
    
    for category, keywords in CATEGORY_ALIASES.items():
        if any(kw in q_lower for kw in keywords):
            return category
    
    return "other"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: PREDICTBASE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

class PredictBaseExtractor:
    """Deep extractor for PredictBase markets."""
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.markets: List[Market] = []
        self.categories_found: Set[str] = set()
        self.endpoints_discovered: List[str] = []
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=60)
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    async def discover_endpoints(self) -> List[str]:
        """Discover all available PredictBase API endpoints."""
        console.print("[cyan]🔍 Discovering PredictBase API endpoints...[/cyan]")
        
        # Known endpoints to try
        potential_endpoints = [
            "/api/get_recent_markets_v2",
            "/api/get_resolved_markets_v2",
            "/api/get_markets",
            "/api/markets",
            "/api/get_all_markets",
            "/api/categories",
            "/api/get_categories",
            "/api/sports",
            "/api/crypto",
            "/api/politics",
        ]
        
        valid_endpoints = []
        
        for endpoint in potential_endpoints:
            try:
                url = f"{CONFIG['PREDICTBASE_API'].replace('/api', '')}{endpoint}"
                resp = await self.client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    count = len(data) if isinstance(data, list) else 1
                    valid_endpoints.append((endpoint, count))
                    console.print(f"  ✅ {endpoint} → {count} items")
                await asyncio.sleep(CONFIG["REQUEST_DELAY"])
            except Exception as e:
                pass  # Endpoint doesn't exist
        
        self.endpoints_discovered = valid_endpoints
        return valid_endpoints
    
    async def extract_all_markets(self, progress: Progress) -> List[Market]:
        """Extract all markets from PredictBase."""
        task = progress.add_task("[cyan]Extracting PredictBase markets...", total=3)
        
        all_markets = []
        seen_ids = set()
        
        # Endpoint 1: Recent markets
        try:
            resp = await self.client.get(f"{CONFIG['PREDICTBASE_API']}/get_recent_markets_v2")
            if resp.status_code == 200:
                data = resp.json()
                for m in data:
                    market = self._parse_market(m, "active")
                    if market and market.id not in seen_ids:
                        seen_ids.add(market.id)
                        all_markets.append(market)
                console.print(f"  📥 Recent markets: {len(data)}")
        except Exception as e:
            console.print(f"  ⚠️ Recent markets error: {e}")
        
        progress.update(task, advance=1)
        await asyncio.sleep(CONFIG["REQUEST_DELAY"])
        
        # Endpoint 2: Resolved markets (paginated if possible)
        try:
            resp = await self.client.get(f"{CONFIG['PREDICTBASE_API']}/get_resolved_markets_v2")
            if resp.status_code == 200:
                data = resp.json()
                for m in data:
                    market = self._parse_market(m, "resolved")
                    if market and market.id not in seen_ids:
                        seen_ids.add(market.id)
                        all_markets.append(market)
                console.print(f"  📥 Resolved markets: {len(data)}")
        except Exception as e:
            console.print(f"  ⚠️ Resolved markets error: {e}")
        
        progress.update(task, advance=1)
        
        # Try additional endpoints
        for endpoint, _ in self.endpoints_discovered:
            if endpoint not in ["/api/get_recent_markets_v2", "/api/get_resolved_markets_v2"]:
                try:
                    url = f"{CONFIG['PREDICTBASE_API'].replace('/api', '')}{endpoint}"
                    resp = await self.client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            count = 0
                            for m in data:
                                market = self._parse_market(m, "unknown")
                                if market and market.id not in seen_ids:
                                    seen_ids.add(market.id)
                                    all_markets.append(market)
                                    count += 1
                            if count > 0:
                                console.print(f"  📥 {endpoint}: {count} new")
                    await asyncio.sleep(CONFIG["REQUEST_DELAY"])
                except:
                    pass
        
        progress.update(task, advance=1)
        
        self.markets = all_markets
        
        # Collect categories
        for m in all_markets:
            self.categories_found.add(m.category)
        
        return all_markets
    
    def _parse_market(self, data: Dict, status: str) -> Optional[Market]:
        """Parse PredictBase market data into Market object."""
        try:
            # Extract question (try multiple fields)
            question = (
                data.get("title") or 
                data.get("question") or 
                data.get("name") or 
                data.get("description") or
                ""
            )
            
            if not question:
                return None
            
            # Extract ID
            market_id = str(
                data.get("id") or 
                data.get("market_id") or 
                data.get("_id") or
                hash(question)
            )
            
            # Extract prices (handle micro-units)
            yes_price = data.get("yes_price") or data.get("yesPrice") or 0
            no_price = data.get("no_price") or data.get("noPrice") or 0
            
            # Convert from micro-units if needed (> 1.0)
            if yes_price > 1:
                yes_price = yes_price / 1_000_000
            if no_price > 1:
                no_price = no_price / 1_000_000
            
            # If no_price is 0, calculate from yes
            if no_price == 0 and yes_price > 0:
                no_price = 1 - yes_price
            
            # Extract volume
            volume = float(data.get("volume") or data.get("total_volume") or 0)
            
            # Extract end date
            end_date = None
            date_str = data.get("end_date") or data.get("endDate") or data.get("resolution_date")
            if date_str:
                try:
                    end_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except:
                    pass
            
            # Detect category
            category = data.get("category") or detect_category(question)
            
            market = Market(
                id=f"PB_{market_id}",
                question=question,
                source="PB",
                category=category,
                yes_price=float(yes_price),
                no_price=float(no_price),
                volume=volume,
                end_date=end_date,
                status=status,
                raw_data=data,
                clean_question=clean_text(question),
                tokens=tokenize(question),
            )
            
            return market
            
        except Exception as e:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: POLYMARKET EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

class PolymarketExtractor:
    """Deep extractor for Polymarket markets via Gamma API."""
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.markets: List[Market] = []
        self.categories_found: Set[str] = set()
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=60)
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    async def extract_all_markets(self, progress: Progress) -> List[Market]:
        """Extract complete market snapshot from Polymarket."""
        total_batches = CONFIG["POLY_MAX_MARKETS"] // CONFIG["POLY_BATCH_SIZE"]
        task = progress.add_task("[green]Extracting Polymarket markets...", total=total_batches)
        
        all_markets = []
        seen_ids = set()
        offset = 0
        consecutive_empty = 0
        
        while offset < CONFIG["POLY_MAX_MARKETS"]:
            try:
                resp = await self.client.get(
                    f"{CONFIG['GAMMA_API']}/markets",
                    params={
                        "limit": CONFIG["POLY_BATCH_SIZE"],
                        "offset": offset,
                    }
                )
                
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                
                if not data:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break  # No more markets
                else:
                    consecutive_empty = 0
                
                for m in data:
                    market = self._parse_market(m)
                    if market and market.id not in seen_ids:
                        seen_ids.add(market.id)
                        all_markets.append(market)
                
                offset += CONFIG["POLY_BATCH_SIZE"]
                progress.update(task, advance=1)
                
                await asyncio.sleep(CONFIG["REQUEST_DELAY"])
                
            except Exception as e:
                console.print(f"  ⚠️ Batch error at offset {offset}: {e}")
                break
        
        # Complete progress
        progress.update(task, completed=total_batches)
        
        self.markets = all_markets
        
        # Collect categories
        for m in all_markets:
            self.categories_found.add(m.category)
        
        console.print(f"  📥 Total Polymarket markets: {len(all_markets)}")
        
        return all_markets
    
    def _parse_market(self, data: Dict) -> Optional[Market]:
        """Parse Polymarket market data into Market object."""
        try:
            question = data.get("question") or ""
            if not question:
                return None
            
            # Extract ID
            market_id = (
                data.get("conditionId") or 
                data.get("condition_id") or 
                data.get("id") or
                str(hash(question))
            )
            
            # Extract prices
            outcome_prices = data.get("outcomePrices")
            if isinstance(outcome_prices, str):
                try:
                    prices = json.loads(outcome_prices)
                    yes_price = float(prices[0]) if prices else 0.5
                except:
                    yes_price = 0.5
            elif isinstance(outcome_prices, list):
                yes_price = float(outcome_prices[0]) if outcome_prices else 0.5
            else:
                yes_price = float(data.get("yes_price") or 0.5)
            
            no_price = 1 - yes_price
            
            # Volume
            volume = float(data.get("volume") or data.get("volume24hr") or 0)
            
            # End date
            end_date = None
            date_str = data.get("endDate") or data.get("end_date")
            if date_str:
                try:
                    end_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except:
                    pass
            
            # Status
            active = data.get("active", True)
            closed = data.get("closed", False)
            status = "active" if active and not closed else "closed"
            
            # Category
            category = detect_category(question)
            
            market = Market(
                id=f"POLY_{market_id}",
                question=question,
                source="POLY",
                category=category,
                yes_price=yes_price,
                no_price=no_price,
                volume=volume,
                end_date=end_date,
                status=status,
                raw_data=data,
                clean_question=clean_text(question),
                tokens=tokenize(question),
            )
            
            return market
            
        except Exception as e:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: MATCHING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class MarketMatcher:
    """CPU-intensive market matching engine."""
    
    def __init__(self, poly_markets: List[Market], pb_markets: List[Market]):
        self.poly_markets = poly_markets
        self.pb_markets = pb_markets
        self.matches: List[MarketMatch] = []
        self.stats = defaultdict(int)
    
    def run_matching(self, progress: Progress) -> List[MarketMatch]:
        """Run full matching algorithm."""
        task = progress.add_task(
            "[yellow]Matching markets (CPU intensive)...", 
            total=len(self.poly_markets)
        )
        
        matches = []
        
        # Pre-compute PB data for efficiency
        pb_questions = [(m, m.clean_question) for m in self.pb_markets]
        
        for poly_market in self.poly_markets:
            best_match = None
            best_score = 0
            
            # Find best PB match for this Poly market
            for pb_market, pb_clean in pb_questions:
                score = calculate_similarity(poly_market.clean_question, pb_clean)
                
                if score > best_score:
                    best_score = score
                    best_match = pb_market
            
            # Classify match
            if best_score >= CONFIG["FUZZY_THRESHOLD_LOW"] and best_match:
                match = self._create_match(poly_market, best_match, best_score)
                matches.append(match)
                self.stats[match.match_type] += 1
            
            progress.update(task, advance=1)
        
        # Sort by score
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        self.matches = matches
        return matches
    
    def _create_match(self, poly: Market, pb: Market, score: float) -> MarketMatch:
        """Create a MarketMatch object with classification."""
        # Determine match type
        if score >= CONFIG["FUZZY_THRESHOLD_EXACT"]:
            match_type = "EXACT"
        elif score >= CONFIG["FUZZY_THRESHOLD_HIGH"]:
            match_type = "HIGH"
        elif score >= CONFIG["FUZZY_THRESHOLD_MEDIUM"]:
            match_type = "MEDIUM"
        else:
            match_type = "LOW"
        
        # Check for date mismatch (futures vs spot)
        if poly.end_date and pb.end_date:
            date_diff = abs((poly.end_date - pb.end_date).total_seconds() / 3600)
            if date_diff > CONFIG["DATE_TOLERANCE_HOURS"] and score >= CONFIG["FUZZY_THRESHOLD_HIGH"]:
                match_type = "MISMATCH_TYPE"
        
        # Calculate price spread
        price_spread = abs(poly.yes_price - pb.yes_price) * 100  # Convert to %
        
        # Determine if arbitrage opportunity
        arb_opportunity = (
            match_type in ["EXACT", "HIGH"] and
            price_spread >= CONFIG["MIN_ARB_SPREAD"] and
            poly.status == "active" and
            pb.status == "active"
        )
        
        # Notes
        notes = []
        if arb_opportunity:
            notes.append(f"💰 ARB: {price_spread:.1f}% spread")
        if match_type == "MISMATCH_TYPE":
            notes.append("⚠️ Different event dates")
        
        return MarketMatch(
            poly_market=poly,
            pb_market=pb,
            similarity_score=score,
            match_type=match_type,
            price_spread=price_spread,
            arb_opportunity=arb_opportunity,
            notes=" | ".join(notes),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4: REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class ReportGenerator:
    """Generate comprehensive analysis report."""
    
    def __init__(
        self, 
        poly_markets: List[Market], 
        pb_markets: List[Market],
        matches: List[MarketMatch],
        pb_categories: Set[str],
        poly_categories: Set[str],
    ):
        self.poly_markets = poly_markets
        self.pb_markets = pb_markets
        self.matches = matches
        self.pb_categories = pb_categories
        self.poly_categories = poly_categories
    
    def generate_markdown_report(self) -> str:
        """Generate complete markdown report."""
        report = []
        
        # Header
        report.append("# 🔬 Market Universe Analysis Report")
        report.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"\n**Analysis Tool:** Market Universe Mapper v1.0")
        report.append("\n---\n")
        
        # Executive Summary
        report.append("## 📊 Executive Summary\n")
        report.append(self._generate_summary())
        
        # Category Heat Map
        report.append("\n## 🗺️ Category Heat Map\n")
        report.append(self._generate_heatmap())
        
        # The Gold Mine (ARB opportunities)
        report.append("\n## 💰 The Gold Mine: Arbitrage Opportunities\n")
        report.append(self._generate_goldmine())
        
        # High Confidence Matches
        report.append("\n## 🎯 High Confidence Matches (>80%)\n")
        report.append(self._generate_high_matches())
        
        # Medium Matches
        report.append("\n## 📋 Medium Confidence Matches (70-80%)\n")
        report.append(self._generate_medium_matches())
        
        # Mismatch Analysis
        report.append("\n## ⚠️ Type Mismatches (Futures vs Spot)\n")
        report.append(self._generate_mismatches())
        
        # Bot Configuration Recommendations
        report.append("\n## 🤖 Bot Configuration Recommendations\n")
        report.append(self._generate_recommendations())
        
        # Raw Data Summary
        report.append("\n## 📁 Data Summary\n")
        report.append(self._generate_data_summary())
        
        return "\n".join(report)
    
    def _generate_summary(self) -> str:
        """Generate executive summary section."""
        total_matches = len(self.matches)
        exact_matches = len([m for m in self.matches if m.match_type == "EXACT"])
        high_matches = len([m for m in self.matches if m.match_type == "HIGH"])
        arb_opportunities = len([m for m in self.matches if m.arb_opportunity])
        
        lines = [
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| **Polymarket Markets** | {len(self.poly_markets):,} |",
            f"| **PredictBase Markets** | {len(self.pb_markets):,} |",
            f"| **Total Potential Matches** | {total_matches:,} |",
            f"| **Exact Matches (>90%)** | {exact_matches:,} |",
            f"| **High Matches (80-90%)** | {high_matches:,} |",
            f"| **🚨 Arbitrage Opportunities** | {arb_opportunities:,} |",
            f"| **Coverage Rate** | {(total_matches/len(self.poly_markets)*100) if self.poly_markets else 0:.1f}% |",
        ]
        
        return "\n".join(lines)
    
    def _generate_heatmap(self) -> str:
        """Generate category overlap heatmap."""
        # Count matches by category
        category_counts = defaultdict(lambda: {"poly": 0, "pb": 0, "matches": 0})
        
        for m in self.poly_markets:
            category_counts[m.category]["poly"] += 1
        
        for m in self.pb_markets:
            category_counts[m.category]["pb"] += 1
        
        for match in self.matches:
            category_counts[match.poly_market.category]["matches"] += 1
        
        lines = [
            "| Category | Polymarket | PredictBase | Matches | Match Rate |",
            "|----------|------------|-------------|---------|------------|",
        ]
        
        for cat in sorted(category_counts.keys()):
            counts = category_counts[cat]
            rate = (counts["matches"] / counts["poly"] * 100) if counts["poly"] > 0 else 0
            emoji = "🔥" if rate > 10 else "✅" if rate > 5 else "⚪"
            lines.append(
                f"| {emoji} {cat.title()} | {counts['poly']:,} | {counts['pb']:,} | {counts['matches']:,} | {rate:.1f}% |"
            )
        
        return "\n".join(lines)
    
    def _generate_goldmine(self) -> str:
        """Generate arbitrage opportunities section."""
        arb_matches = [m for m in self.matches if m.arb_opportunity]
        
        if not arb_matches:
            return "_No arbitrage opportunities found with current thresholds._\n"
        
        lines = [
            "### Active Arbitrage Opportunities\n",
            "| Poly Question | PB Question | Poly YES | PB YES | Spread | ROI |",
            "|--------------|-------------|----------|--------|--------|-----|",
        ]
        
        for match in arb_matches[:20]:  # Top 20
            poly_q = match.poly_market.question[:40] + "..." if len(match.poly_market.question) > 40 else match.poly_market.question
            pb_q = match.pb_market.question[:40] + "..." if len(match.pb_market.question) > 40 else match.pb_market.question
            roi = match.price_spread  # Simplified ROI
            
            lines.append(
                f"| {poly_q} | {pb_q} | ${match.poly_market.yes_price:.3f} | ${match.pb_market.yes_price:.3f} | {match.price_spread:.1f}% | {roi:.1f}% |"
            )
        
        if len(arb_matches) > 20:
            lines.append(f"\n_...and {len(arb_matches) - 20} more opportunities_\n")
        
        return "\n".join(lines)
    
    def _generate_high_matches(self) -> str:
        """Generate high confidence matches section."""
        high = [m for m in self.matches if m.match_type in ["EXACT", "HIGH"]]
        
        if not high:
            return "_No high confidence matches found._\n"
        
        lines = [
            "| Score | Poly Question | PB Question | Status |",
            "|-------|--------------|-------------|--------|",
        ]
        
        for match in high[:30]:
            poly_q = match.poly_market.question[:50]
            pb_q = match.pb_market.question[:50]
            status = "🟢" if match.poly_market.status == "active" else "⚪"
            
            lines.append(f"| {match.similarity_score:.0f}% | {poly_q} | {pb_q} | {status} |")
        
        return "\n".join(lines)
    
    def _generate_medium_matches(self) -> str:
        """Generate medium confidence matches section."""
        medium = [m for m in self.matches if m.match_type == "MEDIUM"]
        
        if not medium:
            return "_No medium confidence matches found._\n"
        
        lines = [
            f"_Found {len(medium)} medium confidence matches (70-80% similarity)_\n",
            "| Score | Poly Question | PB Question |",
            "|-------|--------------|-------------|",
        ]
        
        for match in medium[:20]:
            poly_q = match.poly_market.question[:50]
            pb_q = match.pb_market.question[:50]
            lines.append(f"| {match.similarity_score:.0f}% | {poly_q} | {pb_q} |")
        
        return "\n".join(lines)
    
    def _generate_mismatches(self) -> str:
        """Generate type mismatch analysis."""
        mismatches = [m for m in self.matches if m.match_type == "MISMATCH_TYPE"]
        
        if not mismatches:
            return "_No type mismatches detected._\n"
        
        lines = [
            "These pairs have high textual similarity but different event dates (likely Futures vs Spot):\n",
            "| Poly Question | PB Question | Poly Date | PB Date |",
            "|--------------|-------------|-----------|---------|",
        ]
        
        for match in mismatches[:15]:
            poly_date = match.poly_market.end_date.strftime("%Y-%m-%d") if match.poly_market.end_date else "N/A"
            pb_date = match.pb_market.end_date.strftime("%Y-%m-%d") if match.pb_market.end_date else "N/A"
            
            lines.append(
                f"| {match.poly_market.question[:40]} | {match.pb_market.question[:40]} | {poly_date} | {pb_date} |"
            )
        
        return "\n".join(lines)
    
    def _generate_recommendations(self) -> str:
        """Generate bot configuration recommendations."""
        # Analyze which categories have best overlap
        category_scores = defaultdict(float)
        category_counts = defaultdict(int)
        
        for match in self.matches:
            if match.match_type in ["EXACT", "HIGH"]:
                category_scores[match.poly_market.category] += match.similarity_score
                category_counts[match.poly_market.category] += 1
        
        # Sort by total score
        ranked = sorted(
            [(cat, category_scores[cat], category_counts[cat]) 
             for cat in category_scores.keys()],
            key=lambda x: x[1],
            reverse=True
        )
        
        lines = [
            "### Recommended Categories for ARB Scanning\n",
            "Based on overlap analysis, prioritize these categories:\n",
        ]
        
        for i, (cat, score, count) in enumerate(ranked[:5], 1):
            avg = score / count if count > 0 else 0
            lines.append(f"{i}. **{cat.title()}** - {count} matches, avg similarity: {avg:.1f}%")
        
        lines.append("\n### Suggested Configuration\n")
        lines.append("```python")
        lines.append("# Recommended scanner configuration")
        lines.append("SCANNER_CONFIG = {")
        lines.append(f"    'target_categories': {[cat for cat, _, _ in ranked[:3]]},")
        lines.append(f"    'fuzzy_threshold': {CONFIG['FUZZY_THRESHOLD_HIGH']},")
        lines.append(f"    'min_arb_spread': {CONFIG['MIN_ARB_SPREAD']},")
        lines.append("}")
        lines.append("```")
        
        return "\n".join(lines)
    
    def _generate_data_summary(self) -> str:
        """Generate raw data summary."""
        lines = [
            "### PredictBase Categories Found\n",
            f"```\n{sorted(self.pb_categories)}\n```\n",
            "### Polymarket Categories Detected\n", 
            f"```\n{sorted(self.poly_categories)}\n```\n",
            "### Match Type Distribution\n",
        ]
        
        type_counts = defaultdict(int)
        for m in self.matches:
            type_counts[m.match_type] += 1
        
        for mtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {mtype}: {count}")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    """Main orchestration function."""
    console.print(Panel.fit(
        "[bold cyan]MARKET UNIVERSE MAPPER[/bold cyan]\n"
        "[dim]Deep Dive Analysis: PredictBase ↔ Polymarket[/dim]",
        border_style="cyan"
    ))
    
    start_time = time.time()
    
    # Ensure output directory exists
    CONFIG["OUTPUT_DIR"].mkdir(exist_ok=True)
    
    # Storage
    poly_markets: List[Market] = []
    pb_markets: List[Market] = []
    matches: List[MarketMatch] = []
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 1: PredictBase Extraction
    # ═══════════════════════════════════════════════════════════════════════════
    console.print("\n[bold]═══ PHASE 1: PredictBase Extraction ═══[/bold]\n")
    
    async with PredictBaseExtractor() as pb_extractor:
        await pb_extractor.discover_endpoints()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            pb_markets = await pb_extractor.extract_all_markets(progress)
        
        pb_categories = pb_extractor.categories_found
    
    console.print(f"[green]✅ PredictBase: {len(pb_markets):,} markets extracted[/green]")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 2: Polymarket Extraction
    # ═══════════════════════════════════════════════════════════════════════════
    console.print("\n[bold]═══ PHASE 2: Polymarket Extraction ═══[/bold]\n")
    
    async with PolymarketExtractor() as poly_extractor:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            poly_markets = await poly_extractor.extract_all_markets(progress)
        
        poly_categories = poly_extractor.categories_found
    
    console.print(f"[green]✅ Polymarket: {len(poly_markets):,} markets extracted[/green]")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 3: Matching Engine
    # ═══════════════════════════════════════════════════════════════════════════
    console.print("\n[bold]═══ PHASE 3: Market Matching (CPU Intensive) ═══[/bold]\n")
    
    if not FUZZY_AVAILABLE:
        console.print("[red]❌ thefuzz not installed! Run: pip install thefuzz[speedup][/red]")
        return
    
    matcher = MarketMatcher(poly_markets, pb_markets)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        matches = matcher.run_matching(progress)
    
    console.print(f"[green]✅ Found {len(matches):,} potential matches[/green]")
    
    # Show match stats
    table = Table(title="Match Distribution")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right")
    
    for mtype, count in sorted(matcher.stats.items(), key=lambda x: -x[1]):
        table.add_row(mtype, str(count))
    
    console.print(table)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 4: Report Generation
    # ═══════════════════════════════════════════════════════════════════════════
    console.print("\n[bold]═══ PHASE 4: Report Generation ═══[/bold]\n")
    
    reporter = ReportGenerator(
        poly_markets=poly_markets,
        pb_markets=pb_markets,
        matches=matches,
        pb_categories=pb_categories,
        poly_categories=poly_categories,
    )
    
    # Generate markdown report
    report = reporter.generate_markdown_report()
    report_path = CONFIG["OUTPUT_DIR"] / CONFIG["REPORT_FILE"]
    report_path.write_text(report, encoding="utf-8")
    console.print(f"[green]✅ Report saved: {report_path}[/green]")
    
    # Save raw data
    data = {
        "generated_at": datetime.now().isoformat(),
        "poly_count": len(poly_markets),
        "pb_count": len(pb_markets),
        "match_count": len(matches),
        "matches": [
            {
                "poly_question": m.poly_market.question,
                "poly_id": m.poly_market.id,
                "poly_yes_price": m.poly_market.yes_price,
                "pb_question": m.pb_market.question,
                "pb_id": m.pb_market.id,
                "pb_yes_price": m.pb_market.yes_price,
                "similarity": m.similarity_score,
                "match_type": m.match_type,
                "spread": m.price_spread,
                "arb_opportunity": m.arb_opportunity,
            }
            for m in matches
        ],
        "poly_categories": list(poly_categories),
        "pb_categories": list(pb_categories),
    }
    
    data_path = CONFIG["OUTPUT_DIR"] / CONFIG["DATA_FILE"]
    data_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(f"[green]✅ Data saved: {data_path}[/green]")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════════════════
    elapsed = time.time() - start_time
    
    console.print(Panel.fit(
        f"[bold green]✅ ANALYSIS COMPLETE[/bold green]\n\n"
        f"[cyan]Markets Analyzed:[/cyan] {len(poly_markets) + len(pb_markets):,}\n"
        f"[cyan]Matches Found:[/cyan] {len(matches):,}\n"
        f"[cyan]ARB Opportunities:[/cyan] {len([m for m in matches if m.arb_opportunity]):,}\n"
        f"[cyan]Time Elapsed:[/cyan] {elapsed:.1f}s\n\n"
        f"[dim]Report: {report_path}[/dim]",
        border_style="green"
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Analysis interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        raise
