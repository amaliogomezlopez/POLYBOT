"""
Paper Trading Runner - Optimized Version
Runs without external AI dependency for testing.
Saves all metrics for future gradient-based optimization.
"""

import os
import sys
import json
import time
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.paper_trader import PaperTrader, TradeStatus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass 
class TradeRecord:
    """Complete trade record for analysis"""
    id: str
    timestamp: float
    datetime_str: str
    asset: str
    side: str
    entry_price: float
    size_usdc: float
    tokens: float
    
    # Prediction
    prediction_source: str  # "ai", "momentum", "random", "contrarian"
    prediction_confidence: float
    prediction_features: Dict[str, float] = field(default_factory=dict)
    
    # Market state at entry
    market_state: Dict[str, Any] = field(default_factory=dict)
    
    # Timing
    execution_time_ms: float = 0
    
    # Outcome (filled after resolution)
    outcome: Optional[str] = None
    pnl: float = 0.0
    actual_direction: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SessionMetrics:
    """Session-level metrics for optimization"""
    session_id: str
    start_time: float
    end_time: float = 0
    
    # Performance
    starting_balance: float = 100.0
    ending_balance: float = 100.0
    total_pnl: float = 0.0
    max_balance: float = 100.0
    min_balance: float = 100.0
    max_drawdown: float = 0.0
    
    # Trade stats
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    
    # Strategy stats by source
    stats_by_source: Dict[str, Dict] = field(default_factory=dict)
    
    # Timing
    avg_execution_ms: float = 0
    
    def to_dict(self) -> Dict:
        return asdict(self)


class SimplePredictorEngine:
    """
    Simple prediction engine with multiple strategies.
    Designed to be replaced by ML model later.
    """
    
    def __init__(self):
        self.strategies = ["momentum", "mean_reversion", "random", "contrarian"]
        self.current_strategy = "momentum"
        
        # Track strategy performance for future optimization
        self.strategy_results: Dict[str, List[bool]] = {s: [] for s in self.strategies}
    
    def predict(
        self, 
        market_state: Dict[str, float],
        strategy: Optional[str] = None
    ) -> tuple[str, float, str]:
        """
        Generate prediction.
        
        Returns: (direction, confidence, strategy_used)
        """
        strat = strategy or self.current_strategy
        
        if strat == "momentum":
            return self._momentum_predict(market_state)
        elif strat == "mean_reversion":
            return self._mean_reversion_predict(market_state)
        elif strat == "contrarian":
            return self._contrarian_predict(market_state)
        else:
            return self._random_predict()
    
    def _momentum_predict(self, state: Dict) -> tuple[str, float, str]:
        """Follow the trend"""
        trend = state.get("trend", 0)
        if trend > 0.5:
            return "UP", min(0.5 + trend * 0.3, 0.85), "momentum"
        elif trend < -0.5:
            return "DOWN", min(0.5 + abs(trend) * 0.3, 0.85), "momentum"
        return random.choice(["UP", "DOWN"]), 0.55, "momentum"
    
    def _mean_reversion_predict(self, state: Dict) -> tuple[str, float, str]:
        """Bet against extreme moves"""
        trend = state.get("trend", 0)
        if trend > 1.0:  # Overbought
            return "DOWN", min(0.5 + abs(trend) * 0.2, 0.80), "mean_reversion"
        elif trend < -1.0:  # Oversold
            return "UP", min(0.5 + abs(trend) * 0.2, 0.80), "mean_reversion"
        return random.choice(["UP", "DOWN"]), 0.50, "mean_reversion"
    
    def _contrarian_predict(self, state: Dict) -> tuple[str, float, str]:
        """Always bet against momentum"""
        trend = state.get("trend", 0)
        if trend > 0:
            return "DOWN", 0.55, "contrarian"
        return "UP", 0.55, "contrarian"
    
    def _random_predict(self) -> tuple[str, float, str]:
        """Random baseline"""
        return random.choice(["UP", "DOWN"]), 0.50, "random"
    
    def record_result(self, strategy: str, won: bool):
        """Record result for strategy optimization"""
        if strategy in self.strategy_results:
            self.strategy_results[strategy].append(won)
    
    def get_strategy_stats(self) -> Dict[str, Dict]:
        """Get win rates by strategy"""
        stats = {}
        for strat, results in self.strategy_results.items():
            if results:
                wins = sum(results)
                total = len(results)
                stats[strat] = {
                    "total": total,
                    "wins": wins,
                    "losses": total - wins,
                    "win_rate": wins / total
                }
            else:
                stats[strat] = {"total": 0, "wins": 0, "losses": 0, "win_rate": 0}
        return stats


