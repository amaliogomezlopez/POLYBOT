"""
XGBoost Tail Scorer
ML model to score and rank tail betting opportunities.
"""
import json
import os
import time
import numpy as np
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TailFeatures:
    """Features for tail opportunity scoring"""
    # Price features
    yes_price: float           # Current YES price
    price_pct: float           # Price as % of max threshold
    potential_return: float    # Potential return multiplier
    
    # Market features
    liquidity: float           # Market liquidity
    volume_24h: float          # 24h volume
    
    # Time features
    days_to_expiry: float      # Days until market closes
    hour_of_day: float         # Hour (0-23)
    day_of_week: float         # Day (0-6)
    
    # Category features
    is_political: int          # Political market
    is_crypto: int             # Crypto market
    is_sports: int             # Sports market
    is_finance: int            # Finance/stocks market
    is_tech: int               # Tech market
    
    # Historical features (if available)
    similar_markets_hit_rate: float = 0.01  # Default 1% hit rate
    
    def to_array(self) -> np.ndarray:
        return np.array([
            self.yes_price,
            self.price_pct,
            self.potential_return,
            self.liquidity,
            self.volume_24h,
            self.days_to_expiry,
            self.hour_of_day,
            self.day_of_week,
            self.is_political,
            self.is_crypto,
            self.is_sports,
            self.is_finance,
            self.is_tech,
            self.similar_markets_hit_rate
        ])
        
    @staticmethod
    def feature_names() -> List[str]:
        return [
            "yes_price", "price_pct", "potential_return",
            "liquidity", "volume_24h",
            "days_to_expiry", "hour_of_day", "day_of_week",
            "is_political", "is_crypto", "is_sports", "is_finance", "is_tech",
            "similar_markets_hit_rate"
        ]


class TailFeatureEngineer:
    """Creates features from tail opportunity data"""
    
    POLITICAL_KEYWORDS = ["trump", "biden", "election", "president", "congress", "senate", 
                         "government", "war", "russia", "ukraine", "china", "nato", "minister"]
    CRYPTO_KEYWORDS = ["btc", "bitcoin", "eth", "ethereum", "sol", "solana", "crypto", 
                      "coinbase", "binance", "token", "blockchain"]
    SPORTS_KEYWORDS = ["nba", "nfl", "mlb", "soccer", "football", "basketball", "traded",
                      "championship", "playoffs", "win", "match"]
    FINANCE_KEYWORDS = ["stock", "msft", "aapl", "amzn", "nvda", "fed", "interest rate",
                       "market cap", "etf", "52-week", "gold"]
    TECH_KEYWORDS = ["ai", "openai", "google", "anthropic", "chatgpt", "model", "grok",
                    "apple", "microsoft", "meta", "nvidia"]
    
    @staticmethod
    def detect_category(question: str) -> Dict[str, int]:
        """Detect market category from question"""
        q = question.lower()
        
        return {
            "is_political": 1 if any(kw in q for kw in TailFeatureEngineer.POLITICAL_KEYWORDS) else 0,
            "is_crypto": 1 if any(kw in q for kw in TailFeatureEngineer.CRYPTO_KEYWORDS) else 0,
            "is_sports": 1 if any(kw in q for kw in TailFeatureEngineer.SPORTS_KEYWORDS) else 0,
            "is_finance": 1 if any(kw in q for kw in TailFeatureEngineer.FINANCE_KEYWORDS) else 0,
            "is_tech": 1 if any(kw in q for kw in TailFeatureEngineer.TECH_KEYWORDS) else 0,
        }
    
    @staticmethod
    def calculate_days_to_expiry(end_date: str) -> float:
        """Calculate days until market expires"""
        try:
            if not end_date:
                return 365  # Default to 1 year
            
            # Parse ISO date
            if "T" in end_date:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            else:
                end_dt = datetime.fromisoformat(end_date)
                
            now = datetime.now(end_dt.tzinfo) if end_dt.tzinfo else datetime.now()
            delta = end_dt - now
            
            return max(0, delta.days + delta.seconds / 86400)
            
        except Exception:
            return 365
    
    @staticmethod
    def create_features(
        opportunity: Dict,
        max_price: float = 0.04
    ) -> TailFeatures:
        """Create feature vector from opportunity data"""
        now = datetime.now()
        
        question = opportunity.get("question", "")
        categories = TailFeatureEngineer.detect_category(question)
        
        yes_price = opportunity.get("yes_price", 0.01)
        
        return TailFeatures(
            yes_price=yes_price,
            price_pct=yes_price / max_price,
            potential_return=opportunity.get("potential_return", 1 / yes_price if yes_price > 0 else 100),
            liquidity=opportunity.get("liquidity", 0),
            volume_24h=opportunity.get("volume_24h", 0),
            days_to_expiry=TailFeatureEngineer.calculate_days_to_expiry(opportunity.get("end_date", "")),
            hour_of_day=now.hour,
            day_of_week=now.weekday(),
            is_political=categories["is_political"],
            is_crypto=categories["is_crypto"],
            is_sports=categories["is_sports"],
            is_finance=categories["is_finance"],
            is_tech=categories["is_tech"],
            similar_markets_hit_rate=0.01  # Will be updated with historical data
        )


