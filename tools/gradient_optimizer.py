"""
Gradient-Based Strategy Optimizer
Analyzes paper trading results and optimizes strategy parameters.
Similar to gradient descent in ML - minimizes losses by adjusting weights.
"""

import os
import sys
import json
import math
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class StrategyWeights:
    """Weights for each strategy"""
    momentum: float = 0.33
    mean_reversion: float = 0.33
    contrarian: float = 0.34
    
    def normalize(self):
        """Ensure weights sum to 1"""
        total = self.momentum + self.mean_reversion + self.contrarian
        if total > 0:
            self.momentum /= total
            self.mean_reversion /= total
            self.contrarian /= total
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "momentum": self.momentum,
            "mean_reversion": self.mean_reversion,
            "contrarian": self.contrarian
        }


@dataclass
class OptimizationResult:
    """Result of optimization"""
    initial_weights: Dict[str, float]
    optimized_weights: Dict[str, float]
    expected_win_rate: float
    expected_pnl_per_trade: float
    confidence: float
    iterations: int
    improvement: float


class GradientOptimizer:
    """
    Gradient-based strategy optimizer.
    
    Uses historical trade data to optimize strategy weights.
    Similar to gradient descent but for discrete strategy selection.
    """
    
    DATA_DIR = Path("data/paper_trading_v2")
    
    def __init__(self):
        self.sessions = self._load_sessions()
        self.all_trades = self._load_all_trades()
        
        # Current weights
        self.weights = StrategyWeights()
        
        # Learning parameters
        self.learning_rate = 0.1
        self.momentum_decay = 0.9
        self.min_weight = 0.05  # Minimum 5% allocation
        
        # Gradients (accumulated)
        self.gradients = {"momentum": 0, "mean_reversion": 0, "contrarian": 0}
        self.velocity = {"momentum": 0, "mean_reversion": 0, "contrarian": 0}
    
    def analyze(self) -> Dict[str, Any]:
        """Analyze all historical data"""
        if not self.all_trades:
            return {"error": "No trade data found"}
        
        # Group by strategy
        by_strategy = defaultdict(list)
        for trade in self.all_trades:
            strat = trade.get("prediction_source", "unknown")
            by_strategy[strat].append(trade)
        
        # Calculate metrics per strategy
        strategy_stats = {}
        for strat, trades in by_strategy.items():
            resolved = [t for t in trades if t.get("outcome")]
            wins = [t for t in resolved if t["outcome"] == "win"]
            losses = [t for t in resolved if t["outcome"] == "loss"]
            
            total_pnl = sum(t.get("pnl", 0) for t in resolved)
            avg_pnl = total_pnl / len(resolved) if resolved else 0
            win_rate = len(wins) / len(resolved) if resolved else 0
            
            # Calculate Sharpe-like ratio
            if resolved:
                pnls = [t.get("pnl", 0) for t in resolved]
                mean_pnl = sum(pnls) / len(pnls)
                variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
                std_pnl = math.sqrt(variance) if variance > 0 else 1
                sharpe = mean_pnl / std_pnl if std_pnl > 0 else 0
            else:
                sharpe = 0
            
            strategy_stats[strat] = {
                "total_trades": len(resolved),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "sharpe_ratio": sharpe
            }
        
        return {
            "total_trades": len(self.all_trades),
            "resolved_trades": sum(s["total_trades"] for s in strategy_stats.values()),
            "strategy_performance": strategy_stats,
            "sessions_analyzed": len(self.sessions)
        }
    
    def calculate_gradients(self) -> Dict[str, float]:
        """
        Calculate gradients for each strategy.
        Gradient = direction to move weight to improve performance.
        
        Positive gradient = increase weight
        Negative gradient = decrease weight
        """
        analysis = self.analyze()
        stats = analysis.get("strategy_performance", {})
        
        gradients = {}
        
        # Base gradient on performance metrics
        for strat in ["momentum", "mean_reversion", "contrarian"]:
            if strat not in stats or stats[strat]["total_trades"] < 3:
                gradients[strat] = 0
                continue
            
            s = stats[strat]
            
            # Components of gradient:
            # 1. Win rate contribution (higher = positive)
            win_rate_grad = (s["win_rate"] - 0.5) * 2  # -1 to +1
            
            # 2. Average P&L contribution (scaled)
            pnl_grad = s["avg_pnl"] / 5  # Normalize, $5 avg = 1.0
            
            # 3. Sharpe ratio contribution
            sharpe_grad = s["sharpe_ratio"] * 0.5
            
            # Combined gradient
            gradients[strat] = win_rate_grad * 0.4 + pnl_grad * 0.4 + sharpe_grad * 0.2
        
        return gradients
    
    def step(self) -> Tuple[StrategyWeights, float]:
        """
        Perform one optimization step.
        Updates weights based on gradients.
        
        Returns: (new_weights, total_gradient_magnitude)
        """
        gradients = self.calculate_gradients()
        
        # Apply momentum (like Adam optimizer)
        for strat in gradients:
            self.velocity[strat] = (
                self.momentum_decay * self.velocity[strat] +
                (1 - self.momentum_decay) * gradients[strat]
            )
        
        # Update weights
        old_weights = StrategyWeights(
            momentum=self.weights.momentum,
            mean_reversion=self.weights.mean_reversion,
            contrarian=self.weights.contrarian
        )
        
        self.weights.momentum += self.learning_rate * self.velocity["momentum"]
        self.weights.mean_reversion += self.learning_rate * self.velocity["mean_reversion"]
        self.weights.contrarian += self.learning_rate * self.velocity["contrarian"]
        
        # Clip to minimum
        self.weights.momentum = max(self.min_weight, self.weights.momentum)
        self.weights.mean_reversion = max(self.min_weight, self.weights.mean_reversion)
        self.weights.contrarian = max(self.min_weight, self.weights.contrarian)
        
        # Normalize
        self.weights.normalize()
        
        # Calculate gradient magnitude
        grad_mag = math.sqrt(sum(g ** 2 for g in gradients.values()))
        
        return self.weights, grad_mag
    
    def optimize(self, max_iterations: int = 10, tolerance: float = 0.01) -> OptimizationResult:
        """
        Run optimization until convergence.
        
        Args:
            max_iterations: Maximum optimization steps
            tolerance: Stop when gradient magnitude < tolerance
        """
        initial_weights = self.weights.to_dict()
        
        for i in range(max_iterations):
            weights, grad_mag = self.step()
            
            if grad_mag < tolerance:
                print(f"Converged at iteration {i+1}")
                break
        
        # Calculate expected performance with new weights
        analysis = self.analyze()
        stats = analysis.get("strategy_performance", {})
        
        expected_wr = 0
        expected_pnl = 0
        
        for strat, weight in weights.to_dict().items():
            if strat in stats:
                expected_wr += weight * stats[strat]["win_rate"]
                expected_pnl += weight * stats[strat]["avg_pnl"]
        
        # Calculate improvement
        old_expected = sum(
            initial_weights.get(s, 0.33) * stats.get(s, {}).get("avg_pnl", 0)
            for s in ["momentum", "mean_reversion", "contrarian"]
        )
        improvement = (expected_pnl - old_expected) / abs(old_expected) if old_expected != 0 else 0
        
        return OptimizationResult(
            initial_weights=initial_weights,
            optimized_weights=weights.to_dict(),
            expected_win_rate=expected_wr,
            expected_pnl_per_trade=expected_pnl,
            confidence=min(analysis.get("resolved_trades", 0) / 50, 1.0),  # More trades = more confident
            iterations=i + 1,
            improvement=improvement
        )
    
    def get_recommended_allocation(self) -> Dict[str, Any]:
        """Get recommended strategy allocation based on current data"""
        result = self.optimize()
        
        return {
            "recommended_weights": result.optimized_weights,
            "expected_win_rate": f"{result.expected_win_rate:.1%}",
            "expected_pnl_per_trade": f"${result.expected_pnl_per_trade:.2f}",
            "confidence": f"{result.confidence:.0%}",
            "improvement_vs_equal": f"{result.improvement:.1%}"
        }
    
    def _load_sessions(self) -> List[Dict]:
        """Load all session data"""
        sessions_file = self.DATA_DIR / "all_sessions.json"
        if sessions_file.exists():
            with open(sessions_file, 'r') as f:
                return json.load(f)
        return []
    
    def _load_all_trades(self) -> List[Dict]:
        """Load all trade data from all sessions"""
        all_trades = []
        
        for file in self.DATA_DIR.glob("trades_sess_*.json"):
            try:
                with open(file, 'r') as f:
                    trades = json.load(f)
                    all_trades.extend(trades)
            except Exception as e:
                print(f"Error loading {file}: {e}")
        
        return all_trades


