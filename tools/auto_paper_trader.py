"""
Automated Paper Trading Runner
Executes trades automatically with AI predictions and tracks all metrics.
"""

import os
import sys
import asyncio
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.paper_trader import PaperTrader, PaperTrade, TradeStatus
from src.ai.gemini_client import GeminiClient
from src.ai.bias_analyzer import BiasAnalyzer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class TradeMetrics:
    """Detailed metrics for each trade"""
    trade_id: str
    timestamp: float
    asset: str
    side: str
    
    # Timing metrics (ms)
    ai_latency_ms: float
    total_latency_ms: float
    
    # AI metrics
    ai_prediction: str
    ai_confidence: float
    ai_aligned: bool  # Did we follow AI?
    
    # Trade metrics
    entry_price: float
    size_usdc: float
    tokens: float
    
    # Result (filled after resolution)
    outcome: Optional[str] = None  # "win", "loss", None
    pnl: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MetricsTracker:
    """Tracks and persists all trading metrics"""
    
    def __init__(self, data_dir: str = "data/paper_trading"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.data_dir / "metrics.json"
        self.session_file = self.data_dir / "sessions.json"
        
        self.metrics: List[TradeMetrics] = self._load_metrics()
        self.session_start = time.time()
        self.session_id = f"session_{int(self.session_start)}"
    
    def record(self, metric: TradeMetrics) -> None:
        """Record a trade metric"""
        self.metrics.append(metric)
        self._save_metrics()
    
    def update_outcome(self, trade_id: str, outcome: str, pnl: float) -> None:
        """Update trade outcome after resolution"""
        for m in self.metrics:
            if m.trade_id == trade_id:
                m.outcome = outcome
                m.pnl = pnl
                break
        self._save_metrics()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        if not self.metrics:
            return {
                "session_id": self.session_id,
                "total_trades": 0,
                "resolved": 0,
                "pending": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "ai_accuracy": 0,
                "avg_ai_latency_ms": 0,
                "avg_total_latency_ms": 0,
            }
        
        resolved = [m for m in self.metrics if m.outcome is not None]
        wins = [m for m in resolved if m.outcome == "win"]
        losses = [m for m in resolved if m.outcome == "loss"]
        
        # AI accuracy
        ai_aligned = [m for m in resolved if m.ai_aligned]
        ai_correct = [m for m in ai_aligned if m.outcome == "win"]
        
        return {
            "session_id": self.session_id,
            "total_trades": len(self.metrics),
            "resolved": len(resolved),
            "pending": len(self.metrics) - len(resolved),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(resolved) if resolved else 0,
            "total_pnl": sum(m.pnl for m in resolved),
            "avg_pnl": sum(m.pnl for m in resolved) / len(resolved) if resolved else 0,
            "ai_accuracy": len(ai_correct) / len(ai_aligned) if ai_aligned else 0,
            "avg_ai_latency_ms": sum(m.ai_latency_ms for m in self.metrics) / len(self.metrics),
            "avg_total_latency_ms": sum(m.total_latency_ms for m in self.metrics) / len(self.metrics),
        }
    
    def _load_metrics(self) -> List[TradeMetrics]:
        """Load metrics from file"""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    return [TradeMetrics(**m) for m in data]
            except Exception as e:
                logger.error(f"Error loading metrics: {e}")
        return []
    
    def _save_metrics(self) -> None:
        """Save metrics to file"""
        with open(self.metrics_file, 'w') as f:
            json.dump([m.to_dict() for m in self.metrics], f, indent=2)


class AutomatedPaperTrader:
    """
    Automated paper trading with AI predictions.
    Simulates real trading conditions with timing metrics.
    """
    
    def __init__(self, initial_balance: float = 100.0):
        self.paper_trader = PaperTrader(
            initial_balance=initial_balance,
            data_dir="data/paper_trading"
        )
        self.gemini = GeminiClient()
        self.bias_analyzer = BiasAnalyzer(self.gemini)
        self.metrics = MetricsTracker()
        
        # Trading parameters
        self.min_confidence = 0.60  # Minimum AI confidence to trade
        self.base_size = 2.0        # Base trade size USDC
        self.max_size = 10.0        # Max trade size USDC
        
        logger.info(f"AutomatedPaperTrader initialized")
        logger.info(f"Balance: ${self.paper_trader.balance:.2f}")
    
    async def execute_trade(
        self,
        asset: str,
        simulated_price: float,
        follow_ai: bool = True
    ) -> Optional[PaperTrade]:
        """
        Execute a single paper trade with full metrics tracking.
        
        Args:
            asset: BTC or ETH
            simulated_price: Current market price for the side
            follow_ai: Whether to follow AI prediction
            
        Returns:
            PaperTrade if executed, None if skipped
        """
        start_time = time.time()
        
        # Get AI prediction
        ai_start = time.time()
        try:
            # Create simulated market data
            market_data = {
                "price": simulated_price,
                "price_change_1h": random.uniform(-2, 2),
                "price_change_24h": random.uniform(-5, 5),
                "volume_24h": random.uniform(1e9, 5e9),
                "trend": random.choice(["bullish", "bearish", "neutral"]),
                "volatility": random.uniform(0.5, 2.0)
            }
            bias = self.bias_analyzer.analyze(market_data, asset=asset)
            ai_prediction = bias.bias.value
            ai_confidence = bias.confidence
        except Exception as e:
            logger.error(f"AI error: {e}")
            ai_prediction = random.choice(["UP", "DOWN"])
            ai_confidence = 0.5
        ai_latency = (time.time() - ai_start) * 1000
        
        # Decision
        if ai_confidence < self.min_confidence:
            logger.info(f"⏭️ Skipping {asset}: Low confidence ({ai_confidence:.0%})")
            return None
        
        # Determine side
        side = ai_prediction if follow_ai else ("DOWN" if ai_prediction == "UP" else "UP")
        ai_aligned = (side == ai_prediction)
        
        # Position sizing based on confidence
        confidence_multiplier = (ai_confidence - 0.5) * 4  # 0.5->0, 0.75->1, 1.0->2
        size_usdc = min(
            self.base_size * (1 + confidence_multiplier),
            self.max_size,
            self.paper_trader.balance * 0.2  # Max 20% of balance per trade
        )
        
        if size_usdc < 0.50:
            logger.info(f"⏭️ Skipping {asset}: Size too small (${size_usdc:.2f})")
            return None
        
        # Execute trade
        trade = self.paper_trader.place_trade(
            asset=asset,
            market_id=f"sim_{asset.lower()}_{int(time.time())}",
            market_question=f"Will {asset} go {side}?",
            side=side,
            entry_price=simulated_price,
            size_usdc=size_usdc,
            ai_bias=ai_prediction,
            ai_confidence=ai_confidence,
            notes=f"Automated trade, AI aligned: {ai_aligned}"
        )
        
        total_latency = (time.time() - start_time) * 1000
        
        # Record metrics
        metric = TradeMetrics(
            trade_id=trade.id,
            timestamp=time.time(),
            asset=asset,
            side=side,
            ai_latency_ms=ai_latency,
            total_latency_ms=total_latency,
            ai_prediction=ai_prediction,
            ai_confidence=ai_confidence,
            ai_aligned=ai_aligned,
            entry_price=simulated_price,
            size_usdc=size_usdc,
            tokens=trade.tokens_bought
        )
        self.metrics.record(metric)
        
        logger.info(
            f"📝 TRADE: {side} {asset} @ ${simulated_price:.2f} | "
            f"${size_usdc:.2f} | AI: {ai_prediction} ({ai_confidence:.0%}) | "
            f"Latency: {total_latency:.0f}ms"
        )
        
        return trade
    
    def simulate_resolution(self, trade: PaperTrade, market_went_up: bool) -> None:
        """
        Simulate trade resolution based on market outcome.
        
        Args:
            trade: The trade to resolve
            market_went_up: Whether the market actually went up
        """
        # Determine if trade won
        if trade.side == "UP":
            won = market_went_up
        else:
            won = not market_went_up
        
        # Resolve
        self.paper_trader.resolve_trade(trade.id, won)
        
        # Update metrics
        outcome = "win" if won else "loss"
        self.metrics.update_outcome(trade.id, outcome, trade.pnl)
        
        emoji = "✅" if won else "❌"
        logger.info(f"{emoji} RESOLVED: {trade.side} {trade.asset} | P&L: ${trade.pnl:+.2f}")
    
    async def run_simulation(
        self,
        num_trades: int = 10,
        win_probability: float = 0.55
    ) -> Dict[str, Any]:
        """
        Run a full trading simulation.
        
        Args:
            num_trades: Number of trades to execute
            win_probability: Simulated market win rate (for UP predictions)
            
        Returns:
            Simulation results
        """
        print("\n" + "="*60)
        print("🚀 AUTOMATED PAPER TRADING SIMULATION")
        print("="*60)
        print(f"Trades: {num_trades} | Win Prob: {win_probability:.0%}")
        print(f"Starting Balance: ${self.paper_trader.balance:.2f}")
        print("="*60 + "\n")
        
        trades_executed = []
        
        for i in range(num_trades):
            print(f"\n--- Trade {i+1}/{num_trades} ---")
            
            # Random asset
            asset = random.choice(["BTC", "ETH"])
            
            # Simulate market price (realistic range)
            simulated_price = random.uniform(0.35, 0.65)
            
            # Execute trade
            trade = await self.execute_trade(asset, simulated_price)
            
            if trade:
                trades_executed.append(trade)
                
                # Simulate immediate resolution (in real trading, we'd wait)
                # This simulates whether the market actually went UP
                actual_up = random.random() < win_probability
                
                # Small delay to simulate market resolution
                await asyncio.sleep(0.1)
                
                self.simulate_resolution(trade, actual_up)
            
            # Rate limiting
            await asyncio.sleep(0.5)
        
        # Final summary
        summary = self.metrics.get_summary()
        stats = self.paper_trader.get_stats()
        
        print("\n" + "="*60)
        print("📊 SIMULATION RESULTS")
        print("="*60)
        
        print(f"\n💰 Portfolio:")
        print(f"   Final Balance: ${self.paper_trader.balance:.2f}")
        print(f"   Total P&L: ${summary['total_pnl']:+.2f}")
        print(f"   ROI: {stats['portfolio']['roi']}")
        
        print(f"\n📈 Trades:")
        print(f"   Executed: {summary['total_trades']}")
        print(f"   Wins: {summary['wins']}")
        print(f"   Losses: {summary['losses']}")
        print(f"   Win Rate: {summary['win_rate']:.1%}")
        
        print(f"\n🤖 AI Performance:")
        print(f"   AI Accuracy: {summary['ai_accuracy']:.1%}")
        
        print(f"\n⚡ Latency:")
        print(f"   Avg AI Latency: {summary['avg_ai_latency_ms']:.0f}ms")
        print(f"   Avg Total Latency: {summary['avg_total_latency_ms']:.0f}ms")
        
        print(f"\n📁 Data saved to: data/paper_trading/")
        
        return {
            "summary": summary,
            "stats": stats,
            "trades_executed": len(trades_executed)
        }


async def main():
    """Run automated paper trading simulation"""
    trader = AutomatedPaperTrader(initial_balance=100.0)
    
    # Run simulation with realistic parameters
    results = await trader.run_simulation(
        num_trades=10,
        win_probability=0.52  # Slightly better than coin flip
    )
    
    print("\n✅ Simulation complete!")
    print(f"Check data/paper_trading/ for detailed metrics")


if __name__ == "__main__":
    asyncio.run(main())