@dataclass
class TailScoreResult:
    """Result of tail scoring"""
    opportunity_score: float   # 0-1 score (higher = better opportunity)
    win_probability: float     # Estimated probability of winning
    expected_value: float      # Expected value of bet
    recommendation: str        # BET, SKIP, or WATCH
    reasoning: List[str]       # Reasons for recommendation
    features: Optional[TailFeatures] = None


class XGBoostTailScorer:
    """
    XGBoost model for scoring tail betting opportunities.
    
    Learns from historical outcomes to predict:
    1. Win probability
    2. Expected value
    3. Optimal bet sizing
    """
    
    MODEL_PATH = "data/models/tail_scorer.json"
    
    def __init__(self):
        self.model: Optional[xgb.XGBClassifier] = None
        self.is_trained = False
        
        # Training buffer
        self.X_buffer: List[np.ndarray] = []
        self.y_buffer: List[int] = []
        self.buffer_size = 50
        
        # Historical stats by category
        self.category_stats = {
            "political": {"total": 0, "wins": 0},
            "crypto": {"total": 0, "wins": 0},
            "sports": {"total": 0, "wins": 0},
            "finance": {"total": 0, "wins": 0},
            "tech": {"total": 0, "wins": 0},
            "other": {"total": 0, "wins": 0}
        }
        
        # Model params
        self.params = {
            "n_estimators": 50,
            "max_depth": 3,
            "learning_rate": 0.1,
            "objective": "binary:logistic",
            "eval_metric": "logloss"
        }
        
        # Load existing model
        self._load()
        
    def _load(self):
        """Load model from disk"""
        try:
            if os.path.exists(self.MODEL_PATH):
                self.model = xgb.XGBClassifier()
                self.model.load_model(self.MODEL_PATH)
                self.is_trained = True
                logger.info("Loaded tail scorer model")
                
            # Load category stats
            stats_path = "data/models/tail_category_stats.json"
            if os.path.exists(stats_path):
                with open(stats_path, "r") as f:
                    self.category_stats = json.load(f)
                    
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
            
    def _save(self):
        """Save model to disk"""
        try:
            os.makedirs(os.path.dirname(self.MODEL_PATH), exist_ok=True)
            
            if self.model:
                self.model.save_model(self.MODEL_PATH)
                
            # Save category stats
            with open("data/models/tail_category_stats.json", "w") as f:
                json.dump(self.category_stats, f, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save model: {e}")
            
    def score(self, opportunity: Dict) -> TailScoreResult:
        """Score a tail betting opportunity"""
        
        # Create features
        features = TailFeatureEngineer.create_features(opportunity)
        
        # Calculate rule-based score
        rule_score = self._rule_based_score(features, opportunity)
        
        # Get ML prediction if model is trained
        if self.is_trained and self.model:
            X = features.to_array().reshape(1, -1)
            ml_prob = float(self.model.predict_proba(X)[0][1])
        else:
            ml_prob = 0.01  # Default 1% for tail bets
            
        # Combine scores
        if self.is_trained:
            # Weight ML more as we get more data
            final_prob = ml_prob * 0.6 + rule_score * 0.01 * 0.4
        else:
            final_prob = rule_score * 0.01  # Convert to probability
            
        # Calculate expected value
        stake = 2.0
        potential = stake / features.yes_price if features.yes_price > 0 else 0
        expected_value = (final_prob * potential) - ((1 - final_prob) * stake)
        
        # Generate recommendation
        reasoning = []
        
        if features.yes_price <= 0.01:
            reasoning.append(f"Very low price ({features.yes_price:.3f}) = high asymmetry")
        elif features.yes_price <= 0.02:
            reasoning.append(f"Low price ({features.yes_price:.3f}) = good asymmetry")
            
        if features.days_to_expiry < 7:
            reasoning.append("Short time to expiry - quick resolution")
        elif features.days_to_expiry > 180:
            reasoning.append("Long time to expiry - capital tied up")
            
        # Category insights
        category = self._get_category(features)
        if category in self.category_stats:
            stats = self.category_stats[category]
            if stats["total"] > 10:
                hit_rate = stats["wins"] / stats["total"]
                reasoning.append(f"Historical hit rate for {category}: {hit_rate:.1%}")
                
        # Determine recommendation
        if expected_value > 0.5 and rule_score > 70:
            recommendation = "BET"
            reasoning.append("Positive expected value")
        elif expected_value > 0 and rule_score > 50:
            recommendation = "WATCH"
            reasoning.append("Marginal expected value")
        else:
            recommendation = "SKIP"
            reasoning.append("Negative expected value or low score")
            
        return TailScoreResult(
            opportunity_score=rule_score / 100,
            win_probability=final_prob,
            expected_value=expected_value,
            recommendation=recommendation,
            reasoning=reasoning,
            features=features
        )
        
    def _rule_based_score(self, features: TailFeatures, opportunity: Dict) -> float:
        """Calculate rule-based score (0-100)"""
        score = 50  # Base score
        
        # Price scoring (lower = better)
        if features.yes_price <= 0.005:
            score += 20  # Excellent price
        elif features.yes_price <= 0.01:
            score += 15
        elif features.yes_price <= 0.02:
            score += 10
        elif features.yes_price <= 0.03:
            score += 5
            
        # Time to expiry scoring
        if 7 <= features.days_to_expiry <= 30:
            score += 10  # Sweet spot
        elif features.days_to_expiry < 7:
            score += 5  # Quick resolution
        elif features.days_to_expiry > 180:
            score -= 5  # Too long
            
        # Category bonuses
        if features.is_crypto:
            score += 5  # Crypto events are often surprising
        if features.is_tech:
            score += 3  # Tech announcements
            
        # Potential return bonus
        if features.potential_return >= 500:
            score += 10
        elif features.potential_return >= 200:
            score += 5
            
        return max(0, min(100, score))
        
    def _get_category(self, features: TailFeatures) -> str:
        """Get main category from features"""
        if features.is_political:
            return "political"
        elif features.is_crypto:
            return "crypto"
        elif features.is_sports:
            return "sports"
        elif features.is_finance:
            return "finance"
        elif features.is_tech:
            return "tech"
        return "other"
        
    def add_outcome(self, features: TailFeatures, won: bool):
        """Add outcome for learning"""
        # Update category stats
        category = self._get_category(features)
        if category in self.category_stats:
            self.category_stats[category]["total"] += 1
            if won:
                self.category_stats[category]["wins"] += 1
                
        # Add to training buffer
        X = features.to_array()
        y = 1 if won else 0
        
        self.X_buffer.append(X)
        self.y_buffer.append(y)
        
        # Retrain if buffer is full
        if len(self.X_buffer) >= self.buffer_size:
            self._retrain()
            
        self._save()
        
    def _retrain(self):
        """Retrain model with buffered data"""
        if len(self.X_buffer) < 20:
            return
            
        X = np.array(self.X_buffer)
        y = np.array(self.y_buffer)
        
        # Check class balance
        unique, counts = np.unique(y, return_counts=True)
        if len(unique) < 2:
            logger.warning("Need samples from both classes to train")
            return
            
        logger.info(f"Retraining tail scorer with {len(X)} samples...")
        
        self.model = xgb.XGBClassifier(**self.params)
        self.model.fit(X, y)
        self.is_trained = True
        
        # Keep recent samples
        self.X_buffer = self.X_buffer[-20:]
        self.y_buffer = self.y_buffer[-20:]
        
        self._save()


# =============================================================================
# REWARD SYSTEM FOR TAIL BETTING
# =============================================================================

@dataclass
class TailReward:
    """Reward calculation for tail bet outcome"""
    base_reward: float          # Based on win/loss
    risk_adjusted: float        # Adjusted for stake
    category_bonus: float       # Bonus for category performance
    total_reward: float         # Combined reward


class TailRewardCalculator:
    """Calculates rewards for reinforcement learning"""
    
    def __init__(self):
        self.total_rewards = 0.0
        self.rewards_history: List[TailReward] = []
        
    def calculate(
        self,
        won: bool,
        stake: float,
        potential_return: float,
        actual_return: float,
        features: TailFeatures
    ) -> TailReward:
        """Calculate reward for a tail bet outcome"""
        
        if won:
            # Win: reward based on actual profit
            base = actual_return / stake
            risk_adjusted = np.log1p(actual_return) * 2  # Log reward to prevent dominance
        else:
            # Loss: small negative reward (expected for tail bets)
            base = -1.0
            risk_adjusted = -0.5  # Less penalty since losses are expected
            
        # Category bonus (encourage learning categories)
        category_bonus = 0.0
        if won:
            if features.is_crypto:
                category_bonus = 0.2
            elif features.is_tech:
                category_bonus = 0.1
                
        total = base + risk_adjusted + category_bonus
        
        reward = TailReward(
            base_reward=base,
            risk_adjusted=risk_adjusted,
            category_bonus=category_bonus,
            total_reward=total
        )
        
        self.rewards_history.append(reward)
        self.total_rewards += total
        
        return reward
        
    def get_stats(self) -> Dict:
        """Get reward statistics"""
        if not self.rewards_history:
            return {"total": 0, "avg": 0, "count": 0}
            
        returns = [r.total_reward for r in self.rewards_history]
        
        return {
            "total": self.total_rewards,
            "avg": np.mean(returns),
            "std": np.std(returns),
            "count": len(returns),
            "positive": sum(1 for r in returns if r > 0),
            "negative": sum(1 for r in returns if r < 0)
        }


# =============================================================================
# MAIN
# =============================================================================

def test_scorer():
    """Test the tail scorer"""
    print("\n" + "=" * 60)
    print("🧪 Testing Tail Scorer")
    print("=" * 60)
    
    scorer = XGBoostTailScorer()
    
    # Sample opportunities
    opportunities = [
        {
            "question": "Will Bitcoin reach $200,000 by December 31?",
            "yes_price": 0.003,
            "liquidity": 5000,
            "volume_24h": 10000,
            "end_date": "2025-12-31",
            "potential_return": 667
        },
        {
            "question": "Will Trump win the 2028 election?",
            "yes_price": 0.02,
            "liquidity": 20000,
            "volume_24h": 50000,
            "end_date": "2028-11-15",
            "potential_return": 100
        },
        {
            "question": "Will Half-Life 3 be announced before 2026?",
            "yes_price": 0.004,
            "liquidity": 3000,
            "volume_24h": 5000,
            "end_date": "2025-12-31",
            "potential_return": 500
        }
    ]
    
    for opp in opportunities:
        result = scorer.score(opp)
        
        print(f"\n📊 {opp['question'][:50]}...")
        print(f"   Price: ${opp['yes_price']:.3f} | Potential: {opp['potential_return']:.0f}x")
        print(f"   Score: {result.opportunity_score:.2f}")
        print(f"   Win Prob: {result.win_probability:.2%}")
        print(f"   Expected Value: ${result.expected_value:.2f}")
        print(f"   Recommendation: {result.recommendation}")
        print(f"   Reasons: {', '.join(result.reasoning)}")


if __name__ == "__main__":
    test_scorer()