def main():
    """Run optimization analysis"""
    print("\n" + "="*60)
    print("📊 GRADIENT-BASED STRATEGY OPTIMIZER")
    print("="*60)
    
    optimizer = GradientOptimizer()
    
    # Analyze current data
    print("\n📈 Current Performance Analysis:")
    analysis = optimizer.analyze()
    
    if "error" in analysis:
        print(f"❌ {analysis['error']}")
        print("Run paper_runner.py first to generate data!")
        return
    
    print(f"   Total Trades: {analysis['total_trades']}")
    print(f"   Resolved: {analysis['resolved_trades']}")
    print(f"   Sessions: {analysis['sessions_analyzed']}")
    
    print("\n🎯 Strategy Performance:")
    for strat, stats in analysis['strategy_performance'].items():
        if stats['total_trades'] > 0:
            print(f"\n   {strat.upper()}:")
            print(f"      Trades: {stats['total_trades']}")
            print(f"      Win Rate: {stats['win_rate']:.1%}")
            print(f"      Avg P&L: ${stats['avg_pnl']:.2f}")
            print(f"      Sharpe: {stats['sharpe_ratio']:.2f}")
    
    # Calculate gradients
    print("\n📐 Gradients (direction to optimize):")
    gradients = optimizer.calculate_gradients()
    for strat, grad in gradients.items():
        arrow = "↑" if grad > 0 else "↓" if grad < 0 else "→"
        print(f"   {strat}: {grad:+.3f} {arrow}")
    
    # Optimize
    print("\n🔧 Optimizing weights...")
    result = optimizer.optimize()
    
    print(f"\n✅ Optimization Complete!")
    print(f"   Iterations: {result.iterations}")
    print(f"   Confidence: {result.confidence:.0%}")
    
    print("\n📊 Weight Changes:")
    for strat in ["momentum", "mean_reversion", "contrarian"]:
        old = result.initial_weights[strat]
        new = result.optimized_weights[strat]
        change = new - old
        arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
        print(f"   {strat:15}: {old:.0%} → {new:.0%} ({change:+.0%}) {arrow}")
    
    print(f"\n💰 Expected Performance:")
    print(f"   Win Rate: {result.expected_win_rate:.1%}")
    print(f"   Avg P&L/Trade: ${result.expected_pnl_per_trade:.2f}")
    print(f"   Improvement: {result.improvement:+.1%}")
    
    # Save optimized weights
    weights_file = optimizer.DATA_DIR / "optimized_weights.json"
    with open(weights_file, 'w') as f:
        json.dump({
            "weights": result.optimized_weights,
            "expected_win_rate": result.expected_win_rate,
            "expected_pnl": result.expected_pnl_per_trade,
            "confidence": result.confidence,
            "based_on_trades": analysis['resolved_trades']
        }, f, indent=2)
    
    print(f"\n📁 Saved to: {weights_file}")


if __name__ == "__main__":
    main()
