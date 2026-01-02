#!/usr/bin/env python3
"""
🔬 AUDIT MARKET - Forensic Diagnostic Tool
==========================================
Diagnoses why the bot is not generating trades or near-misses.

Features:
1. Fetches real market data from Gamma API
2. Traces decision logic through ALL 3 strategies
3. Prints exact comparisons with PASS/FAIL
4. Verifies data types (str vs float bugs)
5. Tests Near Miss mechanism with injected data

Usage:
    # Test a random active market
    python tools/audit_market.py
    
    # Test a specific market by condition ID
    python tools/audit_market.py --market 0x19ee98e348c0ccb341d1b9566fa14521566e9b...
    
    # Test Near Miss injection
    python tools/audit_market.py --test-near-miss
    
    # Verbose mode (even more detail)
    python tools/audit_market.py --verbose

Author: Debug Tool for Polybot
"""

import asyncio
import argparse
import json
import sys
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

# =============================================================================
# COLORS FOR OUTPUT
# =============================================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    
    @staticmethod
    def ok(text): return f"{Colors.GREEN}✅ {text}{Colors.ENDC}"
    @staticmethod
    def fail(text): return f"{Colors.RED}❌ {text}{Colors.ENDC}"
    @staticmethod
    def warn(text): return f"{Colors.YELLOW}⚠️ {text}{Colors.ENDC}"
    @staticmethod
    def info(text): return f"{Colors.CYAN}ℹ️ {text}{Colors.ENDC}"
    @staticmethod
    def debug(text): return f"{Colors.BLUE}🔍 {text}{Colors.ENDC}"

# =============================================================================
# MARKET DATA SIMULATOR (matches actual MarketData dataclass)
# =============================================================================

@dataclass
class AuditMarketData:
    """Simulates MarketData from base_strategy.py"""
    condition_id: str
    question: str
    token_id: Optional[str]
    market_slug: str
    yes_price: float
    no_price: float
    best_bid: float
    best_ask: float
    mid_price: float
    spread_bps: float
    volume_24h: float
    hours_to_expiry: Optional[float]
    competitor_prices: Dict
    raw_data: Optional[Dict] = None
    
    def to_snapshot(self) -> Dict:
        return {
            "condition_id": self.condition_id,
            "yes_price": self.yes_price,
            "no_price": self.no_price,
            "volume_24h": self.volume_24h,
        }

# =============================================================================
# STRATEGY LOGIC REPLICATION (for debugging)
# =============================================================================

# TailStrategy thresholds (from actual code)
TAIL_CONFIG = {
    "min_price": 0.001,
    "max_price": 0.04,
    "min_multiplier": 25,
    "min_ml_score": 0.55,
    "stake_size": 2.0,
}

# Sniper thresholds
SNIPER_CONFIG = {
    "price_drop_threshold": 0.15,  # 15%
    "volume_spike_multiplier": 2.0,
    "stink_bid_min_price": 0.02,
    "stink_bid_max_price": 0.05,
    "stink_bid_min_volume": 50000,
    "min_volume_24h": 10000,
    "max_expiry_hours": 24,
}

# Arbitrage thresholds
ARB_CONFIG = {
    "min_spread_pct": 3.0,
    "max_spread_pct": 15.0,
    "fuzzy_threshold": 85,
    "min_liquidity": 1000,
}

# Category weights (from TailStrategy)
CATEGORY_WEIGHTS = {
    'crypto': 0.12, 'bitcoin': 0.10, 'ethereum': 0.08,
    'nvidia': 0.08, 'tesla': 0.10, 'apple': 0.05,
    'ai': 0.08, 'openai': 0.06, 'gpt': 0.05,
    'microsoft': 0.04, 'google': 0.04, 'amazon': 0.04,
    'trump': 0.02, 'biden': 0.01, 'election': 0.00,
    'sports': -0.05, 'nba': -0.06, 'nfl': -0.06,
    'weather': -0.03, 'celebrity': -0.02,
}

