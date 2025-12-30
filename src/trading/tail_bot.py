"""
Tail Betting Bot
Implements @Spon's tail betting strategy.

Strategy:
- Scan all markets every 60 seconds
- Hunt tail outcomes (YES < 4 cents)
- Buy with fixed $2 downside
- A few hits cover hundreds of misses
"""
import asyncio
import json
import time
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class TailBotConfig:
    """Configuration for tail bot"""
    max_yes_price: float = 0.04          # Maximum YES price (4 cents)
    min_yes_price: float = 0.001         # Minimum price (avoid dust)
    stake_usd: float = 2.0               # Fixed stake per bet
    max_liquidity: float = 100_000       # Avoid very high liquidity (manipulated)
    min_liquidity: float = 0             # Disabled - API returns 0 for most
    sleep_seconds: int = 60              # Scan interval
    max_daily_bets: int = 50             # Maximum bets per day
    max_exposure: float = 200            # Maximum total exposure
    paper_trading: bool = True           # Paper trading mode


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class TailOpportunity:
    """A tail betting opportunity"""
    question: str
    condition_id: str
    token_id: str
    yes_price: float
    liquidity: float
    potential_return: float
    score: float
    end_date: str = ""
    category: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TailBet:
    """A placed tail bet"""
    id: str
    timestamp: float
    question: str
    condition_id: str
    token_id: str
    entry_price: float
    stake: float
    size: float
    potential_return: float
    status: str = "OPEN"  # OPEN, WON, LOST
    exit_price: Optional[float] = None
    pnl: float = 0.0
    resolved_at: Optional[float] = None


@dataclass
class TailBotState:
    """Bot state tracking"""
    total_bets: int = 0
    open_bets: int = 0
    won_bets: int = 0
    lost_bets: int = 0
    total_invested: float = 0.0
    total_returns: float = 0.0
    current_exposure: float = 0.0
    bets_today: int = 0
    last_scan: float = 0.0
    seen_conditions: List[str] = field(default_factory=list)


# =============================================================================
# MARKET SCANNER
# =============================================================================

class TailMarketScanner:
    """Scans for tail betting opportunities"""
    
    CLOB_API = "https://clob.polymarket.com"
    GAMMA_API = "https://gamma-api.polymarket.com"
    
    def __init__(self, config: TailBotConfig):
        self.config = config
        
    def get_all_markets(self) -> List[Dict]:
        """Get all active markets with prices"""
        try:
            url = f"{self.CLOB_API}/sampling-markets"
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                return data.get("data", [])
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
        return []
        
    def is_tail_market(self, market: Dict) -> Tuple[bool, Optional[TailOpportunity]]:
        """Check if market qualifies as tail bet"""
        try:
            # Must be active with orderbook
            if not market.get("enable_order_book"):
                return False, None
            if not market.get("active"):
                return False, None
            if market.get("closed"):
                return False, None
                
            # Get tokens
            tokens = market.get("tokens", [])
            if not tokens:
                return False, None
                
            # Find YES token
            yes_token = None
            for t in tokens:
                if "yes" in t.get("outcome", "").lower():
                    yes_token = t
                    break
                    
            if not yes_token:
                return False, None
                
            # Get price
            price = float(yes_token.get("price", 1) or 1)
            
            # Check price bounds
            if price > self.config.max_yes_price:
                return False, None
            if price < self.config.min_yes_price:
                return False, None
                
            # Calculate liquidity (might be 0 in API, use alternative)
            liquidity = sum(float(t.get("liquidity", 0) or 0) for t in tokens)
            
            # If liquidity is 0, estimate from rewards or skip check
            if liquidity == 0:
                # Check if rewards exist (indicates active market)
                rewards = market.get("rewards", {})
                if rewards and rewards.get("rates"):
                    liquidity = 1000  # Assume minimum viable liquidity
                else:
                    # Accept market anyway if liquidity check is disabled
                    liquidity = self.config.min_liquidity  # Pass the check
                    
            # Check liquidity bounds (skip if min_liquidity is 0)
            if self.config.min_liquidity > 0:
                if liquidity > self.config.max_liquidity:
                    return False, None
                if liquidity < self.config.min_liquidity:
                    return False, None
                
            # Calculate potential return
            potential_return = self.config.stake_usd / price
            
            # Calculate score (higher is better)
            # Lower price + good liquidity = better opportunity
            price_score = (self.config.max_yes_price - price) / self.config.max_yes_price
            liquidity_score = min(liquidity / 10000, 1.0)
            score = price_score * 0.7 + liquidity_score * 0.3
            
            opportunity = TailOpportunity(
                question=market.get("question", "")[:150],
                condition_id=market.get("condition_id", ""),
                token_id=yes_token.get("token_id", ""),
                yes_price=price,
                liquidity=liquidity,
                potential_return=potential_return,
                score=score,
                end_date=market.get("end_date_iso", "")
            )
            
            return True, opportunity
            
        except Exception as e:
            logger.debug(f"Error checking market: {e}")
            return False, None
            
    def scan(self) -> List[TailOpportunity]:
        """Scan all markets for tail opportunities"""
        markets = self.get_all_markets()
        opportunities = []
        
        for market in markets:
            is_tail, opp = self.is_tail_market(market)
            if is_tail and opp:
                opportunities.append(opp)
                
        # Sort by score (best first)
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        return opportunities


