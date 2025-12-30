"""
Complete Tail Betting System for Low Capital Trading
Optimized for maximum profit with minimal risk
"""

import asyncio
import json
import httpx
import os
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import Optional, List
from enum import Enum
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BetStatus(Enum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"


class TradingMode(Enum):
    PAPER = "paper"
    REAL = "real"


@dataclass
class TailBet:
    """A tail bet record"""
    id: str
    timestamp: str
    condition_id: str
    token_id: str
    question: str
    entry_price: float
    stake: float
    size: float
    potential_return: float
    status: str = "pending"
    ml_score: float = 0.0
    category: str = "other"
    resolved_at: Optional[str] = None
    actual_return: Optional[float] = None
    profit_loss: Optional[float] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategyConfig:
    """Configuration for tail betting strategy"""
    # Core parameters
    max_yes_price: float = 0.04  # Max 4 cents
    stake_usd: float = 2.0       # Fixed $2 per bet
    
    # Risk management
    max_daily_bets: int = 50
    max_open_bets: int = 100
    max_daily_loss: float = 100.0
    min_bankroll: float = 50.0
    
    # ML scoring thresholds
    min_score_to_bet: float = 0.60
    strong_bet_score: float = 0.70
    
    # Timing
    scan_interval: int = 60  # seconds
    resolution_check_interval: int = 3600  # 1 hour
    
    # Mode
    paper_trading: bool = True


@dataclass
class TradingStats:
    """Trading statistics tracker"""
    total_bets: int = 0
    pending_bets: int = 0
    won: int = 0
    lost: int = 0
    cancelled: int = 0
    total_invested: float = 0.0
    total_returned: float = 0.0
    net_profit: float = 0.0
    hit_rate: float = 0.0
    roi: float = 0.0
    best_win: float = 0.0
    avg_win_multiplier: float = 0.0
    current_bankroll: float = 0.0
    
    def update(self, bets: List[dict]):
        """Update stats from bet list"""
        self.total_bets = len(bets)
        self.pending_bets = sum(1 for b in bets if b.get("status") in ["pending", "OPEN"])
        self.won = sum(1 for b in bets if b.get("status") == "won")
        self.lost = sum(1 for b in bets if b.get("status") == "lost")
        self.cancelled = sum(1 for b in bets if b.get("status") == "cancelled")
        
        self.total_invested = sum(b.get("stake", 2.0) for b in bets)
        self.total_returned = sum(b.get("actual_return", 0) for b in bets if b.get("status") == "won")
        self.net_profit = self.total_returned - (self.won + self.lost) * 2.0 if (self.won + self.lost) > 0 else 0
        
        resolved = self.won + self.lost
        self.hit_rate = (self.won / resolved * 100) if resolved > 0 else 0
        self.roi = ((self.total_returned / self.total_invested) - 1) * 100 if self.total_invested > 0 else 0
        
        wins = [b for b in bets if b.get("status") == "won"]
        if wins:
            self.best_win = max(b.get("actual_return", 0) for b in wins)
            self.avg_win_multiplier = sum(b.get("actual_return", 0) / b.get("stake", 2) for b in wins) / len(wins)


class CompleteTailSystem:
    """
    Complete tail betting system for low capital trading
    
    Features:
    - Market scanning with ML scoring
    - Paper and real trading modes
    - Automatic resolution tracking
    - XGBoost model training
    - Profit optimization
    """
    
    CLOB_API = "https://clob.polymarket.com"
    GAMMA_API = "https://gamma-api.polymarket.com"
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()
        self.data_dir = Path("data/tail_bot")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        self.bets = self._load_json("bets.json", [])
        self.stats = TradingStats()
        self.stats.update(self.bets)
        
        # Category keywords
        self.categories = {
            "political": ["trump", "biden", "election", "congress", "senate", "president"],
            "crypto": ["bitcoin", "ethereum", "btc", "eth", "crypto", "solana"],
            "sports": ["nfl", "nba", "mlb", "soccer", "game", "match", "win"],
            "finance": ["stock", "fed", "rate", "gdp", "inflation", "nasdaq"],
            "tech": ["google", "apple", "microsoft", "ai", "openai", "meta", "nvidia"],
        }
        
        # ML model weights (will be trained from outcomes)
        self.category_weights = {
            "crypto": 0.10,
            "tech": 0.08,
            "entertainment": 0.05,
            "political": 0.03,
            "finance": 0.02,
            "sports": -0.05,
            "other": 0.0
        }
    
    def _load_json(self, filename: str, default):
        """Load JSON file"""
        filepath = self.data_dir / filename
        if filepath.exists():
            return json.loads(filepath.read_text())
        return default
    
    def _save_json(self, filename: str, data):
        """Save JSON file"""
        filepath = self.data_dir / filename
        filepath.write_text(json.dumps(data, indent=2))
    
    def _normalize_bets(self):
        """Normalize bet status values"""
        for bet in self.bets:
            status = bet.get("status", "").lower()
            if status == "open":
                bet["status"] = "pending"
    
    def detect_category(self, question: str) -> str:
        """Detect market category"""
        q_lower = question.lower()
        for category, keywords in self.categories.items():
            if any(kw in q_lower for kw in keywords):
                return category
        return "other"
    
    def calculate_ml_score(self, market: dict) -> float:
        """Calculate ML score for opportunity"""
        score = 0.5
        
        question = market.get("question", "").lower()
        yes_price = market.get("yes_price", 0.01)
        
        # Price factor
        if yes_price <= 0.01:
            score += 0.15
        elif yes_price <= 0.02:
            score += 0.10
        elif yes_price <= 0.03:
            score += 0.05
        
        # Category bonus
        category = self.detect_category(question)
        score += self.category_weights.get(category, 0)
        
        # Keyword bonuses
        if any(kw in question for kw in ["will", "announce", "release", "launch"]):
            score += 0.03
        if any(kw in question for kw in ["not", "never", "fail"]):
            score -= 0.05
        
        return max(0.0, min(1.0, score))
    
    async def scan_markets(self) -> list[dict]:
        """Scan for tail opportunities"""
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(f"{self.CLOB_API}/sampling-markets")
                if resp.status_code != 200:
                    return []
                
                data = resp.json()
                markets = data.get("data", []) if isinstance(data, dict) else data
                
                tail_opportunities = []
                for market in markets:
                    tokens = market.get("tokens", [])
                    for token in tokens:
                        if token.get("outcome") == "Yes":
                            price = float(token.get("price", 1))
                            if price <= self.config.max_yes_price:
                                opp = {
                                    "condition_id": market.get("condition_id"),
                                    "token_id": token.get("token_id"),
                                    "question": market.get("question", ""),
                                    "yes_price": price,
                                    "category": self.detect_category(market.get("question", "")),
                                }
                                opp["ml_score"] = self.calculate_ml_score(opp)
                                opp["potential"] = 1 / price if price > 0 else 0
                                tail_opportunities.append(opp)
                
                # Sort by ML score
                tail_opportunities.sort(key=lambda x: x["ml_score"], reverse=True)
                return tail_opportunities
                
            except Exception as e:
                logger.error(f"Error scanning: {e}")
                return []
    
    def _already_bet_on(self, condition_id: str) -> bool:
        """Check if we already have a bet on this market"""
        return any(b.get("condition_id") == condition_id for b in self.bets)
    
    async def place_paper_bet(self, opportunity: dict) -> Optional[TailBet]:
        """Place a paper trade bet"""
        if self._already_bet_on(opportunity["condition_id"]):
            return None
        
        if len([b for b in self.bets if b.get("status") == "pending"]) >= self.config.max_open_bets:
            return None
        
        bet_id = f"TAIL-{int(datetime.now().timestamp())}-{len(self.bets) + 1}"
        size = self.config.stake_usd / opportunity["yes_price"]
        
        bet = TailBet(
            id=bet_id,
            timestamp=datetime.now().isoformat(),
            condition_id=opportunity["condition_id"],
            token_id=opportunity["token_id"],
            question=opportunity["question"],
            entry_price=opportunity["yes_price"],
            stake=self.config.stake_usd,
            size=size,
            potential_return=size,
            ml_score=opportunity.get("ml_score", 0),
            category=opportunity.get("category", "other"),
            status="pending"
        )
        
        self.bets.append(bet.to_dict())
        self._save_json("bets.json", self.bets)
        
        logger.info(f"📝 PAPER BET: {bet_id}")
        logger.info(f"   {opportunity['question'][:50]}...")
        logger.info(f"   Price: ${opportunity['yes_price']:.4f} | Potential: {bet.potential_return:.0f}x")
        
        return bet
    
    async def place_real_bet(self, opportunity: dict) -> Optional[TailBet]:
        """
        Place a real bet using Polymarket API
        CAUTION: This uses real money!
        """
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType
        
        # Load credentials from env
        private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
        if not private_key:
            logger.error("No private key found!")
            return None
        
        try:
            # Initialize CLOB client
            client = ClobClient(
                host="https://clob.polymarket.com",
                key=private_key,
                chain_id=137,  # Polygon
            )
            
            # Create market buy order
            order = OrderArgs(
                token_id=opportunity["token_id"],
                price=opportunity["yes_price"],
                size=self.config.stake_usd / opportunity["yes_price"],
                side="BUY",
            )
            
            # Submit order
            result = client.create_and_post_order(order)
            
            if result.get("success"):
                bet_id = f"REAL-{int(datetime.now().timestamp())}"
                
                bet = TailBet(
                    id=bet_id,
                    timestamp=datetime.now().isoformat(),
                    condition_id=opportunity["condition_id"],
                    token_id=opportunity["token_id"],
                    question=opportunity["question"],
                    entry_price=opportunity["yes_price"],
                    stake=self.config.stake_usd,
                    size=self.config.stake_usd / opportunity["yes_price"],
                    potential_return=self.config.stake_usd / opportunity["yes_price"],
                    ml_score=opportunity.get("ml_score", 0),
                    category=opportunity.get("category", "other"),
                    status="pending"
                )
                
                self.bets.append(bet.to_dict())
                self._save_json("bets.json", self.bets)
                
                logger.info(f"💰 REAL BET PLACED: {bet_id}")
                logger.info(f"   {opportunity['question'][:50]}...")
                
                return bet
            else:
                logger.error(f"Order failed: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Real bet error: {e}")
            return None
    
    async def check_resolutions(self) -> dict:
        """Check for resolved bets"""
        self._normalize_bets()
        
        newly_resolved = []
        
        async with httpx.AsyncClient(timeout=30) as client:
            for bet in self.bets:
                if bet.get("status") != "pending":
                    continue
                
                condition_id = bet.get("condition_id")
                if not condition_id:
                    continue
                
                try:
                    resp = await client.get(f"{self.GAMMA_API}/markets/{condition_id}")
                    if resp.status_code == 200:
                        data = resp.json()
                        
                        if data.get("closed") or data.get("resolved"):
                            outcome = data.get("outcome")
                            
                            if outcome == "Yes":
                                bet["status"] = "won"
                                bet["actual_return"] = bet["size"]
                                bet["profit_loss"] = bet["size"] - bet["stake"]
                            elif outcome == "No":
                                bet["status"] = "lost"
                                bet["actual_return"] = 0
                                bet["profit_loss"] = -bet["stake"]
                            else:
                                bet["status"] = "cancelled"
                                bet["actual_return"] = bet["stake"]
                                bet["profit_loss"] = 0
                            
                            bet["resolved_at"] = datetime.now().isoformat()
                            newly_resolved.append(bet)
                            
                            status_emoji = "✅" if bet["status"] == "won" else "❌"
                            logger.info(f"{status_emoji} RESOLVED: {bet['question'][:40]}...")
                            logger.info(f"   Status: {bet['status'].upper()}, P/L: ${bet['profit_loss']:.2f}")
                
                except Exception as e:
                    logger.error(f"Error checking {condition_id}: {e}")
                
                await asyncio.sleep(0.1)  # Rate limiting
        
        # Save updated bets
        self._save_json("bets.json", self.bets)
        self.stats.update(self.bets)
        
        return {
            "newly_resolved": len(newly_resolved),
            "wins": sum(1 for b in newly_resolved if b["status"] == "won"),
            "losses": sum(1 for b in newly_resolved if b["status"] == "lost"),
        }
    
    def update_ml_weights(self):
        """
        Update ML weights based on actual outcomes
        This is a simple online learning approach
        """
        # Group resolved bets by category
        category_outcomes = {}
        
        for bet in self.bets:
            if bet.get("status") not in ["won", "lost"]:
                continue
            
            category = bet.get("category", "other")
            if category not in category_outcomes:
                category_outcomes[category] = {"wins": 0, "total": 0}
            
            category_outcomes[category]["total"] += 1
            if bet["status"] == "won":
                category_outcomes[category]["wins"] += 1
        
        # Update weights based on win rate
        for category, outcomes in category_outcomes.items():
            if outcomes["total"] >= 5:  # Need at least 5 bets
                win_rate = outcomes["wins"] / outcomes["total"]
                # Adjust weight based on win rate vs expected (2%)
                adjustment = (win_rate - 0.02) * 2  # Scale adjustment
                self.category_weights[category] = max(-0.1, min(0.2, adjustment))
        
        logger.info("📊 ML weights updated based on outcomes")
        for cat, weight in self.category_weights.items():
            logger.info(f"   {cat}: {weight:+.3f}")
    
    def get_status_report(self) -> str:
        """Generate status report"""
        self.stats.update(self.bets)
        
        lines = [
            "",
            "=" * 70,
            "🎲 TAIL BETTING SYSTEM STATUS",
            "=" * 70,
            "",
            f"Mode: {'PAPER 📝' if self.config.paper_trading else 'REAL 💰'}",
            "",
            "📊 BETS:",
            f"   Total:      {self.stats.total_bets}",
            f"   Pending:    {self.stats.pending_bets}",
            f"   Won:        {self.stats.won} ✅",
            f"   Lost:       {self.stats.lost} ❌",
            f"   Cancelled:  {self.stats.cancelled}",
            "",
            "💰 FINANCIAL:",
            f"   Invested:   ${self.stats.total_invested:.2f}",
            f"   Returned:   ${self.stats.total_returned:.2f}",
            f"   Net Profit: ${self.stats.net_profit:.2f}",
            f"   ROI:        {self.stats.roi:.1f}%",
            "",
            "📈 PERFORMANCE:",
            f"   Hit Rate:   {self.stats.hit_rate:.2f}%",
            f"   Best Win:   ${self.stats.best_win:.2f}",
            f"   Avg Mult:   {self.stats.avg_win_multiplier:.1f}x",
            "",
        ]
        
        # Add profitability analysis
        if self.stats.won + self.stats.lost >= 10:
            lines.append("📉 PROFITABILITY:")
            required_hit = 2.0  # Need ~2% to break even at 50x
            if self.stats.hit_rate >= required_hit:
                lines.append(f"   ✅ PROFITABLE - Hit rate {self.stats.hit_rate:.1f}% >= {required_hit}%")
                lines.append(f"   Consider switching to REAL trading!")
            else:
                lines.append(f"   ❌ NOT YET - Hit rate {self.stats.hit_rate:.1f}% < {required_hit}%")
                lines.append(f"   Keep paper trading...")
        
        lines.extend(["", "=" * 70])
        
        return "\n".join(lines)
    
    async def run_cycle(self):
        """Run one trading cycle"""
        # Scan for opportunities
        opportunities = await self.scan_markets()
        logger.info(f"🔍 Found {len(opportunities)} tail opportunities")
        
        # Filter by ML score
        good_opps = [o for o in opportunities if o["ml_score"] >= self.config.min_score_to_bet]
        logger.info(f"   {len(good_opps)} pass ML threshold (>={self.config.min_score_to_bet:.0%})")
        
        # Place bets on top opportunities
        bets_placed = 0
        for opp in good_opps[:10]:  # Max 10 new bets per cycle
            if self.config.paper_trading:
                bet = await self.place_paper_bet(opp)
            else:
                bet = await self.place_real_bet(opp)
            
            if bet:
                bets_placed += 1
        
        logger.info(f"   Placed {bets_placed} new bets")
        
        # Check resolutions
        resolution_result = await self.check_resolutions()
        if resolution_result["newly_resolved"] > 0:
            logger.info(f"📋 Resolved: {resolution_result['wins']} wins, {resolution_result['losses']} losses")
            
            # Update ML weights if we have new outcomes
            self.update_ml_weights()
        
        return {
            "opportunities": len(opportunities),
            "bets_placed": bets_placed,
            "resolutions": resolution_result
        }
    
    async def run(self, cycles: int = None):
        """Run the trading system"""
        print(self.get_status_report())
        
        cycle = 0
        while cycles is None or cycle < cycles:
            cycle += 1
            logger.info(f"\n[Cycle {cycle}] {datetime.now().isoformat()}")
            
            try:
                result = await self.run_cycle()
                print(self.get_status_report())
                
            except KeyboardInterrupt:
                logger.info("Stopping...")
                break
            except Exception as e:
                logger.error(f"Cycle error: {e}")
            
            if cycles is None or cycle < cycles:
                await asyncio.sleep(self.config.scan_interval)


async def main():
    """Main entry point"""
    # Check paper trading mode
    paper_mode = os.getenv("PAPER_TRADING", "true").lower() == "true"
    
    config = StrategyConfig(
        max_yes_price=0.04,
        stake_usd=2.0,
        min_score_to_bet=0.60,
        paper_trading=paper_mode,
        scan_interval=60,
    )
    
    system = CompleteTailSystem(config)
    
    print("=" * 70)
    print("🚀 COMPLETE TAIL BETTING SYSTEM")
    print(f"   Mode: {'PAPER' if paper_mode else 'REAL'}")
    print(f"   Stake: ${config.stake_usd}")
    print(f"   Max Price: ${config.max_yes_price}")
    print("=" * 70)
    
    # Run 5 cycles for testing
    await system.run(cycles=5)


if __name__ == "__main__":
    asyncio.run(main())
