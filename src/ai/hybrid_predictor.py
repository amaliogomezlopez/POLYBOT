"""
Hybrid Prediction System
Combines LLM (GROQ) + XGBoost for optimal predictions.
Uses ensemble voting and confidence weighting.
"""

import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .groq_client import GroqClient, GroqModel, get_groq_client
from .xgboost_model import XGBoostPredictor, FeatureEngineer, FeatureVector, get_xgb_predictor
from .reward_system import RewardCalculator, TradeOutcome, get_reward_calculator

logger = logging.getLogger(__name__)


class PredictionSource(Enum):
    """Source of prediction"""
    LLM = "llm"
    XGBOOST = "xgboost"
    HYBRID = "hybrid"
    RULES = "rules"


@dataclass
class HybridPrediction:
    """Result from hybrid prediction system"""
    direction: str              # UP or DOWN
    confidence: float           # 0.0 to 1.0
    source: PredictionSource    # Which method was used
    
    # Individual predictions
    llm_prediction: Optional[str] = None
    llm_confidence: float = 0.0
    llm_latency_ms: float = 0.0
    
    xgb_prediction: Optional[str] = None
    xgb_confidence: float = 0.0
    
    rules_prediction: Optional[str] = None
    rules_confidence: float = 0.0
    
    # Ensemble info
    agreement: bool = False     # Do all methods agree?
    total_latency_ms: float = 0.0
    
    # Features used
    features: Optional[FeatureVector] = None