# =============================================================================
# AUDIT FUNCTIONS
# =============================================================================

def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{title}{Colors.ENDC}")
    print(f"{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_type_check(name: str, value: Any):
    """Print type verification for a variable."""
    vtype = type(value).__name__
    if vtype == 'float':
        print(f"  {Colors.ok(f'{name}: type={vtype}, value={value}')}")
    elif vtype == 'int':
        print(f"  {Colors.ok(f'{name}: type={vtype}, value={value}')}")
    elif vtype == 'str':
        try:
            float(value)
            print(f"  {Colors.warn(f'{name}: type={vtype} (should be float!), value={value}')}")
        except:
            print(f"  {Colors.info(f'{name}: type={vtype}, value={value[:50]}...')}")
    else:
        print(f"  {Colors.info(f'{name}: type={vtype}')}")

def check_comparison(name: str, left: Any, op: str, right: Any, expected: bool = None) -> bool:
    """
    Print and evaluate a comparison.
    Returns True if comparison passes (for trading).
    """
    # Ensure numeric types
    try:
        left_val = float(left) if not isinstance(left, (int, float)) else left
        right_val = float(right) if not isinstance(right, (int, float)) else right
    except (ValueError, TypeError):
        print(f"  {Colors.fail(f'{name}: TYPE ERROR - cannot compare {type(left).__name__} with {type(right).__name__}')}")
        return False
    
    # Evaluate
    if op == '<':
        result = left_val < right_val
    elif op == '>':
        result = left_val > right_val
    elif op == '<=':
        result = left_val <= right_val
    elif op == '>=':
        result = left_val >= right_val
    elif op == '==':
        result = left_val == right_val
    elif op == 'between':
        result = right_val[0] < left_val < right_val[1]
        right_val = f"({right_val[0]}, {right_val[1]})"
    else:
        result = False
    
    # Format output
    if result:
        status = Colors.ok(f"PASS")
    else:
        status = Colors.fail(f"FAIL")
    
    print(f"  [DEBUG] {name}: {left_val} {op} {right_val}? {status}")
    return result

def calculate_ml_score(question: str, yes_price: float) -> float:
    """
    Replicate TailStrategy ML scoring logic.
    """
    question_lower = question.lower()
    
    # Detect category
    detected_category = 'other'
    for category in CATEGORY_WEIGHTS.keys():
        if category in question_lower:
            detected_category = category
            break
    
    # Base score
    score = 0.50
    
    # Category weight
    score += CATEGORY_WEIGHTS.get(detected_category, 0)
    
    # Multiplier bonus
    multiplier = 1 / yes_price if yes_price > 0 else 0
    if multiplier >= 500:
        score += 0.05
    elif multiplier >= 200:
        score += 0.03
    elif multiplier >= 100:
        score += 0.02
    elif multiplier >= 50:
        score += 0.01
    
    # Question features
    if any(kw in question_lower for kw in ['crypto', 'bitcoin', 'ethereum']):
        score += 0.03
    if any(kw in question_lower for kw in ['ai', 'openai', 'gpt']):
        score += 0.02
    
    return min(max(score, 0.0), 1.0)

# =============================================================================
# STRATEGY AUDITS
# =============================================================================

def audit_tail_strategy(market: AuditMarketData, verbose: bool = False) -> Dict:
    """
    Audit TailStrategy decision process.
    Returns dict with decision tree.
    """
    print_header("🎰 TAIL STRATEGY AUDIT")
    
    result = {
        "strategy": "TAIL_BETTING_V1",
        "would_trigger": False,
        "is_near_miss": False,
        "checks": [],
    }
    
    # Extract values
    yes_price = market.yes_price
    min_price = TAIL_CONFIG["min_price"]
    max_price = TAIL_CONFIG["max_price"]
    min_multiplier = TAIL_CONFIG["min_multiplier"]
    min_ml_score = TAIL_CONFIG["min_ml_score"]
    
    print(f"Market: {market.question[:60]}...")
    print(f"Condition ID: {market.condition_id[:40]}...")
    print()
    
    # Type checks
    print(f"{Colors.BOLD}TYPE VERIFICATION:{Colors.ENDC}")
    print_type_check("yes_price", yes_price)
    print_type_check("volume_24h", market.volume_24h)
    print_type_check("best_bid", market.best_bid)
    print_type_check("best_ask", market.best_ask)
    print()
    
    # =========================================================================
    # CHECK 1: Price Range
    # =========================================================================
    print(f"{Colors.BOLD}CHECK 1: Price Range{Colors.ENDC}")
    print(f"  Required: {min_price} < yes_price < {max_price}")
    print(f"  Actual: yes_price = {yes_price}")
    
    check1_min = check_comparison("min_price < yes_price", min_price, '<', yes_price)
    check1_max = check_comparison("yes_price < max_price", yes_price, '<', max_price)
    check1_pass = check1_min and check1_max
    
    result["checks"].append({
        "name": "price_range",
        "passed": check1_pass,
        "details": f"{min_price} < {yes_price} < {max_price}"
    })
    
    # Near miss check for price
    if not check1_pass:
        near_miss_threshold = max_price * 1.5  # Up to 50% above
        if max_price <= yes_price <= near_miss_threshold:
            print(f"  {Colors.warn(f'NEAR MISS: Price ${yes_price:.4f} is close to threshold ${max_price:.4f}')}")
            result["is_near_miss"] = True
            result["near_miss_reason"] = f"Price ${yes_price:.4f} (need <${max_price:.4f})"
        print()
        return result
    print()
    
    # =========================================================================
    # CHECK 2: Multiplier
    # =========================================================================
    print(f"{Colors.BOLD}CHECK 2: Multiplier{Colors.ENDC}")
    multiplier = 1 / yes_price if yes_price > 0 else 0
    print(f"  Calculated: 1 / {yes_price} = {multiplier:.1f}x")
    
    check2_pass = check_comparison("multiplier >= min_multiplier", multiplier, '>=', min_multiplier)
    
    result["checks"].append({
        "name": "multiplier",
        "passed": check2_pass,
        "value": multiplier,
        "threshold": min_multiplier
    })
    
    if not check2_pass:
        print()
        return result
    print()
    
    # =========================================================================
    # CHECK 3: ML Score
    # =========================================================================
    print(f"{Colors.BOLD}CHECK 3: ML Score{Colors.ENDC}")
    ml_score = calculate_ml_score(market.question, yes_price)
    print(f"  Calculated ML Score: {ml_score:.2%}")
    print(f"  Components:")
    
    question_lower = market.question.lower()
    detected_category = 'other'
    for category in CATEGORY_WEIGHTS.keys():
        if category in question_lower:
            detected_category = category
            break
    print(f"    - Base: 50%")
    print(f"    - Category '{detected_category}': {CATEGORY_WEIGHTS.get(detected_category, 0):+.0%}")
    print(f"    - Multiplier bonus: +{(0.05 if multiplier >= 500 else 0.03 if multiplier >= 200 else 0.02 if multiplier >= 100 else 0.01 if multiplier >= 50 else 0):.0%}")
    
    check3_pass = check_comparison("ml_score >= min_ml_score", ml_score, '>=', min_ml_score)
    
    result["checks"].append({
        "name": "ml_score",
        "passed": check3_pass,
        "value": ml_score,
        "threshold": min_ml_score
    })
    
    # Near miss check for ML score
    if not check3_pass:
        near_miss_score = min_ml_score * 0.9  # 90% of threshold = near miss
        if ml_score >= near_miss_score:
            print(f"  {Colors.warn(f'NEAR MISS: ML Score {ml_score:.0%} close to threshold {min_ml_score:.0%}')}")
            result["is_near_miss"] = True
            result["near_miss_reason"] = f"ML Score {ml_score:.0%} (need {min_ml_score:.0%})"
        print()
        return result
    print()
    
    # =========================================================================
    # ALL CHECKS PASSED
    # =========================================================================
    print(f"{Colors.BOLD}{Colors.GREEN}🎯 ALL CHECKS PASSED - WOULD TRIGGER SIGNAL!{Colors.ENDC}")
    result["would_trigger"] = True
    result["signal_details"] = {
        "entry_price": yes_price,
        "multiplier": multiplier,
        "ml_score": ml_score,
        "stake": TAIL_CONFIG["stake_size"],
    }
    
    return result

def audit_sniper_strategy(market: AuditMarketData, verbose: bool = False) -> Dict:
    """
    Audit SniperStrategy decision process (both modes).
    """
    print_header("🎯 SNIPER STRATEGY AUDIT (DUAL MODE)")
    
    result = {
        "strategy": "SNIPER_MICRO_V1",
        "would_trigger": False,
        "is_near_miss": False,
        "checks": [],
    }
    
    yes_price = market.yes_price
    volume = market.volume_24h
    hours_to_expiry = market.hours_to_expiry
    
    print(f"Market: {market.question[:60]}...")
    print()
    
    # Type checks
    print(f"{Colors.BOLD}TYPE VERIFICATION:{Colors.ENDC}")
    print_type_check("yes_price", yes_price)
    print_type_check("volume_24h", volume)
    print_type_check("hours_to_expiry", hours_to_expiry)
    print()
    
    # =========================================================================
    # COMMON FILTER 1: Expiry
    # =========================================================================
    print(f"{Colors.BOLD}COMMON CHECK 1: Expiry{Colors.ENDC}")
    max_expiry = SNIPER_CONFIG["max_expiry_hours"]
    
    if hours_to_expiry is None:
        print(f"  {Colors.warn('hours_to_expiry is None - check skipped')}")
        check1_pass = True
    else:
        check1_pass = check_comparison("hours_to_expiry <= max_expiry", hours_to_expiry, '<=', max_expiry)
        if check1_pass:
            check1_pass = check_comparison("hours_to_expiry > 0.5", hours_to_expiry, '>', 0.5)
    
    result["checks"].append({"name": "expiry", "passed": check1_pass})
    print()
    
    # =========================================================================
    # COMMON FILTER 2: Minimum Volume
    # =========================================================================
    print(f"{Colors.BOLD}COMMON CHECK 2: Minimum Volume{Colors.ENDC}")
    min_vol = SNIPER_CONFIG["min_volume_24h"]
    
    check2_pass = check_comparison("volume >= min_volume", volume, '>=', min_vol)
    
    # Near miss
    if not check2_pass:
        near_miss_vol = min_vol * 0.8
        if volume >= near_miss_vol:
            print(f"  {Colors.warn(f'NEAR MISS: Volume ${volume:,.0f} close to ${min_vol:,.0f}')}")
            result["is_near_miss"] = True
            result["near_miss_reason"] = f"Volume ${volume:,.0f} (need ${min_vol:,.0f})"
    
    result["checks"].append({"name": "min_volume", "passed": check2_pass})
    print()
    
    if not check2_pass:
        return result
    
    # =========================================================================
    # MODE 1: CRASH DETECTOR
    # =========================================================================
    print(f"{Colors.BOLD}MODE 1: CRASH DETECTOR{Colors.ENDC}")
    print(f"  ⚠️ Crash detector requires price history (rolling buffer)")
    print(f"  ⚠️ Cannot test without historical data")
    print(f"  Threshold: {SNIPER_CONFIG['price_drop_threshold']:.0%} drop in {5} minutes")
    print()
    
    # =========================================================================
    # MODE 2: STINK BID
    # =========================================================================
    print(f"{Colors.BOLD}MODE 2: STINK BID{Colors.ENDC}")
    stink_min = SNIPER_CONFIG["stink_bid_min_price"]
    stink_max = SNIPER_CONFIG["stink_bid_max_price"]
    stink_vol = SNIPER_CONFIG["stink_bid_min_volume"]
    
    print(f"  Price range for stink bid: ${stink_min} - ${stink_max}")
    print(f"  Current YES price: ${yes_price}")
    
    price_in_range = check_comparison("price in stink range", yes_price, 'between', (stink_min, stink_max))
    
    if price_in_range:
        vol_check = check_comparison("volume >= stink_min_volume", volume, '>=', stink_vol)
        
        if not vol_check:
            near_miss_vol = stink_vol * 0.8
            if volume >= near_miss_vol:
                print(f"  {Colors.warn(f'NEAR MISS: Volume ${volume:,.0f} close to ${stink_vol:,.0f}')}")
                result["is_near_miss"] = True
    else:
        print(f"  Price ${yes_price} not in stink bid range")
    
    return result

def audit_arb_strategy(market: AuditMarketData, verbose: bool = False) -> Dict:
    """
    Audit ArbitrageStrategy decision process.
    """
    print_header("🔀 ARBITRAGE STRATEGY AUDIT")
    
    result = {
        "strategy": "ARB_PREDICTBASE_V1",
        "would_trigger": False,
        "is_near_miss": False,
        "checks": [],
    }
    
    print(f"Market: {market.question[:60]}...")
    print()
    
    print(f"{Colors.BOLD}ARBITRAGE LOGIC:{Colors.ENDC}")
    print(f"  Requires PredictBase prices for comparison")
    print(f"  Looking for: Poly_YES + PB_NO < 0.95 (5% profit)")
    print(f"  Or: Poly_NO + PB_YES < 0.95")
    print()
    
    print(f"  Polymarket prices:")
    print(f"    YES: ${market.yes_price:.4f}")
    print(f"    NO:  ${market.no_price:.4f}")
    print()
    
    print(f"  {Colors.warn('PredictBase lookup required - not performed in audit')}")
    print(f"  {Colors.info('Arb requires fuzzy matching to find equivalent market')}")
    print()
    
    # Simulate near-miss check
    min_spread = ARB_CONFIG["min_spread_pct"]
    simulated_pb_yes = market.yes_price * 1.02  # Simulate 2% higher
    combined_cost = market.yes_price + (1 - simulated_pb_yes)
    spread_pct = (1 - combined_cost) * 100
    
    print(f"  Simulated spread calculation:")
    print(f"    If PB_YES = ${simulated_pb_yes:.4f} (2% higher than Poly)")
    print(f"    Combined cost = {market.yes_price:.4f} + (1 - {simulated_pb_yes:.4f}) = {combined_cost:.4f}")
    print(f"    Spread = {spread_pct:.1f}%")
    
    check_comparison(f"spread >= {min_spread}%", spread_pct, '>=', min_spread)
    
    return result

# =============================================================================
# NEAR MISS TEST
# =============================================================================

def test_near_miss_injection():
    """
    Test Near Miss mechanism with injected data.
    """
    print_header("🧪 NEAR MISS INJECTION TEST")
    
    print("Testing that the near-miss detection logic works correctly...")
    print()
    
    # Test Case 1: Price just above threshold
    print(f"{Colors.BOLD}TEST 1: Price just above TAIL threshold{Colors.ENDC}")
    test_market_1 = AuditMarketData(
        condition_id="TEST_001",
        question="Will Bitcoin reach $200,000 by end of 2026?",
        token_id="test_token",
        market_slug="test-market",
        yes_price=0.045,  # Just above 0.04 threshold
        no_price=0.955,
        best_bid=0.044,
        best_ask=0.046,
        mid_price=0.045,
        spread_bps=44,
        volume_24h=100000,
        hours_to_expiry=48,
        competitor_prices={},
    )
    
    result = audit_tail_strategy(test_market_1)
    if result["is_near_miss"]:
        print(f"\n{Colors.ok('Near Miss detection WORKING for price threshold!')}")
    else:
        print(f"\n{Colors.fail('Near Miss NOT detected - BUG!')}")
    
    print("\n" + "-"*60 + "\n")
    
    # Test Case 2: ML score close to threshold
    print(f"{Colors.BOLD}TEST 2: ML Score close to threshold{Colors.ENDC}")
    test_market_2 = AuditMarketData(
        condition_id="TEST_002",
        question="Will some random unknown event happen?",  # Low category score
        token_id="test_token",
        market_slug="test-market",
        yes_price=0.03,  # Valid price
        no_price=0.97,
        best_bid=0.029,
        best_ask=0.031,
        mid_price=0.03,
        spread_bps=66,
        volume_24h=100000,
        hours_to_expiry=48,
        competitor_prices={},
    )
    
    result = audit_tail_strategy(test_market_2)
    print(f"\nML Score result: {result['checks'][-1] if result['checks'] else 'No checks'}")
    
    print("\n" + "-"*60 + "\n")
    
    # Test Case 3: Volume close to threshold
    print(f"{Colors.BOLD}TEST 3: Volume close to SNIPER threshold{Colors.ENDC}")
    test_market_3 = AuditMarketData(
        condition_id="TEST_003",
        question="Test market for volume check",
        token_id="test_token",
        market_slug="test-market",
        yes_price=0.5,
        no_price=0.5,
        best_bid=0.49,
        best_ask=0.51,
        mid_price=0.5,
        spread_bps=40,
        volume_24h=8500,  # Just below 10000 threshold
        hours_to_expiry=12,
        competitor_prices={},
    )
    
    result = audit_sniper_strategy(test_market_3)
    if result["is_near_miss"]:
        print(f"\n{Colors.ok('Near Miss detection WORKING for volume threshold!')}")
    else:
        print(f"\n{Colors.fail('Near Miss NOT detected - BUG!')}")

# =============================================================================
# MAIN FUNCTIONS
# =============================================================================

async def fetch_random_market() -> Optional[AuditMarketData]:
    """Fetch a random active market from Gamma API."""
    print(f"{Colors.info('Fetching random market from Gamma API...')}")
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Get markets with some volume
        resp = await client.get(
            "https://gamma-api.polymarket.com/markets",
            params={
                "limit": 50,
                "active": "true",
                "closed": "false",
            }
        )
        
        if resp.status_code != 200:
            print(f"{Colors.fail(f'API error: {resp.status_code}')}")
            return None
        
        markets = resp.json()
        
        # Filter for markets with volume > 10000
        good_markets = []
        for m in markets:
            vol = float(m.get("volume", 0) or 0)
            if vol > 10000:
                good_markets.append(m)
        
        if not good_markets:
            good_markets = markets[:10]  # Fallback
        
        # Pick random
        raw = random.choice(good_markets)
        
        return parse_gamma_market(raw)

async def fetch_market_by_id(condition_id: str) -> Optional[AuditMarketData]:
    """Fetch a specific market by condition ID."""
    print(f"{Colors.info(f'Fetching market: {condition_id[:40]}...')}")
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://gamma-api.polymarket.com/markets",
            params={
                "limit": 100,
                "active": "true",
            }
        )
        
        if resp.status_code != 200:
            return None
        
        markets = resp.json()
        
        for m in markets:
            cid = m.get("conditionId", "")
            if condition_id in cid or cid in condition_id:
                return parse_gamma_market(m)
        
        print(f"{Colors.fail('Market not found')}")
        return None

