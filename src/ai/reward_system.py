"""
Reward System for Reinforcement Learning
Calculates rewards based on trade outcomes to guide learning.
"""

import math
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class RewardType(Enum):
    """Types of rewards"""
    PROFIT = "profit"           # Based on P&L
    ACCURACY = "accuracy"       # Based on prediction correctness
    SHARPE = "sharpe"           # Risk-adjusted return
    COMPOSITE = "composite"     # Combination of all


@dataclass
class TradeOutcome:
    """Outcome of a single trade"""
    prediction: str             # UP or DOWN
    actual: str                 # What happened
    confidence: float           # Prediction confidence
    pnl: float                  # Profit/Loss
    entry_price: float          # Token price at entry
    size: float                 # Trade size in USDC
    
    @property
    def correct(self) -> bool:
        return self.prediction == self.actual
    
    @property
    def roi(self) -> float:
        return self.pnl / self.size if self.size > 0 else 0


@dataclass
class RewardSignal:
    """Reward signal for learning"""
    reward: float               # Main reward value
    components: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class RewardCalculator:
    """
    Calculates rewards for trading decisions.
    
    Features:
    - Multiple reward components
    - Risk-adjusted rewards (Sharpe-like)
    - Confidence calibration penalty
    - Streak bonuses/penalties
    """
    
    def __init__(
        self,
        reward_type: RewardType = RewardType.COMPOSITE,
        window_size: int = 20
    ):
        self.reward_type = reward_type
        self.window_size = window_size
        
        # History for rolling calculations
        self.pnl_history: deque = deque(maxlen=window_size)
        self.accuracy_history: deque = deque(maxlen=window_size)
        self.confidence_history: deque = deque(maxlen=window_size)
        
        # Streak tracking
        self.current_streak = 0  # Positive = wins, negative = losses
        self.max_streak = 0
        self.min_streak = 0
        
        # Cumulative stats
        self.total_trades = 0
        self.total_reward = 0.0
        
        logger.info(f"RewardCalculator initialized: {reward_type.value}")
    
    def calculate(self, outcome: TradeOutcome) -> RewardSignal:
        """
        Calculate reward for a trade outcome.
        
        Args:
            outcome: Trade outcome details
            
        Returns:
            RewardSignal with reward and components
        """
        components = {}
        
        # 1. Profit reward (normalized P&L)
        # Scale: $5 profit = +1.0, $5 loss = -1.0
        profit_reward = outcome.pnl / 5.0
        profit_reward = max(-2.0, min(2.0, profit_reward))  # Clip
        components["profit"] = profit_reward
        
        # 2. Accuracy reward
        # +0.5 for correct, -0.5 for incorrect
        accuracy_reward = 0.5 if outcome.correct else -0.5
        components["accuracy"] = accuracy_reward
        
        # 3. Confidence calibration reward
        # Penalize overconfidence on wrong predictions
        # Reward appropriate confidence
        if outcome.correct:
            # Higher confidence on correct = good
            calibration_reward = (outcome.confidence - 0.5) * 0.5
        else:
            # Higher confidence on wrong = bad
            calibration_reward = -(outcome.confidence - 0.5) * 1.0
        components["calibration"] = calibration_reward
        
        # 4. Risk-adjusted component
        # Favor consistent small wins over volatile results
        self.pnl_history.append(outcome.pnl)
        if len(self.pnl_history) >= 5:
            mean_pnl = sum(self.pnl_history) / len(self.pnl_history)
            var_pnl = sum((p - mean_pnl) ** 2 for p in self.pnl_history) / len(self.pnl_history)
            std_pnl = math.sqrt(var_pnl) if var_pnl > 0 else 0.01
            sharpe_component = mean_pnl / std_pnl * 0.1  # Scale down
            sharpe_component = max(-0.5, min(0.5, sharpe_component))
        else:
            sharpe_component = 0
        components["sharpe"] = sharpe_component
        
        # 5. Streak bonus/penalty
        if outcome.correct:
            if self.current_streak >= 0:
                self.current_streak += 1
            else:
                self.current_streak = 1
        else:
            if self.current_streak <= 0:
                self.current_streak -= 1
            else:
                self.current_streak = -1
        
        self.max_streak = max(self.max_streak, self.current_streak)
        self.min_streak = min(self.min_streak, self.current_streak)
        
        # Bonus for streaks
        if self.current_streak >= 3:
            streak_bonus = 0.2 * min(self.current_streak - 2, 3)  # Cap at +0.6
        elif self.current_streak <= -3:
            streak_bonus = -0.1 * min(abs(self.current_streak) - 2, 3)  # Cap at -0.3
        else:
            streak_bonus = 0
        components["streak"] = streak_bonus
        
        # Calculate final reward based on type
        if self.reward_type == RewardType.PROFIT:
            final_reward = profit_reward
        elif self.reward_type == RewardType.ACCURACY:
            final_reward = accuracy_reward
        elif self.reward_type == RewardType.SHARPE:
            final_reward = profit_reward * 0.5 + sharpe_component * 0.5
        else:  # COMPOSITE
            final_reward = (
                profit_reward * 0.35 +
                accuracy_reward * 0.25 +
                calibration_reward * 0.20 +
                sharpe_component * 0.10 +
                streak_bonus * 0.10
            )
        
        # Update history
        self.accuracy_history.append(1 if outcome.correct else 0)
        self.confidence_history.append(outcome.confidence)
        self.total_trades += 1
        self.total_reward += final_reward
        
        return RewardSignal(
            reward=final_reward,
            components=components,
            metadata={
                "trade_number": self.total_trades,
                "current_streak": self.current_streak,
                "rolling_accuracy": self._rolling_accuracy(),
                "rolling_pnl": self._rolling_pnl()
            }
        )
    
    def _rolling_accuracy(self) -> float:
        """Calculate rolling accuracy"""
        if not self.accuracy_history:
            return 0.5
        return sum(self.accuracy_history) / len(self.accuracy_history)
    
    def _rolling_pnl(self) -> float:
        """Calculate rolling P&L"""
        if not self.pnl_history:
            return 0
        return sum(self.pnl_history)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get reward system statistics"""
        return {
            "total_trades": self.total_trades,
            "total_reward": self.total_reward,
            "avg_reward": self.total_reward / self.total_trades if self.total_trades > 0 else 0,
            "rolling_accuracy": self._rolling_accuracy(),
            "rolling_pnl": self._rolling_pnl(),
            "current_streak": self.current_streak,
            "max_streak": self.max_streak,
            "min_streak": self.min_streak
        }
    
    def reset(self) -> None:
        """Reset all statistics"""
        self.pnl_history.clear()
        self.accuracy_history.clear()
        self.confidence_history.clear()
        self.current_streak = 0
        self.max_streak = 0
        self.min_streak = 0
        self.total_trades = 0
        self.total_reward = 0.0


class AdaptiveRewardCalculator(RewardCalculator):
    """
    Adaptive reward calculator that adjusts weights based on performance.
    Similar to gradient descent - finds optimal reward weights.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Adaptive weights
        self.weights = {
            "profit": 0.35,
            "accuracy": 0.25,
            "calibration": 0.20,
            "sharpe": 0.10,
            "streak": 0.10
        }
        
        # Performance tracking per component
        self.component_performance: Dict[str, List[float]] = {
            k: [] for k in self.weights
        }
        
        self.adaptation_rate = 0.05
    
    def calculate(self, outcome: TradeOutcome) -> RewardSignal:
        """Calculate with adaptive weights"""
        # Get base signal
        signal = super().calculate(outcome)
        
        # Recalculate with adaptive weights
        final_reward = sum(
            self.weights[k] * signal.components.get(k, 0)
            for k in self.weights
        )
        
        # Track component performance
        for k, v in signal.components.items():
            if k in self.component_performance:
                # Track if component aligned with actual outcome
                aligned = (v > 0 and outcome.correct) or (v < 0 and not outcome.correct)
                self.component_performance[k].append(1 if aligned else 0)
        
        signal.reward = final_reward
        signal.metadata["weights"] = self.weights.copy()
        
        return signal
    
    def adapt_weights(self) -> Dict[str, float]:
        """
        Adapt weights based on component performance.
        Increase weight of components that predict well.
        """
        if self.total_trades < 20:
            return self.weights
        
        # Calculate performance score for each component
        scores = {}
        for k, history in self.component_performance.items():
            if len(history) >= 10:
                # Recent performance (last 20 trades)
                recent = history[-20:]
                scores[k] = sum(recent) / len(recent)
            else:
                scores[k] = 0.5  # Neutral
        
        # Update weights
        total_score = sum(scores.values())
        if total_score > 0:
            for k in self.weights:
                target_weight = scores[k] / total_score
                # Smooth update
                self.weights[k] = (
                    (1 - self.adaptation_rate) * self.weights[k] +
                    self.adaptation_rate * target_weight
                )
        
        # Ensure minimum weights
        min_weight = 0.05
        for k in self.weights:
            self.weights[k] = max(min_weight, self.weights[k])
        
        # Normalize
        total = sum(self.weights.values())
        for k in self.weights:
            self.weights[k] /= total
        
        logger.info(f"Adapted weights: {self.weights}")
        return self.weights


# Global instance
_reward_calculator: Optional[RewardCalculator] = None


def get_reward_calculator(adaptive: bool = True) -> RewardCalculator:
    """Get or create global reward calculator"""
    global _reward_calculator
    if _reward_calculator is None:
        if adaptive:
            _reward_calculator = AdaptiveRewardCalculator()
        else:
            _reward_calculator = RewardCalculator()
    return _reward_calculator
