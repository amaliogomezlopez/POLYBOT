"""
Tail Betting Backtester
Analyzes historical Polymarket data to validate tail betting strategy
"""

import json
import httpx
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import random


@dataclass
class HistoricalMarket:
    """Historical market for backtesting"""
    condition_id: str
    question: str
    outcome: str  # "Yes" or "No"
    yes_price_at_snapshot: float  # Price when we would have bet
    resolved_at: Optional[str] = None


@dataclass 
class BacktestResult:
    """Result of a single backtest bet"""
    question: str
    entry_price: float
    stake: float
    outcome: str
    won: bool
    return_amount: float
    profit: float
    multiplier: float


class TailBacktester:
    """
    Backtest tail betting strategy on historical data
    """
    
    GAMMA_API = "https://gamma-api.polymarket.com"
    
    def __init__(
        self,
        max_yes_price: float = 0.04,
        stake_usd: float = 2.0,
        min_markets: int = 100
    ):
        self.max_yes_price = max_yes_price
        self.stake_usd = stake_usd
        self.min_markets = min_markets
        self.results_dir = Path("data/backtest")
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    async def fetch_resolved_markets(self, limit: int = 500) -> list[dict]:
        """
        Fetch resolved markets from Gamma API
        These are markets that have already concluded
        """
        print(f"📥 Fetching resolved markets (limit={limit})...")
        
        resolved_markets = []
        offset = 0
        page_size = 100
        
        async with httpx.AsyncClient(timeout=30) as client:
            while len(resolved_markets) < limit:
                try:
                    # Fetch closed/resolved markets
                    params = {
                        "closed": "true",
                        "limit": page_size,
                        "offset": offset,
                        "order": "endDate",
                        "ascending": "false"
                    }
                    
                    resp = await client.get(f"{self.GAMMA_API}/markets", params=params)
                    
                    if resp.status_code != 200:
                        print(f"❌ API error: {resp.status_code}")
                        break
                    
                    data = resp.json()
                    
                    if not data:
                        break
                    
                    for market in data:
                        # Only include markets with valid outcomes
                        if market.get("outcome") in ["Yes", "No"]:
                            resolved_markets.append(market)
                    
                    offset += page_size
                    print(f"   Fetched {len(resolved_markets)} resolved markets...")
                    
                    await asyncio.sleep(0.2)  # Rate limiting
                    
                except Exception as e:
                    print(f"❌ Error fetching markets: {e}")
                    break
        
        print(f"✅ Total resolved markets: {len(resolved_markets)}")
        return resolved_markets
    
    def simulate_tail_opportunities(
        self,
        resolved_markets: list[dict],
        simulated_low_prices: bool = True
    ) -> list[dict]:
        """
        Identify markets that would have qualified as tail bets
        
        Since we don't have historical price data, we can:
        1. Use current/final prices and assume similar prices existed
        2. Simulate random low prices for testing
        """
        tail_opportunities = []
        
        for market in resolved_markets:
            outcome = market.get("outcome")
            
            # We need markets where YES was very cheap at some point
            # For backtesting, we'll simulate that some markets had tail prices
            
            if simulated_low_prices:
                # Simulate: assume ~5% of markets had a tail opportunity at some point
                # This is a rough estimate based on Polymarket patterns
                if random.random() < 0.05:
                    # Simulate a tail price (1-4 cents)
                    simulated_price = random.uniform(0.01, 0.04)
                    
                    tail_opportunities.append({
                        "condition_id": market.get("conditionId", market.get("id")),
                        "question": market.get("question", ""),
                        "outcome": outcome,
                        "entry_price": simulated_price,
                        "resolved_at": market.get("endDate")
                    })
            else:
                # Use actual outcomePrice if available
                # This is less accurate but uses real data
                tokens = market.get("tokens", [])
                for token in tokens:
                    if token.get("outcome") == "Yes":
                        price = float(token.get("price", 1))
                        if price <= self.max_yes_price:
                            tail_opportunities.append({
                                "condition_id": market.get("conditionId", market.get("id")),
                                "question": market.get("question", ""),
                                "outcome": outcome,
                                "entry_price": price,
                                "resolved_at": market.get("endDate")
                            })
        
        return tail_opportunities
    
    def run_backtest(
        self,
        tail_opportunities: list[dict],
        verbose: bool = True
    ) -> dict:
        """
        Run backtest on tail opportunities
        """
        print(f"\n🎲 Running backtest on {len(tail_opportunities)} tail opportunities...")
        print(f"   Strategy: ${self.stake_usd} per bet, YES < ${self.max_yes_price}")
        print("")
        
        results = []
        total_invested = 0.0
        total_returned = 0.0
        wins = 0
        losses = 0
        
        for opp in tail_opportunities:
            entry_price = opp["entry_price"]
            outcome = opp["outcome"]
            stake = self.stake_usd
            
            # Calculate position size
            size = stake / entry_price
            
            # Determine if we won (YES resolved to 1.0)
            won = outcome == "Yes"
            
            if won:
                return_amount = size  # Each token worth $1
                profit = return_amount - stake
                multiplier = return_amount / stake
                wins += 1
            else:
                return_amount = 0.0
                profit = -stake
                multiplier = 0.0
                losses += 1
            
            total_invested += stake
            total_returned += return_amount
            
            result = BacktestResult(
                question=opp["question"][:60],
                entry_price=entry_price,
                stake=stake,
                outcome=outcome,
                won=won,
                return_amount=return_amount,
                profit=profit,
                multiplier=multiplier
            )
            results.append(result)
            
            if verbose and won:
                print(f"   ✅ WON: {opp['question'][:50]}...")
                print(f"      Entry: ${entry_price:.4f} → Return: ${return_amount:.2f} ({multiplier:.0f}x)")
        
        # Calculate summary statistics
        net_profit = total_returned - total_invested
        hit_rate = wins / len(results) * 100 if results else 0
        roi = (total_returned / total_invested - 1) * 100 if total_invested > 0 else 0
        
        avg_win_mult = 0
        if wins > 0:
            win_results = [r for r in results if r.won]
            avg_win_mult = sum(r.multiplier for r in win_results) / wins
        
        # Required hit rate calculation
        # If avg win = Nx stake, we need 1/N hit rate to break even
        required_hit_rate = (1 / avg_win_mult * 100) if avg_win_mult > 0 else 100
        
        summary = {
            "total_bets": len(results),
            "wins": wins,
            "losses": losses,
            "hit_rate": hit_rate,
            "total_invested": total_invested,
            "total_returned": total_returned,
            "net_profit": net_profit,
            "roi": roi,
            "avg_win_multiplier": avg_win_mult,
            "required_hit_rate": required_hit_rate,
            "profitable": hit_rate > required_hit_rate,
            "results": [
                {
                    "question": r.question,
                    "entry_price": r.entry_price,
                    "won": r.won,
                    "profit": r.profit,
                    "multiplier": r.multiplier
                }
                for r in results
            ]
        }
        
        return summary
    
    def print_backtest_report(self, summary: dict):
        """Print formatted backtest report"""
        print("")
        print("=" * 70)
        print("📊 TAIL BETTING BACKTEST REPORT")
        print("=" * 70)
        print("")
        print(f"🎯 Strategy Parameters:")
        print(f"   Max YES Price:  ${self.max_yes_price}")
        print(f"   Stake per Bet:  ${self.stake_usd}")
        print("")
        print(f"📈 Results:")
        print(f"   Total Bets:     {summary['total_bets']}")
        print(f"   Wins:           {summary['wins']} ✅")
        print(f"   Losses:         {summary['losses']} ❌")
        print(f"   Hit Rate:       {summary['hit_rate']:.2f}%")
        print("")
        print(f"💰 Financial:")
        print(f"   Total Invested: ${summary['total_invested']:.2f}")
        print(f"   Total Returned: ${summary['total_returned']:.2f}")
        print(f"   Net Profit:     ${summary['net_profit']:.2f}")
        print(f"   ROI:            {summary['roi']:.1f}%")
        print("")
        print(f"📉 Break-Even Analysis:")
        print(f"   Avg Win Mult:   {summary['avg_win_multiplier']:.1f}x")
        print(f"   Required Hit:   {summary['required_hit_rate']:.2f}%")
        print(f"   Actual Hit:     {summary['hit_rate']:.2f}%")
        print("")
        
        if summary['profitable']:
            print(f"   ✅ PROFITABLE - Hit rate exceeds required rate!")
            print(f"      Edge: {summary['hit_rate'] - summary['required_hit_rate']:.2f}%")
        else:
            print(f"   ❌ NOT PROFITABLE - Need higher hit rate")
            print(f"      Gap: {summary['required_hit_rate'] - summary['hit_rate']:.2f}%")
        
        print("")
        print("=" * 70)
    
    def monte_carlo_simulation(
        self,
        num_simulations: int = 10000,
        num_bets_per_sim: int = 100,
        true_hit_rate: float = 0.02,  # 2% assumed
        avg_multiplier: float = 50.0  # 50x average
    ) -> dict:
        """
        Monte Carlo simulation to estimate probability of profit
        """
        print(f"\n🎰 Running Monte Carlo Simulation...")
        print(f"   Simulations: {num_simulations}")
        print(f"   Bets per sim: {num_bets_per_sim}")
        print(f"   Hit rate: {true_hit_rate * 100:.1f}%")
        print(f"   Avg multiplier: {avg_multiplier:.0f}x")
        
        profits = []
        wins_distribution = []
        
        for _ in range(num_simulations):
            total_invested = num_bets_per_sim * self.stake_usd
            total_returned = 0.0
            num_wins = 0
            
            for _ in range(num_bets_per_sim):
                # Simulate bet
                if random.random() < true_hit_rate:
                    # Win - multiply stake by random multiplier around avg
                    multiplier = random.uniform(avg_multiplier * 0.5, avg_multiplier * 1.5)
                    total_returned += self.stake_usd * multiplier
                    num_wins += 1
            
            profit = total_returned - total_invested
            profits.append(profit)
            wins_distribution.append(num_wins)
        
        # Calculate statistics
        avg_profit = sum(profits) / len(profits)
        profitable_sims = sum(1 for p in profits if p > 0)
        prob_profit = profitable_sims / num_simulations * 100
        
        # Percentiles
        sorted_profits = sorted(profits)
        p5 = sorted_profits[int(num_simulations * 0.05)]
        p25 = sorted_profits[int(num_simulations * 0.25)]
        p50 = sorted_profits[int(num_simulations * 0.50)]
        p75 = sorted_profits[int(num_simulations * 0.75)]
        p95 = sorted_profits[int(num_simulations * 0.95)]
        
        avg_wins = sum(wins_distribution) / len(wins_distribution)
        max_wins = max(wins_distribution)
        
        result = {
            "num_simulations": num_simulations,
            "num_bets_per_sim": num_bets_per_sim,
            "true_hit_rate": true_hit_rate,
            "avg_multiplier": avg_multiplier,
            "avg_profit": avg_profit,
            "prob_profit": prob_profit,
            "percentiles": {
                "5%": p5,
                "25%": p25,
                "50%": p50,
                "75%": p75,
                "95%": p95
            },
            "avg_wins": avg_wins,
            "max_wins": max_wins
        }
        
        # Print results
        print("")
        print("=" * 70)
        print("🎰 MONTE CARLO SIMULATION RESULTS")
        print("=" * 70)
        print("")
        print(f"📊 Profit Statistics:")
        print(f"   Average Profit:     ${avg_profit:.2f}")
        print(f"   Probability > $0:   {prob_profit:.1f}%")
        print("")
        print(f"📉 Profit Distribution:")
        print(f"    5th percentile:    ${p5:.2f}")
        print(f"   25th percentile:    ${p25:.2f}")
        print(f"   50th percentile:    ${p50:.2f} (median)")
        print(f"   75th percentile:    ${p75:.2f}")
        print(f"   95th percentile:    ${p95:.2f}")
        print("")
        print(f"🎯 Wins per {num_bets_per_sim} bets:")
        print(f"   Average:            {avg_wins:.1f}")
        print(f"   Maximum:            {max_wins}")
        print("")
        
        if prob_profit > 50:
            print(f"   ✅ Strategy is likely profitable (>{50}% chance)")
        else:
            print(f"   ⚠️ Strategy has <50% chance of profit")
        
        print("=" * 70)
        
        return result
    
    def kelly_criterion(
        self,
        hit_rate: float,
        avg_multiplier: float
    ) -> dict:
        """
        Calculate optimal bet sizing using Kelly Criterion
        
        f* = (bp - q) / b
        where:
        - b = odds received on bet (multiplier - 1)
        - p = probability of winning
        - q = probability of losing (1 - p)
        """
        p = hit_rate
        q = 1 - p
        b = avg_multiplier - 1  # Net odds
        
        if b <= 0:
            kelly_fraction = 0
        else:
            kelly_fraction = (b * p - q) / b
        
        # Fractional Kelly for safety
        half_kelly = kelly_fraction / 2
        quarter_kelly = kelly_fraction / 4
        
        # Expected value per bet
        ev_per_bet = p * avg_multiplier - 1  # As fraction of stake
        
        result = {
            "hit_rate": hit_rate,
            "avg_multiplier": avg_multiplier,
            "kelly_fraction": max(0, kelly_fraction),
            "half_kelly": max(0, half_kelly),
            "quarter_kelly": max(0, quarter_kelly),
            "ev_per_bet": ev_per_bet,
            "edge": ev_per_bet * 100
        }
        
        print("")
        print("=" * 70)
        print("📐 KELLY CRITERION ANALYSIS")
        print("=" * 70)
        print("")
        print(f"📊 Inputs:")
        print(f"   Hit Rate:        {hit_rate * 100:.2f}%")
        print(f"   Avg Multiplier:  {avg_multiplier:.1f}x")
        print("")
        print(f"💰 Optimal Bet Sizing:")
        print(f"   Full Kelly:      {kelly_fraction * 100:.2f}% of bankroll")
        print(f"   Half Kelly:      {half_kelly * 100:.2f}% of bankroll")
        print(f"   Quarter Kelly:   {quarter_kelly * 100:.2f}% of bankroll")
        print("")
        print(f"📈 Expected Value:")
        print(f"   EV per Bet:      {ev_per_bet * 100:.2f}% of stake")
        
        if ev_per_bet > 0:
            print(f"   Edge:            +{ev_per_bet * 100:.2f}%")
            print(f"   ✅ POSITIVE EXPECTED VALUE")
        else:
            print(f"   Edge:            {ev_per_bet * 100:.2f}%")
            print(f"   ❌ NEGATIVE EXPECTED VALUE")
        
        print("")
        
        # Practical recommendations
        if kelly_fraction > 0:
            bankroll_example = 1000
            print(f"💡 For ${bankroll_example} bankroll:")
            print(f"   Full Kelly bet:    ${bankroll_example * kelly_fraction:.2f}")
            print(f"   Half Kelly bet:    ${bankroll_example * half_kelly:.2f}")
            print(f"   Quarter Kelly:     ${bankroll_example * quarter_kelly:.2f}")
        
        print("=" * 70)
        
        return result
    
    def save_results(self, summary: dict, filename: str = "backtest_results.json"):
        """Save backtest results to file"""
        filepath = self.results_dir / filename
        filepath.write_text(json.dumps(summary, indent=2))
        print(f"\n💾 Results saved to: {filepath}")