def parse_gamma_market(raw: Dict) -> AuditMarketData:
    """Parse raw Gamma API response into AuditMarketData."""
    
    # Parse prices
    yes_price = 0.0
    no_price = 0.0
    
    prices_str = raw.get("outcomePrices", "")
    outcomes_str = raw.get("outcomes", "")
    
    if prices_str and outcomes_str:
        try:
            prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
            outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
            
            for i, o in enumerate(outcomes):
                if o.upper() == "YES":
                    yes_price = float(prices[i])
                elif o.upper() == "NO":
                    no_price = float(prices[i])
        except:
            pass
    
    # Parse volume
    volume = 0.0
    try:
        volume = float(raw.get("volume", 0) or 0)
    except:
        pass
    
    # Parse expiry
    hours_to_expiry = None
    end_date = raw.get("endDate")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            hours_to_expiry = (end_dt - datetime.now(end_dt.tzinfo)).total_seconds() / 3600
        except:
            pass
    
    # Token IDs
    token_id = None
    clob_ids = raw.get("clobTokenIds")
    if clob_ids:
        try:
            ids = json.loads(clob_ids) if isinstance(clob_ids, str) else clob_ids
            token_id = ids[0] if ids else None
        except:
            pass
    
    return AuditMarketData(
        condition_id=raw.get("conditionId", ""),
        question=raw.get("question", ""),
        token_id=token_id,
        market_slug=raw.get("slug", ""),
        yes_price=yes_price,
        no_price=no_price,
        best_bid=yes_price * 0.99,
        best_ask=yes_price * 1.01,
        mid_price=(yes_price + no_price) / 2 if no_price else yes_price,
        spread_bps=abs(yes_price - (1 - no_price)) * 10000 if no_price else 0,
        volume_24h=volume,
        hours_to_expiry=hours_to_expiry,
        competitor_prices={},
        raw_data=raw,
    )