class OptimizedPaperTrader:
    """
    Optimized paper trading system.
    Tracks all data for gradient-based optimization.
    """
    
    DATA_DIR = Path("data/paper_trading_v2")
    
    def __init__(self, initial_balance: float = 100.0):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        self.paper_trader = PaperTrader(
            initial_balance=initial_balance,
            data_dir=str(self.DATA_DIR)
        )
        self.predictor = SimplePredictorEngine()
        
        # Session tracking
        self.session_id = f"sess_{int(time.time())}"
        self.session = SessionMetrics(
            session_id=self.session_id,
            start_time=time.time(),
            starting_balance=initial_balance,
            ending_balance=initial_balance,
            max_balance=initial_balance,
            min_balance=initial_balance
        )
        
        # Trade records
        self.trades: List[TradeRecord] = []
        
        # Files
        self.trades_file = self.DATA_DIR / f"trades_{self.session_id}.json"
        self.sessions_file = self.DATA_DIR / "all_sessions.json"
        
        logger.info(f"OptimizedPaperTrader initialized")
        logger.info(f"Session: {self.session_id}")
        logger.info(f"Balance: ${initial_balance:.2f}")
    
    def execute_trade(
        self,
        asset: str = "BTC",
        strategy: str = "momentum"
    ) -> Optional[TradeRecord]:
        """Execute a single trade with full tracking"""
        start_time = time.time()
        
        # Simulate market state
        market_state = self._generate_market_state(asset)
        
        # Get prediction
        direction, confidence, strat_used = self.predictor.predict(market_state, strategy)
        
        # Skip low confidence
        if confidence < 0.55:
            logger.info(f"⏭️ Skip {asset}: Low confidence ({confidence:.0%})")
            return None
        
        # Calculate position size (Kelly-inspired)
        # size = bankroll * edge * confidence
        edge = (confidence - 0.5) * 2  # 0.55 -> 0.1, 0.75 -> 0.5
        max_risk = 0.15  # Max 15% of balance per trade
        size_pct = min(edge * confidence, max_risk)
        size_usdc = max(1.0, self.paper_trader.balance * size_pct)
        
        if size_usdc > self.paper_trader.balance:
            logger.warning(f"Insufficient balance: ${self.paper_trader.balance:.2f}")
            return None
        
        # Simulate entry price
        entry_price = market_state["current_price"]
        
        # Execute paper trade
        paper_trade = self.paper_trader.place_trade(
            asset=asset,
            market_id=f"sim_{asset}_{int(time.time()*1000)}",
            market_question=f"Will {asset} go {direction}?",
            side=direction,
            entry_price=entry_price,
            size_usdc=size_usdc,
            ai_bias=direction,
            ai_confidence=confidence,
            notes=f"Strategy: {strat_used}"
        )
        
        exec_time = (time.time() - start_time) * 1000
        
        # Create detailed record
        record = TradeRecord(
            id=paper_trade.id,
            timestamp=time.time(),
            datetime_str=datetime.now().isoformat(),
            asset=asset,
            side=direction,
            entry_price=entry_price,
            size_usdc=size_usdc,
            tokens=paper_trade.tokens_bought,
            prediction_source=strat_used,
            prediction_confidence=confidence,
            prediction_features={
                "trend": market_state["trend"],
                "volatility": market_state["volatility"],
                "momentum": market_state["momentum"]
            },
            market_state=market_state,
            execution_time_ms=exec_time
        )
        
        self.trades.append(record)
        self._update_session()
        
        logger.info(
            f"📝 {direction} {asset} @ ${entry_price:.2f} | "
            f"${size_usdc:.2f} | Conf: {confidence:.0%} | "
            f"Strat: {strat_used} | {exec_time:.0f}ms"
        )
        
        return record
    
    def resolve_trade(
        self,
        trade_id: str,
        actual_direction: str  # What actually happened: "UP" or "DOWN"
    ) -> Optional[TradeRecord]:
        """Resolve a trade with actual market outcome"""
        
        # Find record
        record = None
        for r in self.trades:
            if r.id == trade_id:
                record = r
                break
        
        if not record:
            logger.error(f"Trade not found: {trade_id}")
            return None
        
        # Determine if won
        won = (record.side == actual_direction)
        
        # Resolve in paper trader
        self.paper_trader.resolve_trade(trade_id, won)
        
        # Get updated PnL from paper trade
        for pt in self.paper_trader._trades:
            if pt.id == trade_id:
                record.pnl = pt.pnl
                break
        
        # Update record
        record.outcome = "win" if won else "loss"
        record.actual_direction = actual_direction
        
        # Update predictor stats
        self.predictor.record_result(record.prediction_source, won)
        
        # Update session
        self._update_session()
        
        emoji = "✅" if won else "❌"
        logger.info(f"{emoji} {record.side} {record.asset} → {actual_direction} | P&L: ${record.pnl:+.2f}")
        
        return record
    
    def run_simulation(
        self,
        num_trades: int = 20,
        market_bias: float = 0.50,  # Probability market goes UP
        strategies: List[str] = None
    ) -> SessionMetrics:
        """
        Run complete simulation.
        
        Args:
            num_trades: Number of trades to execute
            market_bias: Probability of UP (0.5 = fair, >0.5 = bullish)
            strategies: List of strategies to rotate through
        """
        strategies = strategies or ["momentum", "mean_reversion", "contrarian"]
        
        print("\n" + "="*60)
        print("🚀 OPTIMIZED PAPER TRADING SIMULATION")
        print("="*60)
        print(f"Trades: {num_trades}")
        print(f"Market Bias: {market_bias:.0%} UP")
        print(f"Strategies: {', '.join(strategies)}")
        print(f"Starting Balance: ${self.paper_trader.balance:.2f}")
        print("="*60 + "\n")
        
        for i in range(num_trades):
            # Rotate strategies
            strategy = strategies[i % len(strategies)]
            asset = random.choice(["BTC", "ETH"])
            
            print(f"\n--- Trade {i+1}/{num_trades} ({strategy}) ---")
            
            record = self.execute_trade(asset, strategy)
            
            if record:
                # Simulate market outcome
                actual_up = random.random() < market_bias
                actual_direction = "UP" if actual_up else "DOWN"
                
                # Small delay for realism
                time.sleep(0.1)
                
                self.resolve_trade(record.id, actual_direction)
        
        # Finalize session
        self.session.end_time = time.time()
        self.session.stats_by_source = self.predictor.get_strategy_stats()
        
        # Calculate final metrics
        exec_times = [t.execution_time_ms for t in self.trades if t.execution_time_ms > 0]
        self.session.avg_execution_ms = sum(exec_times) / len(exec_times) if exec_times else 0
        
        # Save all data
        self._save_data()
        
        # Print results
        self._print_results()
        
        return self.session
    
    def _generate_market_state(self, asset: str) -> Dict[str, float]:
        """Generate simulated market state"""
        return {
            "asset": asset,
            "current_price": random.uniform(0.35, 0.65),
            "trend": random.gauss(0, 1),  # -3 to +3 roughly
            "volatility": random.uniform(0.5, 2.0),
            "momentum": random.gauss(0, 0.5),
            "volume_ratio": random.uniform(0.5, 2.0),
            "time_of_day": datetime.now().hour
        }
    
    def _update_session(self):
        """Update session metrics"""
        balance = self.paper_trader.balance
        
        self.session.ending_balance = balance
        self.session.total_pnl = balance - self.session.starting_balance
        
        if balance > self.session.max_balance:
            self.session.max_balance = balance
        if balance < self.session.min_balance:
            self.session.min_balance = balance
        
        # Drawdown
        if self.session.max_balance > 0:
            dd = (self.session.max_balance - balance) / self.session.max_balance
            self.session.max_drawdown = max(self.session.max_drawdown, dd)
        
        # Trade counts
        resolved = [t for t in self.trades if t.outcome]
        self.session.total_trades = len(self.trades)
        self.session.wins = sum(1 for t in resolved if t.outcome == "win")
        self.session.losses = sum(1 for t in resolved if t.outcome == "loss")
    
    def _save_data(self):
        """Save all data to files"""
        # Save trades
        with open(self.trades_file, 'w') as f:
            json.dump([t.to_dict() for t in self.trades], f, indent=2)
        
        # Append to sessions history
        sessions = []
        if self.sessions_file.exists():
            with open(self.sessions_file, 'r') as f:
                sessions = json.load(f)
        
        sessions.append(self.session.to_dict())
        
        with open(self.sessions_file, 'w') as f:
            json.dump(sessions, f, indent=2)
        
        logger.info(f"Data saved to {self.DATA_DIR}")
    
    def _print_results(self):
        """Print detailed results"""
        print("\n" + "="*60)
        print("📊 SIMULATION RESULTS")
        print("="*60)
        
        s = self.session
        print(f"\n💰 Portfolio:")
        print(f"   Starting: ${s.starting_balance:.2f}")
        print(f"   Ending: ${s.ending_balance:.2f}")
        print(f"   P&L: ${s.total_pnl:+.2f} ({s.total_pnl/s.starting_balance*100:+.1f}%)")
        print(f"   Peak: ${s.max_balance:.2f}")
        print(f"   Max Drawdown: {s.max_drawdown*100:.1f}%")
        
        win_rate = s.wins / (s.wins + s.losses) if (s.wins + s.losses) > 0 else 0
        print(f"\n📈 Trades:")
        print(f"   Total: {s.total_trades}")
        print(f"   Wins: {s.wins}")
        print(f"   Losses: {s.losses}")
        print(f"   Win Rate: {win_rate:.1%}")
        
        print(f"\n🎯 Strategy Performance:")
        for strat, stats in s.stats_by_source.items():
            if stats["total"] > 0:
                wr = stats["win_rate"]
                print(f"   {strat:15} | {stats['wins']:2}W/{stats['losses']:2}L | WR: {wr:.0%}")
        
        print(f"\n⚡ Performance:")
        print(f"   Avg Execution: {s.avg_execution_ms:.1f}ms")
        print(f"   Duration: {s.end_time - s.start_time:.1f}s")
        
        print(f"\n📁 Data: {self.DATA_DIR}")


def main():
    """Run simulation"""
    trader = OptimizedPaperTrader(initial_balance=100.0)
    
    # Run with different market conditions
    session = trader.run_simulation(
        num_trades=20,
        market_bias=0.52,  # Slight bullish bias
        strategies=["momentum", "mean_reversion", "contrarian"]
    )
    
    print("\n✅ Simulation complete!")


if __name__ == "__main__":
    main()