class HybridPredictor:
    """
    Hybrid prediction system combining multiple approaches.
    
    Methods:
    1. LLM (GROQ) - Deep reasoning, context understanding
    2. XGBoost - Pattern recognition, fast inference
    3. Rules-based - Simple momentum/mean-reversion
    
    Ensemble Strategy:
    - If all agree: High confidence
    - If 2/3 agree: Medium confidence, go with majority
    - If all disagree: Low confidence, use weighted average
    """
    
    def __init__(
        self,
        use_llm: bool = True,
        use_xgboost: bool = True,
        use_rules: bool = True,
        llm_weight: float = 0.40,
        xgb_weight: float = 0.35,
        rules_weight: float = 0.25
    ):
        self.use_llm = use_llm
        self.use_xgboost = use_xgboost
        self.use_rules = use_rules
        
        # Weights for ensemble
        self.weights = {
            "llm": llm_weight,
            "xgb": xgb_weight,
            "rules": rules_weight
        }
        
        # Initialize components
        self.groq: Optional[GroqClient] = None
        self.xgb: Optional[XGBoostPredictor] = None
        self.reward_calc = get_reward_calculator(adaptive=True)
        
        # Performance tracking
        self.predictions_by_source: Dict[str, List[bool]] = {
            "llm": [], "xgb": [], "rules": [], "hybrid": []
        }
        
        # Lazy initialization
        self._initialized = False
        
        logger.info(f"HybridPredictor created. LLM: {use_llm}, XGB: {use_xgboost}, Rules: {use_rules}")
    
    def _ensure_initialized(self):
        """Lazy initialization of components"""
        if self._initialized:
            return
        
        if self.use_llm:
            try:
                self.groq = get_groq_client(GroqModel.LLAMA_33_70B)
            except Exception as e:
                logger.warning(f"Failed to initialize GROQ: {e}")
                self.use_llm = False
        
        if self.use_xgboost:
            try:
                self.xgb = get_xgb_predictor()
            except Exception as e:
                logger.warning(f"Failed to initialize XGBoost: {e}")
                self.use_xgboost = False
        
        self._initialized = True
    
    def predict(
        self,
        market_data: Dict[str, Any],
        asset: str = "BTC"
    ) -> HybridPrediction:
        """
        Generate hybrid prediction.
        
        Args:
            market_data: Market state dict
            asset: BTC or ETH
            
        Returns:
            HybridPrediction with direction and confidence
        """
        self._ensure_initialized()
        start_time = time.time()
        
        # Create features
        features = FeatureEngineer.create_features(market_data, asset)
        
        # Collect predictions
        predictions = []  # List of (direction, confidence, source)
        
        # 1. LLM Prediction
        llm_pred = None
        llm_conf = 0.0
        llm_lat = 0.0
        if self.use_llm and self.groq:
            try:
                llm_pred, llm_conf, llm_lat = self.groq.quick_decision(market_data, asset)
                predictions.append((llm_pred, llm_conf, "llm"))
            except Exception as e:
                logger.error(f"LLM prediction failed: {e}")
        
        # 2. XGBoost Prediction
        xgb_pred = None
        xgb_conf = 0.0
        if self.use_xgboost and self.xgb:
            try:
                xgb_pred, xgb_conf = self.xgb.predict(features)
                predictions.append((xgb_pred, xgb_conf, "xgb"))
            except Exception as e:
                logger.error(f"XGBoost prediction failed: {e}")
        
        # 3. Rules-based Prediction
        rules_pred = None
        rules_conf = 0.0
        if self.use_rules:
            rules_pred, rules_conf = self._rules_predict(market_data)
            predictions.append((rules_pred, rules_conf, "rules"))
        
        # Ensemble logic
        if not predictions:
            # Fallback
            return HybridPrediction(
                direction="UP",
                confidence=0.50,
                source=PredictionSource.RULES,
                total_latency_ms=(time.time() - start_time) * 1000,
                features=features
            )
        
        # Calculate ensemble
        direction, confidence, agreement = self._ensemble(predictions)
        
        total_latency = (time.time() - start_time) * 1000
        
        return HybridPrediction(
            direction=direction,
            confidence=confidence,
            source=PredictionSource.HYBRID if len(predictions) > 1 else PredictionSource(predictions[0][2]),
            llm_prediction=llm_pred,
            llm_confidence=llm_conf,
            llm_latency_ms=llm_lat,
            xgb_prediction=xgb_pred,
            xgb_confidence=xgb_conf,
            rules_prediction=rules_pred,
            rules_confidence=rules_conf,
            agreement=agreement,
            total_latency_ms=total_latency,
            features=features
        )
    
    def _rules_predict(self, market_data: Dict[str, Any]) -> Tuple[str, float]:
        """Simple rules-based prediction"""
        trend = market_data.get("trend", 0)
        momentum = market_data.get("momentum", 0)
        volatility = market_data.get("volatility", 1.0)
        
        # Momentum strategy
        signal = trend * 0.5 + momentum * 0.3
        
        # Mean reversion for extreme values
        if abs(trend) > 1.5:
            signal = -signal * 0.3  # Slight mean reversion
        
        # Reduce confidence in high volatility
        vol_factor = 1.0 / (1 + volatility * 0.2)
        
        if signal > 0:
            direction = "UP"
            confidence = min(0.5 + abs(signal) * 0.15 * vol_factor, 0.75)
        else:
            direction = "DOWN"
            confidence = min(0.5 + abs(signal) * 0.15 * vol_factor, 0.75)
        
        return direction, confidence
    
    def _ensemble(
        self,
        predictions: List[Tuple[str, float, str]]
    ) -> Tuple[str, float, bool]:
        """
        Ensemble predictions using weighted voting.
        
        Returns:
            (direction, confidence, all_agree)
        """
        # Count votes
        up_score = 0.0
        down_score = 0.0
        
        for direction, confidence, source in predictions:
            weight = self.weights.get(source, 0.33)
            
            if direction == "UP":
                up_score += weight * confidence
            else:
                down_score += weight * confidence
        
        # Check agreement
        directions = [p[0] for p in predictions]
        all_agree = len(set(directions)) == 1
        
        # Final decision
        if up_score > down_score:
            direction = "UP"
            total_score = up_score + down_score
            confidence = up_score / total_score if total_score > 0 else 0.5
        else:
            direction = "DOWN"
            total_score = up_score + down_score
            confidence = down_score / total_score if total_score > 0 else 0.5
        
        # Boost confidence if all agree
        if all_agree:
            confidence = min(confidence * 1.1, 0.90)
        
        # Reduce confidence if strong disagreement
        if len(predictions) >= 2:
            confs = [p[1] for p in predictions]
            if max(confs) - min(confs) > 0.3:
                confidence *= 0.85
        
        return direction, confidence, all_agree
    
    def record_outcome(
        self,
        prediction: HybridPrediction,
        actual_direction: str,
        pnl: float,
        size: float
    ) -> Dict[str, Any]:
        """
        Record trade outcome for learning.
        
        Args:
            prediction: The prediction that was made
            actual_direction: What actually happened
            pnl: Profit/loss
            size: Trade size
            
        Returns:
            Reward signal and updated stats
        """
        # Create outcome
        outcome = TradeOutcome(
            prediction=prediction.direction,
            actual=actual_direction,
            confidence=prediction.confidence,
            pnl=pnl,
            entry_price=0.5,  # Placeholder
            size=size
        )
        
        # Calculate reward
        reward = self.reward_calc.calculate(outcome)
        
        # Update XGBoost with new sample
        if self.xgb and prediction.features:
            self.xgb.add_sample(prediction.features, actual_direction)
        
        # Track performance by source
        correct = prediction.direction == actual_direction
        self.predictions_by_source["hybrid"].append(correct)
        
        if prediction.llm_prediction:
            self.predictions_by_source["llm"].append(
                prediction.llm_prediction == actual_direction
            )
        if prediction.xgb_prediction:
            self.predictions_by_source["xgb"].append(
                prediction.xgb_prediction == actual_direction
            )
        if prediction.rules_prediction:
            self.predictions_by_source["rules"].append(
                prediction.rules_prediction == actual_direction
            )
        
        # Adapt weights based on performance
        self._adapt_weights()
        
        return {
            "reward": reward.reward,
            "components": reward.components,
            "correct": correct,
            "weights": self.weights.copy()
        }
    
    def _adapt_weights(self):
        """Adapt ensemble weights based on performance"""
        min_samples = 10
        
        accuracies = {}
        for source, results in self.predictions_by_source.items():
            if source == "hybrid":
                continue
            if len(results) >= min_samples:
                recent = results[-20:]  # Last 20 predictions
                accuracies[source] = sum(recent) / len(recent)
        
        if not accuracies:
            return
        
        # Update weights
        total_acc = sum(accuracies.values())
        if total_acc > 0:
            for source, acc in accuracies.items():
                target = acc / total_acc
                current = self.weights.get(source, 0.33)
                # Smooth update
                self.weights[source] = 0.9 * current + 0.1 * target
        
        # Normalize
        total = sum(self.weights.values())
        for k in self.weights:
            self.weights[k] /= total
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        stats = {
            "weights": self.weights.copy(),
            "reward_stats": self.reward_calc.get_stats(),
            "performance_by_source": {}
        }
        
        for source, results in self.predictions_by_source.items():
            if results:
                stats["performance_by_source"][source] = {
                    "total": len(results),
                    "wins": sum(results),
                    "accuracy": sum(results) / len(results)
                }
        
        if self.groq:
            stats["llm_stats"] = self.groq.get_stats()
        
        if self.xgb:
            stats["xgb_stats"] = self.xgb.get_stats()
        
        return stats


# Global instance
_hybrid_predictor: Optional[HybridPredictor] = None


def get_hybrid_predictor(**kwargs) -> HybridPredictor:
    """Get or create global hybrid predictor"""
    global _hybrid_predictor
    if _hybrid_predictor is None:
        _hybrid_predictor = HybridPredictor(**kwargs)
    return _hybrid_predictor
