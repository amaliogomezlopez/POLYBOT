"""
Advanced Paper Trading Runner
Compares LLM vs XGBoost vs Rules vs Hybrid approaches.
Full evaluation with metrics and learning.
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

from src.trading.paper_trader import PaperTrader
from src.ai.groq_client import GroqClient, GroqModel
from src.ai.xgboost_model import XGBoostPredictor, FeatureEngineer, FeatureVector
from src.ai.reward_system import AdaptiveRewardCalculator, TradeOutcome
from src.ai.hybrid_predictor import HybridPredictor, HybridPrediction

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class EvaluationTrade:
    """Complete trade record for evaluation"""
    id: str
    timestamp: float
    asset: str
    
    # Market state
    market_data: Dict[str, float]
    
    # Predictions from each method
    llm_prediction: Optional[str] = None
    llm_confidence: float = 0.0
    llm_latency_ms: float = 0.0
    
    xgb_prediction: Optional[str] = None
    xgb_confidence: float = 0.0
    
    rules_prediction: Optional[str] = None
    rules_confidence: float = 0.0
    
    hybrid_prediction: Optional[str] = None
    hybrid_confidence: float = 0.0
    
    # Final trade
    final_direction: str = "UP"
    final_confidence: float = 0.5
    entry_price: float = 0.5
    size_usdc: float = 2.0
    
    # Outcome
    actual_direction: Optional[str] = None
    pnl: float = 0.0
    
    # Correctness by method
    llm_correct: Optional[bool] = None
    xgb_correct: Optional[bool] = None
    rules_correct: Optional[bool] = None
    hybrid_correct: Optional[bool] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MethodStats:
    """Statistics for a prediction method"""
    name: str
    total: int = 0
    correct: int = 0
    total_pnl: float = 0.0
    total_latency_ms: float = 0.0
    
    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total > 0 else 0
    
    @property
    def avg_latency(self) -> float:
        return self.total_latency_ms / self.total if self.total > 0 else 0


class AdvancedEvaluator:
    """
    Advanced evaluation system comparing all prediction methods.
    """
    
    DATA_DIR = Path("data/evaluation")
    
    def __init__(
        self,
        initial_balance: float = 100.0,
        use_llm: bool = True,
        use_xgboost: bool = True
    ):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Paper trader
        self.paper_trader = PaperTrader(
            initial_balance=initial_balance,
            data_dir=str(self.DATA_DIR / "paper_trading")
        )
        
        # Initialize predictors
        self.use_llm = use_llm
        self.use_xgb = use_xgboost
        
        self.groq: Optional[GroqClient] = None
        self.xgb: Optional[XGBoostPredictor] = None
        
        if use_llm:
            try:
                self.groq = GroqClient(model=GroqModel.LLAMA_33_70B)
                logger.info("✅ GROQ LLM initialized")
            except Exception as e:
                logger.warning(f"❌ GROQ not available: {e}")
                self.use_llm = False
        
        if use_xgboost:
            try:
                self.xgb = XGBoostPredictor()
                logger.info(f"✅ XGBoost initialized (trained: {self.xgb.is_trained})")
            except Exception as e:
                logger.warning(f"❌ XGBoost not available: {e}")
                self.use_xgb = False
        
        # Hybrid predictor
        self.hybrid = HybridPredictor(
            use_llm=use_llm,
            use_xgboost=use_xgboost,
            use_rules=True
        )
        
        # Reward calculator
        self.reward_calc = AdaptiveRewardCalculator()
        
        # Stats by method
        self.stats = {
            "llm": MethodStats("LLM (GROQ)"),
            "xgb": MethodStats("XGBoost"),
            "rules": MethodStats("Rules"),
            "hybrid": MethodStats("Hybrid")
        }
        
        # Trade records
        self.trades: List[EvaluationTrade] = []
        
        # Session info
        self.session_id = f"eval_{int(time.time())}"
        self.session_start = time.time()
        
        logger.info(f"AdvancedEvaluator initialized")
        logger.info(f"LLM: {use_llm}, XGBoost: {use_xgboost}")
    
    def generate_market_data(self, asset: str) -> Dict[str, float]:
        """Generate realistic market data"""
        # Base random state
        trend = random.gauss(0, 1.2)
        momentum = random.gauss(0, 0.8)
        volatility = abs(random.gauss(1.0, 0.5))
        
        return {
            "asset": asset,
            "price": random.uniform(0.35, 0.65),
            "trend": trend,
            "momentum": momentum,
            "volatility": volatility,
            "volume_ratio": random.uniform(0.5, 2.0),
            "price_change_1h": trend * random.uniform(0.5, 1.5),
            "price_change_24h": trend * random.uniform(1, 3)
        }
    
    def simulate_market_outcome(
        self,
        market_data: Dict[str, float],
        base_probability: float = 0.50
    ) -> str:
        """
        Simulate actual market outcome.
        Has slight correlation with market data for realism.
        """
        trend = market_data.get("trend", 0)
        momentum = market_data.get("momentum", 0)
        
        # Base probability adjusted by signals
        # This creates slight edge for correct predictions
        signal = trend * 0.1 + momentum * 0.05
        prob_up = base_probability + signal * 0.1
        prob_up = max(0.3, min(0.7, prob_up))  # Keep somewhat random
        
        return "UP" if random.random() < prob_up else "DOWN"
    
    def evaluate_single(
        self,
        asset: str = "BTC",
        size_usdc: float = 2.0,
        market_bias: float = 0.50
    ) -> EvaluationTrade:
        """Run single evaluation trade"""
        
        # Generate market data
        market_data = self.generate_market_data(asset)
        
        trade = EvaluationTrade(
            id=f"eval_{int(time.time()*1000)}",
            timestamp=time.time(),
            asset=asset,
            market_data=market_data,
            entry_price=market_data["price"],
            size_usdc=size_usdc
        )
        
        # Get predictions from each method
        
        # 1. LLM
        if self.use_llm and self.groq:
            try:
                llm_dir, llm_conf, llm_lat = self.groq.quick_decision(market_data, asset)
                trade.llm_prediction = llm_dir
                trade.llm_confidence = llm_conf
                trade.llm_latency_ms = llm_lat
            except Exception as e:
                logger.error(f"LLM error: {e}")
        
        # 2. XGBoost
        if self.use_xgb and self.xgb:
            features = FeatureEngineer.create_features(market_data, asset)
            xgb_dir, xgb_conf = self.xgb.predict(features)
            trade.xgb_prediction = xgb_dir
            trade.xgb_confidence = xgb_conf
        
        # 3. Rules
        rules_dir, rules_conf = self._rules_predict(market_data)
        trade.rules_prediction = rules_dir
        trade.rules_confidence = rules_conf
        
        # 4. Hybrid
        hybrid_pred = self.hybrid.predict(market_data, asset)
        trade.hybrid_prediction = hybrid_pred.direction
        trade.hybrid_confidence = hybrid_pred.confidence
        
        # Use hybrid for final decision
        trade.final_direction = hybrid_pred.direction
        trade.final_confidence = hybrid_pred.confidence
        
        # Simulate outcome
        actual = self.simulate_market_outcome(market_data, market_bias)
        trade.actual_direction = actual
        
        # Calculate correctness
        if trade.llm_prediction:
            trade.llm_correct = trade.llm_prediction == actual
        if trade.xgb_prediction:
            trade.xgb_correct = trade.xgb_prediction == actual
        trade.rules_correct = trade.rules_prediction == actual
        trade.hybrid_correct = trade.hybrid_prediction == actual
        
        # Calculate P&L (simplified)
        won = trade.final_direction == actual
        tokens = size_usdc / trade.entry_price
        trade.pnl = (1.0 - trade.entry_price) * tokens if won else -size_usdc
        
        # Update stats
        self._update_stats(trade)
        
        # Learn from outcome
        self._learn(trade, hybrid_pred)
        
        # Store trade
        self.trades.append(trade)
        
        return trade
    
    def _rules_predict(self, market_data: Dict) -> tuple[str, float]:
        """Simple rules-based prediction"""
        trend = market_data.get("trend", 0)
        momentum = market_data.get("momentum", 0)
        
        signal = trend * 0.6 + momentum * 0.4
        
        # Mean reversion for extremes
        if abs(trend) > 1.5:
            signal = -signal * 0.3
        
        if signal > 0:
            return "UP", min(0.5 + abs(signal) * 0.1, 0.70)
        else:
            return "DOWN", min(0.5 + abs(signal) * 0.1, 0.70)
    
    def _update_stats(self, trade: EvaluationTrade):
        """Update method statistics"""
        if trade.llm_correct is not None:
            self.stats["llm"].total += 1
            if trade.llm_correct:
                self.stats["llm"].correct += 1
            self.stats["llm"].total_latency_ms += trade.llm_latency_ms
        
        if trade.xgb_correct is not None:
            self.stats["xgb"].total += 1
            if trade.xgb_correct:
                self.stats["xgb"].correct += 1
        
        self.stats["rules"].total += 1
        if trade.rules_correct:
            self.stats["rules"].correct += 1
        
        self.stats["hybrid"].total += 1
        if trade.hybrid_correct:
            self.stats["hybrid"].correct += 1
        self.stats["hybrid"].total_pnl += trade.pnl
    
    def _learn(self, trade: EvaluationTrade, prediction: HybridPrediction):
        """Learn from trade outcome"""
        # Update XGBoost
        if self.xgb and trade.actual_direction:
            features = FeatureEngineer.create_features(trade.market_data, trade.asset)
            self.xgb.add_sample(features, trade.actual_direction)
        
        # Update hybrid
        if trade.actual_direction:
            self.hybrid.record_outcome(
                prediction,
                trade.actual_direction,
                trade.pnl,
                trade.size_usdc
            )
        
        # Update reward
        outcome = TradeOutcome(
            prediction=trade.final_direction,
            actual=trade.actual_direction or "UP",
            confidence=trade.final_confidence,
            pnl=trade.pnl,
            entry_price=trade.entry_price,
            size=trade.size_usdc
        )
        self.reward_calc.calculate(outcome)
    
    def run_evaluation(
        self,
        num_trades: int = 50,
        market_bias: float = 0.50
    ) -> Dict[str, Any]:
        """
        Run full evaluation.
        
        Args:
            num_trades: Number of trades to evaluate
            market_bias: Probability of UP outcome
        """
        print("\n" + "="*70)
        print("🔬 ADVANCED PREDICTION EVALUATION")
        print("="*70)
        print(f"Trades: {num_trades} | Market Bias: {market_bias:.0%} UP")
        print(f"Methods: LLM={self.use_llm}, XGBoost={self.use_xgb}, Rules=True, Hybrid=True")
        print(f"Starting Balance: ${self.paper_trader.balance:.2f}")
        print("="*70 + "\n")
        
        for i in range(num_trades):
            asset = random.choice(["BTC", "ETH"])
            
            print(f"Trade {i+1}/{num_trades}: {asset}", end=" ")
            
            trade = self.evaluate_single(
                asset=asset,
                size_usdc=2.0,
                market_bias=market_bias
            )
            
            # Print result
            emoji = "✅" if trade.hybrid_correct else "❌"
            lat = f" | LLM: {trade.llm_latency_ms:.0f}ms" if trade.llm_latency_ms > 0 else ""
            print(f"{emoji} Hybrid: {trade.hybrid_prediction} (Actual: {trade.actual_direction}){lat}")
            
            # Rate limiting for LLM
            if self.use_llm:
                time.sleep(1.0)
            else:
                time.sleep(0.1)
        
        # Print results
        self._print_results()
        
        # Save data
        self._save_data()
        
        return self.get_summary()
    
    def _print_results(self):
        """Print evaluation results"""
        print("\n" + "="*70)
        print("📊 EVALUATION RESULTS")
        print("="*70)
        
        print("\n🎯 Accuracy by Method:")
        print("-"*50)
        
        results = []
        for name, stat in self.stats.items():
            if stat.total > 0:
                results.append((name, stat.accuracy, stat.total))
        
        results.sort(key=lambda x: x[1], reverse=True)
        
        for name, acc, total in results:
            bar = "█" * int(acc * 20) + "░" * (20 - int(acc * 20))
            extra = ""
            if name == "llm" and self.stats["llm"].total > 0:
                extra = f" | Latency: {self.stats['llm'].avg_latency:.0f}ms"
            print(f"  {name.upper():8} | {bar} | {acc:.1%} ({self.stats[name].correct}/{total}){extra}")
        
        print("\n💰 P&L (Hybrid Strategy):")
        print(f"  Total P&L: ${self.stats['hybrid'].total_pnl:+.2f}")
        
        print("\n🔧 Hybrid Weights (Adaptive):")
        for method, weight in self.hybrid.weights.items():
            print(f"  {method:8}: {weight:.0%}")
        
        if self.xgb and self.xgb.is_trained:
            print("\n📈 XGBoost Feature Importance:")
            importance = self.xgb.get_feature_importance()
            for i, (feat, imp) in enumerate(list(importance.items())[:5]):
                print(f"  {i+1}. {feat}: {imp:.3f}")
        
        print("\n🏆 Reward System Stats:")
        reward_stats = self.reward_calc.get_stats()
        print(f"  Total Reward: {reward_stats['total_reward']:.2f}")
        print(f"  Avg Reward: {reward_stats['avg_reward']:.3f}")
        print(f"  Current Streak: {reward_stats['current_streak']}")
    
    def _save_data(self):
        """Save evaluation data"""
        # Save trades
        trades_file = self.DATA_DIR / f"trades_{self.session_id}.json"
        with open(trades_file, 'w') as f:
            json.dump([t.to_dict() for t in self.trades], f, indent=2)
        
        # Save summary
        summary_file = self.DATA_DIR / f"summary_{self.session_id}.json"
        with open(summary_file, 'w') as f:
            json.dump(self.get_summary(), f, indent=2)
        
        logger.info(f"Data saved to {self.DATA_DIR}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get evaluation summary"""
        return {
            "session_id": self.session_id,
            "duration_seconds": time.time() - self.session_start,
            "total_trades": len(self.trades),
            "methods": {
                name: {
                    "total": stat.total,
                    "correct": stat.correct,
                    "accuracy": stat.accuracy,
                    "avg_latency_ms": stat.avg_latency
                }
                for name, stat in self.stats.items()
            },
            "hybrid_pnl": self.stats["hybrid"].total_pnl,
            "hybrid_weights": self.hybrid.weights,
            "xgb_trained": self.xgb.is_trained if self.xgb else False
        }


def main():
    """Run evaluation"""
    print("\n🚀 Starting Advanced Evaluation...\n")
    
    # Test GROQ first
    print("Testing GROQ connection...")
    try:
        groq = GroqClient(model=GroqModel.LLAMA_33_70B)
        health = groq.health_check()
        print(f"GROQ Health: {'✅ OK' if health else '❌ FAILED'}")
        use_llm = health
    except Exception as e:
        print(f"GROQ Error: {e}")
        use_llm = False
    
    # Run evaluation
    evaluator = AdvancedEvaluator(
        initial_balance=100.0,
        use_llm=use_llm,
        use_xgboost=True
    )
    
    results = evaluator.run_evaluation(
        num_trades=30,  # Start small
        market_bias=0.52  # Slight bullish bias
    )
    
    print("\n✅ Evaluation complete!")
    print(f"Best Method: {max(results['methods'].items(), key=lambda x: x[1]['accuracy'])[0].upper()}")


if __name__ == "__main__":
    main()
