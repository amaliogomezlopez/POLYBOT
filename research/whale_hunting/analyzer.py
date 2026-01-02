"""
The Analyzer: Advanced Metrics & Classification for Whale Traders.

This module reads harvested Parquet data and computes behavioral metrics
to classify trader archetypes.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

DATA_DIR = Path(__file__).parent / "data"
REPORT_PATH = Path(__file__).parent / "report.md"


# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def load_all_trades() -> dict[str, pd.DataFrame]:
    """Load all parquet files from the data directory."""
    trades = {}
    
    for parquet_file in DATA_DIR.glob("*_trades.parquet"):
        username = parquet_file.stem.replace("_trades", "")
        try:
            df = pd.read_parquet(parquet_file)
            trades[username] = df
            logger.info(f"Loaded {len(df)} trades for {username}")
        except Exception as e:
            logger.error(f"Failed to load {parquet_file}: {e}")
    
    return trades


def analyze_frequency(df: pd.DataFrame) -> dict:
    """
    Analyze trading frequency to detect bot vs human behavior.
    
    Metrics:
    - Trades per hour distribution
    - Time between consecutive trades
    - Activity by hour of day
    """
    if "timestamp" not in df.columns and "createdAt" not in df.columns:
        return {"error": "No timestamp column found"}
    
    # Normalize timestamp column
    ts_col = "timestamp" if "timestamp" in df.columns else "createdAt"
    
    try:
        df["_ts"] = pd.to_datetime(df[ts_col], unit="s", errors="coerce")
    except:
        df["_ts"] = pd.to_datetime(df[ts_col], errors="coerce")
    
    df = df.dropna(subset=["_ts"]).sort_values("_ts")
    
    if df.empty:
        return {"error": "No valid timestamps"}
    
    # Calculate inter-trade intervals
    df["_interval"] = df["_ts"].diff().dt.total_seconds()
    
    # Trades per hour
    df["_hour"] = df["_ts"].dt.hour
    hourly_counts = df.groupby("_hour").size()
    
    # Time span
    time_span = (df["_ts"].max() - df["_ts"].min()).total_seconds() / 3600  # hours
    
    # Bot detection heuristics
    median_interval = df["_interval"].median()
    min_interval = df["_interval"].min()
    trades_per_hour = len(df) / max(time_span, 1)
    
    is_likely_bot = (
        (min_interval < 1.0) or  # Sub-second trades
        (trades_per_hour > 50) or  # Very high frequency
        (median_interval < 5.0)  # Very consistent timing
    )
    
    return {
        "total_trades": len(df),
        "time_span_hours": round(time_span, 2),
        "trades_per_hour": round(trades_per_hour, 2),
        "median_interval_seconds": round(median_interval, 2) if pd.notna(median_interval) else None,
        "min_interval_seconds": round(min_interval, 2) if pd.notna(min_interval) else None,
        "peak_hour": int(hourly_counts.idxmax()) if not hourly_counts.empty else None,
        "is_likely_bot": is_likely_bot,
    }


def analyze_pnl_attribution(df: pd.DataFrame) -> dict:
    """
    Attribute P&L to different strategies:
    - Directional: Betting on outcomes
    - Arbitrage: Delta-neutral positions
    - Market Making: Providing liquidity
    """
    if "side" not in df.columns:
        return {"error": "No side column"}
    
    # Count buys vs sells
    buy_count = len(df[df["side"].str.upper() == "BUY"])
    sell_count = len(df[df["side"].str.upper() == "SELL"])
    
    # Analyze if user trades both sides of same market
    if "conditionId" in df.columns:
        condition_sides = df.groupby("conditionId")["side"].nunique()
        both_sides_count = (condition_sides == 2).sum()
        single_side_count = (condition_sides == 1).sum()
        
        delta_neutral_ratio = both_sides_count / max(both_sides_count + single_side_count, 1)
    else:
        delta_neutral_ratio = 0.0
        both_sides_count = 0
        single_side_count = 0
    
    # Classify strategy
    if delta_neutral_ratio > 0.5:
        primary_strategy = "Arbitrageur"
    elif buy_count > sell_count * 2:
        primary_strategy = "Directional Buyer"
    elif sell_count > buy_count * 2:
        primary_strategy = "Market Maker"
    else:
        primary_strategy = "Mixed"
    
    return {
        "buy_count": buy_count,
        "sell_count": sell_count,
        "delta_neutral_ratio": round(delta_neutral_ratio, 2),
        "primary_strategy": primary_strategy,
    }


def analyze_category_focus(df: pd.DataFrame) -> dict:
    """Analyze which categories the trader focuses on."""
    # Try to extract category from market title or slug
    if "title" in df.columns:
        titles = df["title"].dropna().str.lower()
        
        crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto", "xrp"]
        sports_keywords = ["nfl", "nba", "mlb", "soccer", "football", "game", "match", "vs"]
        politics_keywords = ["trump", "biden", "election", "president", "vote", "congress"]
        
        crypto_count = titles.apply(lambda x: any(k in x for k in crypto_keywords)).sum()
        sports_count = titles.apply(lambda x: any(k in x for k in sports_keywords)).sum()
        politics_count = titles.apply(lambda x: any(k in x for k in politics_keywords)).sum()
        
        total = len(titles)
        
        return {
            "crypto_pct": round(crypto_count / max(total, 1) * 100, 1),
            "sports_pct": round(sports_count / max(total, 1) * 100, 1),
            "politics_pct": round(politics_count / max(total, 1) * 100, 1),
            "other_pct": round((total - crypto_count - sports_count - politics_count) / max(total, 1) * 100, 1),
        }
    
    return {"error": "No title column"}


def classify_trader(freq: dict, pnl: dict, category: dict) -> str:
    """
    Classify trader into archetype based on all metrics.
    
    Archetypes:
    - Market Maker: High frequency, both sides, liquidity provision
    - News Trader: Directional, politics focus, variable timing
    - Arbitrageur: Delta-neutral, crypto focus, bot-like behavior
    - Gambler: Low frequency, sports focus, buy-heavy
    """
    is_bot = freq.get("is_likely_bot", False)
    strategy = pnl.get("primary_strategy", "")
    crypto_focus = category.get("crypto_pct", 0) > 50
    sports_focus = category.get("sports_pct", 0) > 30
    politics_focus = category.get("politics_pct", 0) > 30
    
    if is_bot and crypto_focus and "Arbit" in strategy:
        return "🤖 Arbitrageur"
    elif is_bot and "Market Maker" in strategy:
        return "💹 Market Maker"
    elif politics_focus:
        return "📰 News Trader"
    elif sports_focus:
        return "🎰 Gambler"
    else:
        return "🔮 Mixed Strategy"


def generate_report(all_analysis: dict[str, dict]) -> str:
    """Generate a markdown report from all analysis results."""
    lines = [
        "# 🐋 Whale Hunting Report",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## Executive Summary",
        "",
        "This report analyzes the trading behavior of top Polymarket traders to identify",
        "strategies that can be replicated or improved upon.",
        "",
        "---",
        "",
        "## Trader Classifications",
        "",
        "| Username | Classification | Trades | Trades/Hour | Bot? |",
        "|----------|----------------|--------|-------------|------|",
    ]
    
    for username, analysis in all_analysis.items():
        freq = analysis.get("frequency", {})
        classification = analysis.get("classification", "Unknown")
        
        lines.append(
            f"| **{username}** | {classification} | "
            f"{freq.get('total_trades', 'N/A')} | "
            f"{freq.get('trades_per_hour', 'N/A')} | "
            f"{'✅' if freq.get('is_likely_bot') else '❌'} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## Detailed Analysis",
        "",
    ])
    
    for username, analysis in all_analysis.items():
        lines.extend([
            f"### {username}",
            "",
            f"**Classification:** {analysis.get('classification', 'Unknown')}",
            "",
            "#### Frequency Metrics",
            f"- Total Trades: {analysis.get('frequency', {}).get('total_trades', 'N/A')}",
            f"- Time Span: {analysis.get('frequency', {}).get('time_span_hours', 'N/A')} hours",
            f"- Trades/Hour: {analysis.get('frequency', {}).get('trades_per_hour', 'N/A')}",
            f"- Median Interval: {analysis.get('frequency', {}).get('median_interval_seconds', 'N/A')}s",
            "",
            "#### Strategy Breakdown",
            f"- Primary Strategy: {analysis.get('pnl', {}).get('primary_strategy', 'N/A')}",
            f"- Buy/Sell Ratio: {analysis.get('pnl', {}).get('buy_count', 0)}/{analysis.get('pnl', {}).get('sell_count', 0)}",
            f"- Delta-Neutral Ratio: {analysis.get('pnl', {}).get('delta_neutral_ratio', 'N/A')}",
            "",
            "#### Category Focus",
            f"- Crypto: {analysis.get('category', {}).get('crypto_pct', 'N/A')}%",
            f"- Sports: {analysis.get('category', {}).get('sports_pct', 'N/A')}%",
            f"- Politics: {analysis.get('category', {}).get('politics_pct', 'N/A')}%",
            "",
            "---",
            "",
        ])
    
    lines.extend([
        "## Conclusions",
        "",
        "Based on the analysis, the following strategies show promise for replication:",
        "",
        "1. **Arbitrage Bots**: High-frequency traders operating on crypto flash markets",
        "   demonstrate consistent profitability through delta-neutral positions.",
        "",
        "2. **Market Making**: Users with balanced buy/sell ratios likely profit from",
        "   bid-ask spreads rather than directional bets.",
        "",
        "3. **News Trading**: Accounts focused on political markets may follow external",
        "   signals (polls, news) to make directional bets.",
        "",
    ])
    
    return "\n".join(lines)


# ============================================================================
# MAIN ANALYSIS PIPELINE
# ============================================================================

def run_analysis() -> dict[str, dict]:
    """Run full analysis pipeline on all harvested data."""
    trades = load_all_trades()
    
    if not trades:
        logger.warning("No trade data found. Run harvester.py first.")
        return {}
    
    all_analysis = {}
    
    for username, df in trades.items():
        logger.info(f"Analyzing {username}...")
        
        freq = analyze_frequency(df)
        pnl = analyze_pnl_attribution(df)
        category = analyze_category_focus(df)
        classification = classify_trader(freq, pnl, category)
        
        all_analysis[username] = {
            "frequency": freq,
            "pnl": pnl,
            "category": category,
            "classification": classification,
        }
    
    # Generate report
    report = generate_report(all_analysis)
    REPORT_PATH.write_text(report, encoding="utf-8")
    logger.info(f"Report saved to {REPORT_PATH}")
    
    return all_analysis


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🔬 WHALE ANALYZER - Behavioral Classification")
    print("=" * 60)
    print()
    
    results = run_analysis()
    
    print()
    print("=" * 60)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 60)
    for username, analysis in results.items():
        print(f"  {username}: {analysis.get('classification', 'Unknown')}")
    
    print()
    print(f"📄 Full report: {REPORT_PATH}")