# =============================================================================
# TAIL BOT
# =============================================================================

class TailBot:
    """
    Tail Betting Bot implementing @Spon's strategy.
    """
    
    def __init__(self, config: TailBotConfig = None):
        self.config = config or TailBotConfig()
        self.scanner = TailMarketScanner(self.config)
        self.state = TailBotState()
        self.bets: List[TailBet] = []
        self.state_file = "data/tail_bot/state.json"
        self.bets_file = "data/tail_bot/bets.json"
        
        # Load state
        self._load_state()
        
    def _load_state(self):
        """Load bot state from disk"""
        os.makedirs("data/tail_bot", exist_ok=True)
        
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.state = TailBotState(**data)
                    
            if os.path.exists(self.bets_file):
                with open(self.bets_file, "r") as f:
                    data = json.load(f)
                    self.bets = [TailBet(**b) for b in data]
                    
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
            
    def _save_state(self):
        """Save bot state to disk"""
        try:
            with open(self.state_file, "w") as f:
                json.dump(asdict(self.state), f, indent=2)
                
            with open(self.bets_file, "w") as f:
                json.dump([asdict(b) for b in self.bets], f, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save state: {e}")
            
    def should_bet(self, opportunity: TailOpportunity) -> Tuple[bool, str]:
        """Decide if we should bet on this opportunity"""
        
        # Check if already bet on this market
        if opportunity.condition_id in self.state.seen_conditions:
            return False, "Already bet on this market"
            
        # Check daily limit
        if self.state.bets_today >= self.config.max_daily_bets:
            return False, f"Daily bet limit reached ({self.config.max_daily_bets})"
            
        # Check exposure limit
        if self.state.current_exposure >= self.config.max_exposure:
            return False, f"Max exposure reached (${self.config.max_exposure})"
            
        # Check score threshold
        if opportunity.score < 0.5:
            return False, f"Score too low ({opportunity.score:.2f})"
            
        return True, "OK"
        
    def place_bet(self, opportunity: TailOpportunity) -> Optional[TailBet]:
        """Place a tail bet (paper or real)"""
        
        # Calculate size
        size = round(self.config.stake_usd / opportunity.yes_price, 2)
        
        # Create bet record
        bet = TailBet(
            id=f"TAIL-{int(time.time())}-{self.state.total_bets + 1}",
            timestamp=time.time(),
            question=opportunity.question,
            condition_id=opportunity.condition_id,
            token_id=opportunity.token_id,
            entry_price=opportunity.yes_price,
            stake=self.config.stake_usd,
            size=size,
            potential_return=opportunity.potential_return
        )
        
        if self.config.paper_trading:
            logger.info(f"📝 PAPER BET: {bet.id}")
        else:
            # TODO: Execute real trade via Polymarket API
            logger.info(f"💰 REAL BET: {bet.id}")
            # self._execute_real_bet(bet)
            
        # Update state
        self.bets.append(bet)
        self.state.total_bets += 1
        self.state.open_bets += 1
        self.state.total_invested += self.config.stake_usd
        self.state.current_exposure += self.config.stake_usd
        self.state.bets_today += 1
        self.state.seen_conditions.append(opportunity.condition_id)
        
        self._save_state()
        
        return bet
        
    def check_resolutions(self):
        """Check if any open bets have resolved"""
        # TODO: Implement resolution checking
        pass
        
    def run_scan_cycle(self) -> List[TailBet]:
        """Run one scan cycle"""
        logger.info(f"🔍 Scanning for tail markets...")
        
        # Scan for opportunities
        opportunities = self.scanner.scan()
        logger.info(f"   Found {len(opportunities)} tail opportunities")
        
        new_bets = []
        
        for opp in opportunities:
            should, reason = self.should_bet(opp)
            
            if should:
                bet = self.place_bet(opp)
                if bet:
                    new_bets.append(bet)
                    logger.info(f"   ✅ Bet placed: ${opp.yes_price:.3f} -> {opp.potential_return:.0f}x potential")
                    logger.info(f"      {opp.question[:60]}...")
                    
        if not new_bets:
            logger.info("   No new bets this cycle")
            
        self.state.last_scan = time.time()
        self._save_state()
        
        return new_bets
        
    def get_stats(self) -> Dict:
        """Get bot statistics"""
        return {
            "total_bets": self.state.total_bets,
            "open_bets": self.state.open_bets,
            "won_bets": self.state.won_bets,
            "lost_bets": self.state.lost_bets,
            "total_invested": self.state.total_invested,
            "total_returns": self.state.total_returns,
            "current_exposure": self.state.current_exposure,
            "roi_pct": ((self.state.total_returns - self.state.total_invested) / max(self.state.total_invested, 1)) * 100,
            "win_rate": self.state.won_bets / max(self.state.total_bets, 1) * 100,
            "bets_today": self.state.bets_today
        }
        
    def print_status(self):
        """Print current status"""
        stats = self.get_stats()
        
        print("\n" + "=" * 60)
        print("🎯 TAIL BOT STATUS")
        print("=" * 60)
        print(f"Mode: {'PAPER' if self.config.paper_trading else 'LIVE'}")
        print(f"Total Bets: {stats['total_bets']}")
        print(f"Open Bets: {stats['open_bets']}")
        print(f"Won/Lost: {stats['won_bets']}/{stats['lost_bets']}")
        print(f"Total Invested: ${stats['total_invested']:.2f}")
        print(f"Total Returns: ${stats['total_returns']:.2f}")
        print(f"ROI: {stats['roi_pct']:.1f}%")
        print(f"Current Exposure: ${stats['current_exposure']:.2f}")
        print("=" * 60)
        
    async def run(self, cycles: int = None):
        """Run the bot"""
        print("\n" + "=" * 60)
        print("🚀 TAIL BOT STARTED")
        print(f"   Max YES Price: ${self.config.max_yes_price}")
        print(f"   Stake per Bet: ${self.config.stake_usd}")
        print(f"   Scan Interval: {self.config.sleep_seconds}s")
        print(f"   Paper Trading: {self.config.paper_trading}")
        print("=" * 60 + "\n")
        
        cycle = 0
        
        try:
            while cycles is None or cycle < cycles:
                now = datetime.now(timezone.utc).isoformat()
                print(f"\n[{now}] Cycle {cycle + 1}")
                
                new_bets = self.run_scan_cycle()
                
                if new_bets:
                    for bet in new_bets:
                        print(f"   🎯 NEW BET: {bet.id}")
                        print(f"      Price: ${bet.entry_price:.3f}")
                        print(f"      Potential: ${bet.potential_return:.0f}")
                        print(f"      Question: {bet.question[:50]}...")
                        
                self.print_status()
                
                cycle += 1
                
                if cycles is None or cycle < cycles:
                    await asyncio.sleep(self.config.sleep_seconds)
                    
        except KeyboardInterrupt:
            print("\n⏹️ Bot stopped by user")
            
        self.print_status()


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Tail Betting Bot")
    parser.add_argument("--max-price", type=float, default=0.04, help="Max YES price")
    parser.add_argument("--stake", type=float, default=2.0, help="Stake per bet")
    parser.add_argument("--cycles", type=int, default=5, help="Number of cycles (0=infinite)")
    parser.add_argument("--live", action="store_true", help="Enable live trading")
    
    args = parser.parse_args()
    
    config = TailBotConfig(
        max_yes_price=args.max_price,
        stake_usd=args.stake,
        paper_trading=not args.live
    )
    
    bot = TailBot(config)
    
    cycles = args.cycles if args.cycles > 0 else None
    asyncio.run(bot.run(cycles=cycles))


if __name__ == "__main__":
    main()
