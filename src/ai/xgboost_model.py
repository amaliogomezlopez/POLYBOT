"""
XGBoost Trading Model
Machine learning model for market direction prediction.
"""

import os
import sys
import json
import pickle
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

# Check if XGBoost is available
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("XGBoost not installed. Install with: pip install xgboost")


@dataclass
class FeatureVector:
    """Features for ML prediction"""
    # Price features
    price: float                    # Current token price (0-1)
    price_momentum: float           # Recent price change
    
    # Trend features
    trend_1m: float                 # 1-minute trend
    trend_5m: float                 # 5-minute trend
    trend_15m: float                # 15-minute trend
    
    # Volatility
    volatility: float               # Recent volatility
    volatility_ratio: float         # Current vs avg volatility
    
    # Volume
    volume_ratio: float             # Volume vs average
    
    # Time features
    hour_sin: float                 # Hour encoded as sine
    hour_cos: float                 # Hour encoded as cosine
    minute_sin: float               # Minute encoded as sine
    minute_cos: float               # Minute encoded as cosine
    
    # Asset encoding
    is_btc: int                     # 1 if BTC, 0 if ETH
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array for model"""
        return np.array([
            self.price,
            self.price_momentum,
            self.trend_1m,
            self.trend_5m,
            self.trend_15m,
            self.volatility,
            self.volatility_ratio,
            self.volume_ratio,
            self.hour_sin,
            self.hour_cos,
            self.minute_sin,
            self.minute_cos,
            self.is_btc
        ])
    
    @staticmethod
    def feature_names() -> List[str]:
        return [
            "price", "price_momentum",
            "trend_1m", "trend_5m", "trend_15m",
            "volatility", "volatility_ratio", "volume_ratio",
            "hour_sin", "hour_cos", "minute_sin", "minute_cos",
            "is_btc"
        ]


class FeatureEngineer:
    """Creates features from raw market data"""
    
    @staticmethod
    def encode_time(dt: datetime) -> Dict[str, float]:
        """Encode time as cyclic features"""
        hour = dt.hour
        minute = dt.minute
        
        return {
            "hour_sin": np.sin(2 * np.pi * hour / 24),
            "hour_cos": np.cos(2 * np.pi * hour / 24),
            "minute_sin": np.sin(2 * np.pi * minute / 60),
            "minute_cos": np.cos(2 * np.pi * minute / 60)
        }
    
    @staticmethod
    def create_features(
        market_data: Dict[str, Any],
        asset: str = "BTC"
    ) -> FeatureVector:
        """Create feature vector from market data"""
        now = datetime.now()
        time_features = FeatureEngineer.encode_time(now)
        
        return FeatureVector(
            price=market_data.get("price", 0.5),
            price_momentum=market_data.get("momentum", 0),
            trend_1m=market_data.get("trend", 0) * 0.3,
            trend_5m=market_data.get("trend", 0) * 0.6,
            trend_15m=market_data.get("trend", 0),
            volatility=market_data.get("volatility", 1.0),
            volatility_ratio=market_data.get("volatility", 1.0) / 1.0,
            volume_ratio=market_data.get("volume_ratio", 1.0),
            hour_sin=time_features["hour_sin"],
            hour_cos=time_features["hour_cos"],
            minute_sin=time_features["minute_sin"],
            minute_cos=time_features["minute_cos"],
            is_btc=1 if asset.upper() == "BTC" else 0
        )


class XGBoostPredictor:
    """
    XGBoost model for market direction prediction.
    
    Features:
    - Online learning (incremental updates)
    - Feature importance tracking
    - Model persistence
    - Confidence calibration
    """
    
    MODEL_DIR = Path("data/models")
    
    def __init__(self, model_path: Optional[str] = None):
        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        
        self.model: Optional[xgb.XGBClassifier] = None
        self.is_trained = False
        self.training_samples = 0
        
        # Training data buffer
        self.X_buffer: List[np.ndarray] = []
        self.y_buffer: List[int] = []
        self.buffer_size = 100  # Retrain after this many samples
        
        # Model parameters optimized for trading
        self.params = {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "use_label_encoder": False,
            "random_state": 42
        }
        
        # Load existing model
        if model_path:
            self.load(model_path)
        else:
            default_path = self.MODEL_DIR / "xgb_trading.pkl"
            if default_path.exists():
                self.load(str(default_path))
        
        logger.info(f"XGBoostPredictor initialized. Trained: {self.is_trained}")
    
    def predict(
        self,
        features: FeatureVector
    ) -> Tuple[str, float]:
        """
        Predict market direction.
        
        Args:
            features: Feature vector
            
        Returns:
            (direction, confidence)
        """
        if not self.is_trained:
            # Return random until trained
            return "UP", 0.50
        
        X = features.to_array().reshape(1, -1)
        
        # Get probability
        prob = self.model.predict_proba(X)[0]
        
        # prob[0] = probability of DOWN (0)
        # prob[1] = probability of UP (1)
        
        if prob[1] > prob[0]:
            direction = "UP"
            confidence = prob[1]
        else:
            direction = "DOWN"
            confidence = prob[0]
        
        # Calibrate confidence (reduce overconfidence)
        confidence = 0.5 + (confidence - 0.5) * 0.8
        confidence = max(0.50, min(0.90, confidence))
        
        return direction, confidence
    
    def add_sample(
        self,
        features: FeatureVector,
        actual_direction: str
    ) -> None:
        """
        Add training sample to buffer.
        
        Args:
            features: Feature vector at time of prediction
            actual_direction: What actually happened (UP/DOWN)
        """
        X = features.to_array()
        y = 1 if actual_direction == "UP" else 0
        
        self.X_buffer.append(X)
        self.y_buffer.append(y)
        
        # Retrain if buffer is full
        if len(self.X_buffer) >= self.buffer_size:
            self._retrain()
    
    def _retrain(self) -> None:
        """Retrain model with buffered data"""
        if len(self.X_buffer) < 20:
            logger.warning("Not enough samples to train")
            return
        
        X = np.array(self.X_buffer)
        y = np.array(self.y_buffer)
        
        # Check class balance
        unique, counts = np.unique(y, return_counts=True)
        if len(unique) < 2:
            logger.warning("Need samples from both classes")
            return
        
        logger.info(f"Retraining XGBoost with {len(X)} samples...")
        
        if XGBOOST_AVAILABLE:
            self.model = xgb.XGBClassifier(**self.params)
            self.model.fit(X, y)
            self.is_trained = True
            self.training_samples += len(X)
            
            # Save model
            self.save()
            
            # Clear buffer (keep some for continuity)
            keep = min(20, len(self.X_buffer))
            self.X_buffer = self.X_buffer[-keep:]
            self.y_buffer = self.y_buffer[-keep:]
            
            logger.info(f"Model retrained. Total samples: {self.training_samples}")
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores"""
        if not self.is_trained:
            return {}
        
        importance = self.model.feature_importances_
        names = FeatureVector.feature_names()
        
        return dict(sorted(
            zip(names, importance),
            key=lambda x: x[1],
            reverse=True
        ))
    
    def save(self, path: Optional[str] = None) -> None:
        """Save model to disk"""
        if not self.is_trained:
            return
        
        save_path = Path(path) if path else self.MODEL_DIR / "xgb_trading.pkl"
        
        data = {
            "model": self.model,
            "training_samples": self.training_samples,
            "params": self.params,
            "timestamp": datetime.now().isoformat()
        }
        
        with open(save_path, 'wb') as f:
            pickle.dump(data, f)
        
        logger.info(f"Model saved to {save_path}")
    
    def load(self, path: str) -> bool:
        """Load model from disk"""
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            
            self.model = data["model"]
            self.training_samples = data.get("training_samples", 0)
            self.is_trained = True
            
            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get model statistics"""
        return {
            "is_trained": self.is_trained,
            "training_samples": self.training_samples,
            "buffer_size": len(self.X_buffer),
            "feature_importance": self.get_feature_importance() if self.is_trained else {}
        }


# Global instance
_xgb_predictor: Optional[XGBoostPredictor] = None


def get_xgb_predictor() -> XGBoostPredictor:
    """Get or create global XGBoost predictor"""
    global _xgb_predictor
    if _xgb_predictor is None:
        _xgb_predictor = XGBoostPredictor()
    return _xgb_predictor