async def main():
    parser = argparse.ArgumentParser(description="Audit market through all strategies")
    parser.add_argument("--market", "-m", type=str, help="Specific market condition ID to audit")
    parser.add_argument("--test-near-miss", action="store_true", help="Test Near Miss injection")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--all-strategies", "-a", action="store_true", help="Run all strategies")
    
    args = parser.parse_args()
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║        🔬 POLYBOT MARKET AUDIT TOOL                      ║")
    print("║        Forensic Diagnostic for Trading Strategies        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    # Test Near Miss
    if args.test_near_miss:
        test_near_miss_injection()
        return
    
    # Fetch market
    if args.market:
        market = await fetch_market_by_id(args.market)
    else:
        market = await fetch_random_market()
    
    if not market:
        print(f"{Colors.fail('Could not fetch market data')}")
        return
    
    # Print raw data
    print_header("📥 RAW MARKET DATA FROM API")
    print(f"Condition ID: {market.condition_id}")
    print(f"Question: {market.question}")
    print(f"Slug: {market.market_slug}")
    print()
    print(f"{Colors.BOLD}PRICES:{Colors.ENDC}")
    print(f"  YES: ${market.yes_price:.6f}")
    print(f"  NO:  ${market.no_price:.6f}")
    print(f"  Best Bid: ${market.best_bid:.6f}")
    print(f"  Best Ask: ${market.best_ask:.6f}")
    print()
    print(f"{Colors.BOLD}METRICS:{Colors.ENDC}")
    print(f"  Volume 24h: ${market.volume_24h:,.2f}")
    print(f"  Spread (bps): {market.spread_bps:.0f}")
    print(f"  Hours to Expiry: {market.hours_to_expiry:.1f}" if market.hours_to_expiry else "  Hours to Expiry: N/A")
    
    # Run strategy audits
    audit_tail_strategy(market, verbose=args.verbose)
    audit_sniper_strategy(market, verbose=args.verbose)
    
    if args.all_strategies:
        audit_arb_strategy(market, verbose=args.verbose)
    
    # Summary
    print_header("📊 AUDIT SUMMARY")
    print(f"Market: {market.question[:50]}...")
    print(f"YES Price: ${market.yes_price:.4f}")
    print(f"Volume: ${market.volume_24h:,.0f}")
    print()
    
    # Quick diagnosis
    if market.yes_price < 0.001:
        print(f"{Colors.warn('Price too low (<$0.001) - likely settled or dead market')}")
    elif market.yes_price > 0.99:
        print(f"{Colors.warn('Price too high (>$0.99) - likely already settled')}")
    elif market.volume_24h < 500:
        print(f"{Colors.warn('Volume too low (<$500) - market not active enough')}")
    else:
        print(f"{Colors.info('Market appears valid - check strategy thresholds above')}")

if __name__ == "__main__":
    asyncio.run(main())
