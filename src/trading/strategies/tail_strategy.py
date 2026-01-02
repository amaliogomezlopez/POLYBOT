"""
🎰 STRATEGY C: TAIL BETTING
============================
Low-cost, high-multiplier bets on unlikely outcomes.

Based on @Spon's approach - systematic $2 bets on YES < $0.04.

Logic:
1. Filter: YES price between $0.001 and $0.04
2. Score: ML-based scoring using category features
3. Action: Place $2 bet if ML score > threshold

Features:
- XGBoost-compatible feature extraction
- Category-based scoring
- EV calculation
- Training data collection
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List
import re

from .base_strategy import BaseStrategy, MarketData, TradeSignal, SignalType

logger = logging.getLogger(__name__)


class TailStrategy(BaseStrategy):
    """
    Tail betting strategy - low cost, high multiplier.
    
    Parameters:
        max_price: Maximum entry price (default: $0.04)
        min_price: Minimum entry price (default: $0.001)
        min_multiplier: Minimum potential multiplier (default: 25x)
        min_ml_score: Minimum ML score to trigger (default: 0.55)
        stake_size: USD per bet (default: $2)
    """
    
    STRATEGY_ID = "TAIL_BETTING_V1"
    
    # Category weights learned from historical data
    CATEGORY_WEIGHTS = {
        # Positive categories (historically better hit rates)
        'crypto': 0.12,
        'bitcoin': 0.10,
        'ethereum': 0.08,
        'nvidia': 0.08,
        'tesla': 0.10,
        'apple': 0.05,
        'ai': 0.08,
        'openai': 0.06,
        'gpt': 0.05,
        'microsoft': 0.04,
        'google': 0.04,
        'amazon': 0.04,
        
        # Neutral to slightly negative
        'trump': 0.02,
        'biden': 0.01,
        'election': 0.00,
        
        # Negative categories (historically worse)
        'sports': -0.05,
        'nba': -0.06,
        'nfl': -0.06,
        'weather': -0.03,
        'celebrity': -0.02,
        'entertainment': -0.02,
    }
    
    def __init__(
        self,
        paper_mode: bool = True,
        stake_size: float = 2.0,
        max_price: float = 0.04,
        min_price: float = 0.001,
        min_multiplier: float = 25,
        min_ml_score: float = 0.55,
        **kwargs
    ):
        super().__init__(
            strategy_id=self.STRATEGY_ID,
            paper_mode=paper_mode,
            stake_size=stake_size,
            max_daily_trades=50,
            **kwargs
        )
        
        self.max_price = max_price
        self.min_price = min_price
        self.min_multiplier = min_multiplier
        self.min_ml_score = min_ml_score
    
    def get_config(self) -> Dict:
        return {
            "strategy_id": self.STRATEGY_ID,
            "type": "TAIL",
            "price_range": f"${self.min_price:.3f} - ${self.max_price:.3f}",
            "min_multiplier": f"{self.min_multiplier}x",
            "min_ml_score": f"{self.min_ml_score:.0%}",
            "stake_size": f"${self.stake_size:.2f}",
            "paper_mode": self.paper_mode,
        }
    
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Evaluate market for tail betting opportunity.
        
        Steps:
        1. Price filter
        2. Extract ML features
        3. Calculate ML score
        4. Generate signal if score > threshold
        """
        # Price filter
        if not (self.min_price < market.yes_price < self.max_price):
            return None
        
        # Calculate multiplier
        multiplier = 1 / market.yes_price
        
        if multiplier < self.min_multiplier:
            return None
        
        # Extract features and calculate score
        features = self.extract_features(market)
        ml_score = self.calculate_score(market.question, features)
        
        # Check threshold
        if ml_score < self.min_ml_score:
            return None
        
        # Calculate expected value
        # EV = (prob_win * payout) - stake
        # We estimate prob_win from ML score (calibrated)
        estimated_prob = self._score_to_probability(ml_score)
        ev = (estimated_prob * self.stake_size * multiplier) - self.stake_size
        
        signal = TradeSignal(
            strategy_id=self.strategy_id,
            signal_type=SignalType.BUY,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            outcome="YES",
            entry_price=market.yes_price,
            stake=self.stake_size,
            confidence=ml_score,
            expected_value=ev,
            trigger_reason=f"tail_ml_score_{ml_score:.2f}",
            signal_data={
                "multiplier": multiplier,
                "ml_score": ml_score,
                "estimated_prob": estimated_prob,
                "ev": ev,
                "category": features.get('detected_category', 'unknown'),
                "ml_features": features,
                "required_hit_rate": 1 / multiplier,
            },
            snapshot_data=market.to_snapshot()
        )
        
        logger.info(
            f"🎰 TAIL: ${market.yes_price:.3f} ({multiplier:.0f}x) | "
            f"ML: {ml_score:.0%} | EV: ${ev:+.2f} | "
            f"{market.question[:40]}..."
        )
        
        return signal
    
    def extract_features(self, market: MarketData) -> Dict:
        """
        Extract ML features from market data.
        
        Features designed for XGBoost training.
        """
        question = market.question.lower()
        
        # Category detection
        detected_category = 'other'
        for category in self.CATEGORY_WEIGHTS.keys():
            if category in question:
                detected_category = category
                break
        
        # Binary category features
        features = {
            'has_crypto': any(kw in question for kw in ['crypto', 'bitcoin', 'ethereum', 'btc', 'eth']),
            'has_stock': any(kw in question for kw in ['nvidia', 'tesla', 'apple', 'stock', 'nvda', 'tsla']),
            'has_ai': any(kw in question for kw in ['ai', 'openai', 'gpt', 'artificial intelligence', 'chatgpt']),
            'has_politics': any(kw in question for kw in ['trump', 'biden', 'election', 'president', 'congress']),
            'has_sports': any(kw in question for kw in ['sports', 'nba', 'nfl', 'football', 'basketball', 'score']),
            'has_number': bool(re.search(r'\d+', question)),
            'has_date': bool(re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december|\d{4})', question)),
            'has_comparison': any(kw in question for kw in ['above', 'below', 'more than', 'less than', 'exceed']),
            
            # Numeric features
            'question_length': len(market.question),
            'word_count': len(market.question.split()),
            'entry_price': market.yes_price,
            'multiplier': 1 / market.yes_price if market.yes_price > 0 else 0,
            'volume_24h': market.volume_24h,
            'spread_bps': market.spread_bps,
            'hours_to_expiry': market.hours_to_expiry or 0,
            
            # Derived
            'detected_category': detected_category,
            'category_weight': self.CATEGORY_WEIGHTS.get(detected_category, 0),
        }
        
        return features
    
    def calculate_score(self, question: str, features: Dict) -> float:
        """
        Calculate ML score for a market.
        
        Uses category weights + feature adjustments.
        Can be replaced with trained XGBoost model.
        """
        # Base score
        score = 0.50
        
        # Category weight
        score += features.get('category_weight', 0)
        
        # Multiplier bonus (higher multiplier = slight bonus)
        multiplier = features.get('multiplier', 50)
        if multiplier >= 500:
            score += 0.05
        elif multiplier >= 200:
            score += 0.03
        elif multiplier >= 100:
            score += 0.01
        
        # Volume bonus (more liquid = better)
        volume = features.get('volume_24h', 0)
        if volume > 100000:
            score += 0.03
        elif volume > 50000:
            score += 0.02
        elif volume > 10000:
            score += 0.01
        
        # Time to expiry adjustment
        hours = features.get('hours_to_expiry', 0)
        if 24 < hours < 168:  # 1-7 days - sweet spot
            score += 0.02
        elif hours > 720:  # > 30 days - too far
            score -= 0.02
        
        # Question complexity (longer = usually more specific = better)
        word_count = features.get('word_count', 0)
        if word_count > 15:
            score += 0.02
        elif word_count < 5:
            score -= 0.02
        
        # Has specific number (target)
        if features.get('has_number'):
            score += 0.02
        
        # Penalize sports
        if features.get('has_sports'):
            score -= 0.05
        
        # Clamp to valid range
        return max(0.0, min(1.0, score))
    
    def _score_to_probability(self, score: float) -> float:
        """
        Convert ML score to estimated probability of winning.
        
        Calibrated based on historical data.
        Score of 0.55 -> ~1% probability (based on tail betting math)
        """
        # This is a rough calibration
        # Score 0.5 = baseline = ~0.5% hit rate
        # Score 0.7 = good = ~2% hit rate
        # Score 0.9 = excellent = ~5% hit rate
        
        if score < 0.5:
            return 0.003  # 0.3%
        elif score < 0.6:
            return 0.005 + (score - 0.5) * 0.05  # 0.5% - 1%
        elif score < 0.7:
            return 0.01 + (score - 0.6) * 0.1  # 1% - 2%
        elif score < 0.8:
            return 0.02 + (score - 0.7) * 0.2  # 2% - 4%
        else:
            return 0.04 + (score - 0.8) * 0.3  # 4% - 7%


class TailScorer:
    """
    Standalone scorer for use in other modules.
    Wraps the strategy's scoring logic.
    """
    
    def __init__(self):
        self._strategy = TailStrategy(paper_mode=True)
    
    def score(self, question: str, price: float = 0.02, volume: float = 0) -> float:
        """Calculate score for a question."""
        from .base_strategy import MarketData
        
        market = MarketData(
            condition_id="",
            question=question,
            yes_price=price,
            volume_24h=volume,
        )
        
        features = self._strategy.extract_features(market)
        return self._strategy.calculate_score(question, features)
    
    def extract_features(self, question: str, price: float = 0.02, volume: float = 0) -> Dict:
        """Extract features for a question."""
        from .base_strategy import MarketData
        
        market = MarketData(
            condition_id="",
            question=question,
            yes_price=price,
            volume_24h=volume,
        )
        
        return self._strategy.extract_features(market)