async def run_full_backtest():
    """Run comprehensive backtest analysis"""
    backtester = TailBacktester(
        max_yes_price=0.04,  # Max 4 cents
        stake_usd=2.0        # $2 per bet (Spon's strategy)
    )
    
    print("=" * 70)
    print("🔬 TAIL BETTING STRATEGY VALIDATION")
    print("    Based on @Spon's Polymarket Strategy")
    print("=" * 70)
    
    # 1. Fetch historical resolved markets
    print("\n📥 Phase 1: Fetching Historical Data")
    resolved_markets = await backtester.fetch_resolved_markets(limit=500)
    
    # 2. Simulate tail opportunities
    print("\n🎯 Phase 2: Identifying Tail Opportunities")
    tail_opportunities = backtester.simulate_tail_opportunities(
        resolved_markets,
        simulated_low_prices=True  # Simulate since we don't have historical prices
    )
    print(f"   Found {len(tail_opportunities)} simulated tail opportunities")
    
    # 3. Run backtest if we have opportunities
    if tail_opportunities:
        print("\n📊 Phase 3: Running Backtest")
        summary = backtester.run_backtest(tail_opportunities, verbose=True)
        backtester.print_backtest_report(summary)
        
        # Save results
        backtester.save_results(summary, "backtest_results.json")
    
    # 4. Monte Carlo simulation with different assumptions
    print("\n🎰 Phase 4: Monte Carlo Simulation")
    
    # Conservative estimate (1% hit rate, 40x avg)
    print("\n--- Conservative Scenario ---")
    backtester.monte_carlo_simulation(
        num_simulations=10000,
        num_bets_per_sim=100,
        true_hit_rate=0.01,
        avg_multiplier=40
    )
    
    # Moderate estimate (2% hit rate, 50x avg)
    print("\n--- Moderate Scenario ---")
    backtester.monte_carlo_simulation(
        num_simulations=10000,
        num_bets_per_sim=100,
        true_hit_rate=0.02,
        avg_multiplier=50
    )
    
    # Optimistic estimate (3% hit rate, 60x avg)
    print("\n--- Optimistic Scenario ---")
    backtester.monte_carlo_simulation(
        num_simulations=10000,
        num_bets_per_sim=100,
        true_hit_rate=0.03,
        avg_multiplier=60
    )
    
    # 5. Kelly Criterion analysis
    print("\n📐 Phase 5: Optimal Bet Sizing (Kelly Criterion)")
    
    # Based on @Spon's estimated performance
    backtester.kelly_criterion(
        hit_rate=0.02,  # 2% hit rate
        avg_multiplier=50  # 50x average win
    )
    
    print("\n✅ Backtest complete!")


if __name__ == "__main__":
    asyncio.run(run_full_backtest())
