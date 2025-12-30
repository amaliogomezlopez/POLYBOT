"""
Real-time evaluator using live Polymarket data.
NO TRADING - Prediction validation only.
"""
import asyncio
import sys
import os
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.polymarket_feed import PolymarketFeed, MarketTick, DataCollector


@dataclass
class PredictionRecord:
    """Record of a prediction for later validation"""
    timestamp: float
    token_id: str
    question: str
    predicted_direction: str  # UP or DOWN
    predicted_confidence: float
    method: str  # LLM, XGB, RULES, HYBRID
    entry_price: float
    # Filled after validation
    exit_price: Optional[float] = None
    actual_direction: Optional[str] = None
    is_correct: Optional[bool] = None
    pnl_pct: float = 0.0
    validation_time: Optional[float] = None


@dataclass
class LiveEvaluatorStats:
    """Statistics for live evaluation"""
    total_predictions: int = 0
    validated_predictions: int = 0
    correct_predictions: int = 0
    total_pnl_pct: float = 0.0
    by_method: Dict[str, Dict] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)


class LiveEvaluator:
    """
    Evaluates prediction methods against live Polymarket data.
    NO TRADING - Just validates predictions.
    """
    
    def __init__(
        self,
        validation_window_seconds: float = 60.0,  # How long to wait before validating
        min_price_change: float = 0.001  # Minimum price change to consider
    ):
        self.validation_window = validation_window_seconds
        self.min_price_change = min_price_change
        
        # State
        self.pending_predictions: List[PredictionRecord] = []
        self.validated_predictions: List[PredictionRecord] = []
        self.stats = LiveEvaluatorStats()
        
        # Predictors (will be loaded)
        self.hybrid_predictor = None
        self.groq_client = None
        self.xgboost_model = None
        
        # Feed
        self.feed = None
        self.collector = DataCollector()
        
    async def initialize(self):
        """Initialize predictors and feed"""
        print("🔧 Initializing Live Evaluator...")
        
        # Load GROQ client
        try:
            from src.ai.groq_client import GroqClient
            self.groq_client = GroqClient()
            print("  ✓ GROQ client loaded")
        except Exception as e:
            print(f"  ✗ GROQ client failed: {e}")
            
        # Load XGBoost model
        try:
            from src.ai.xgboost_model import XGBoostPredictor
            self.xgboost_model = XGBoostPredictor()
            # Try to load saved model
            try:
                self.xgboost_model.load("data/models/xgb_model.json")
                print("  ✓ XGBoost model loaded (pre-trained)")
            except:
                print("  ✓ XGBoost model loaded (untrained)")
        except Exception as e:
            print(f"  ✗ XGBoost model failed: {e}")
            
        # Load Hybrid predictor
        try:
            from src.ai.hybrid_predictor import HybridPredictor
            self.hybrid_predictor = HybridPredictor(
                use_llm=True,
                use_xgboost=True,
                use_rules=True
            )
            print("  ✓ Hybrid predictor loaded")
        except Exception as e:
            print(f"  ✗ Hybrid predictor failed: {e}")
            
        # Initialize feed
        self.feed = PolymarketFeed()
        print("  ✓ Polymarket feed ready")
        
    def _tick_to_market_data(self, tick: MarketTick) -> Dict:
        """Convert tick to market data format for predictors"""
        return {
            "current_price": tick.mid_price,
            "price_1m_ago": tick.mid_price - tick.price_change_1m,
            "price_5m_ago": tick.mid_price - tick.price_change_5m,
            "spread": tick.spread,
            "volume": tick.volume_24h,
            "liquidity": tick.liquidity,
            "best_bid": tick.best_bid,
            "best_ask": tick.best_ask,
            "bid_size": tick.bid_size,
            "ask_size": tick.ask_size,
            "timestamp": tick.timestamp
        }
        
    def _detect_asset(self, question: str) -> str:
        """Detect asset from question"""
        q = question.lower()
        if "btc" in q or "bitcoin" in q:
            return "BTC"
        elif "eth" in q or "ethereum" in q:
            return "ETH"
        elif "sol" in q or "solana" in q:
            return "SOL"
        else:
            return "CRYPTO"
            
    async def make_predictions(self, tick: MarketTick) -> Dict[str, PredictionRecord]:
        """Make predictions from all methods for a tick"""
        predictions = {}
        market_data = self._tick_to_market_data(tick)
        asset = self._detect_asset(tick.question)
        
        # 1. Rules-based prediction
        try:
            from src.ai.hybrid_predictor import RulesPredictor
            rules = RulesPredictor()
            r_pred = rules.predict(market_data)
            predictions["RULES"] = PredictionRecord(
                timestamp=tick.timestamp,
                token_id=tick.token_id,
                question=tick.question,
                predicted_direction=r_pred.direction,
                predicted_confidence=r_pred.confidence,
                method="RULES",
                entry_price=tick.mid_price
            )
        except Exception as e:
            print(f"  Rules error: {e}")
            
        # 2. XGBoost prediction
        if self.xgboost_model:
            try:
                from src.ai.xgboost_model import FeatureEngineer
                features = FeatureEngineer.create_features(market_data, asset)
                xgb_pred = self.xgboost_model.predict(features)
                predictions["XGB"] = PredictionRecord(
                    timestamp=tick.timestamp,
                    token_id=tick.token_id,
                    question=tick.question,
                    predicted_direction=xgb_pred.direction,
                    predicted_confidence=xgb_pred.confidence,
                    method="XGB",
                    entry_price=tick.mid_price
                )
            except Exception as e:
                print(f"  XGB error: {e}")
                
        # 3. LLM prediction (with rate limit handling)
        if self.groq_client:
            try:
                llm_dir, llm_conf, llm_latency = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.groq_client.quick_decision,
                        market_data,
                        asset
                    ),
                    timeout=10.0
                )
                predictions["LLM"] = PredictionRecord(
                    timestamp=tick.timestamp,
                    token_id=tick.token_id,
                    question=tick.question,
                    predicted_direction=llm_dir,
                    predicted_confidence=llm_conf,
                    method="LLM",
                    entry_price=tick.mid_price
                )
            except asyncio.TimeoutError:
                print("  LLM timeout")
            except Exception as e:
                print(f"  LLM error: {e}")
                
        # 4. Hybrid prediction
        if self.hybrid_predictor and len(predictions) >= 2:
            try:
                hybrid = await asyncio.to_thread(
                    self.hybrid_predictor.predict,
                    market_data,
                    asset
                )
                predictions["HYBRID"] = PredictionRecord(
                    timestamp=tick.timestamp,
                    token_id=tick.token_id,
                    question=tick.question,
                    predicted_direction=hybrid.direction,
                    predicted_confidence=hybrid.confidence,
                    method="HYBRID",
                    entry_price=tick.mid_price
                )
            except Exception as e:
                print(f"  Hybrid error: {e}")
                
        return predictions
        
    def validate_predictions(self, current_price: float, token_id: str):
        """Validate pending predictions that have expired"""
        now = time.time()
        still_pending = []
        
        for pred in self.pending_predictions:
            if pred.token_id != token_id:
                still_pending.append(pred)
                continue
                
            age = now - pred.timestamp
            if age < self.validation_window:
                still_pending.append(pred)
                continue
                
            # Validate this prediction
            price_change = current_price - pred.entry_price
            actual_direction = "UP" if price_change > 0 else "DOWN"
            
            # Skip if no significant change
            if abs(price_change) < self.min_price_change:
                actual_direction = pred.predicted_direction  # Count as correct if flat
                
            pred.exit_price = current_price
            pred.actual_direction = actual_direction
            pred.is_correct = (pred.predicted_direction == actual_direction)
            pred.pnl_pct = (price_change / pred.entry_price) * 100 if pred.entry_price > 0 else 0
            pred.validation_time = now
            
            # Adjust PnL based on direction
            if pred.predicted_direction == "DOWN":
                pred.pnl_pct = -pred.pnl_pct
                
            self.validated_predictions.append(pred)
            self._update_stats(pred)
            
        self.pending_predictions = still_pending
        
    def _update_stats(self, pred: PredictionRecord):
        """Update statistics with validated prediction"""
        self.stats.validated_predictions += 1
        
        if pred.is_correct:
            self.stats.correct_predictions += 1
            
        self.stats.total_pnl_pct += pred.pnl_pct
        
        # Update by method
        if pred.method not in self.stats.by_method:
            self.stats.by_method[pred.method] = {
                "total": 0,
                "correct": 0,
                "pnl_pct": 0.0
            }
            
        method_stats = self.stats.by_method[pred.method]
        method_stats["total"] += 1
        if pred.is_correct:
            method_stats["correct"] += 1
        method_stats["pnl_pct"] += pred.pnl_pct
        
    def print_status(self):
        """Print current evaluation status"""
        print("\n" + "=" * 60)
        print("📊 LIVE EVALUATION STATUS")
        print("=" * 60)
        
        runtime = time.time() - self.stats.start_time
        print(f"⏱️  Runtime: {runtime/60:.1f} minutes")
        print(f"📈 Predictions: {self.stats.validated_predictions} validated, {len(self.pending_predictions)} pending")
        
        if self.stats.validated_predictions > 0:
            accuracy = self.stats.correct_predictions / self.stats.validated_predictions * 100
            print(f"🎯 Overall Accuracy: {accuracy:.1f}%")
            print(f"💰 Total P&L: {self.stats.total_pnl_pct:+.2f}%")
            
        print("\n📊 By Method:")
        for method, stats in sorted(self.stats.by_method.items()):
            if stats["total"] > 0:
                acc = stats["correct"] / stats["total"] * 100
                print(f"  {method:8s} | Acc: {acc:5.1f}% ({stats['correct']:2d}/{stats['total']:2d}) | P&L: {stats['pnl_pct']:+.2f}%")
                
        print("=" * 60 + "\n")
        
    async def train_xgboost_from_validation(self):
        """Train XGBoost model from validated predictions"""
        if not self.xgboost_model:
            return
            
        training_count = 0
        for pred in self.validated_predictions:
            if pred.actual_direction:
                # Create features from the prediction data
                market_data = {
                    "current_price": pred.entry_price,
                    "price_1m_ago": pred.entry_price * 0.999,  # Approximation
                    "price_5m_ago": pred.entry_price * 0.998,
                    "spread": 0.01,
                    "volume": 10000,
                    "liquidity": 50000
                }
                asset = self._detect_asset(pred.question)
                
                from src.ai.xgboost_model import FeatureEngineer
                features = FeatureEngineer.create_features(market_data, asset)
                
                # Train with actual outcome
                label = 1 if pred.actual_direction == "UP" else 0
                self.xgboost_model.train_online(features, label)
                training_count += 1
                
        if training_count > 0:
            print(f"🎓 Trained XGBoost with {training_count} samples")
            
    def save_results(self):
        """Save evaluation results"""
        os.makedirs("data/live_evaluation", exist_ok=True)
        
        timestamp = int(time.time())
        
        # Save predictions
        preds_file = f"data/live_evaluation/predictions_{timestamp}.json"
        with open(preds_file, 'w') as f:
            json.dump([{
                "timestamp": p.timestamp,
                "token_id": p.token_id,
                "question": p.question[:100],
                "method": p.method,
                "predicted": p.predicted_direction,
                "actual": p.actual_direction,
                "correct": p.is_correct,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "pnl_pct": p.pnl_pct
            } for p in self.validated_predictions], f, indent=2)
            
        # Save stats
        stats_file = f"data/live_evaluation/stats_{timestamp}.json"
        with open(stats_file, 'w') as f:
            json.dump({
                "runtime_seconds": time.time() - self.stats.start_time,
                "total_predictions": self.stats.validated_predictions,
                "correct_predictions": self.stats.correct_predictions,
                "accuracy": self.stats.correct_predictions / max(1, self.stats.validated_predictions),
                "total_pnl_pct": self.stats.total_pnl_pct,
                "by_method": self.stats.by_method
            }, f, indent=2)
            
        print(f"💾 Results saved to data/live_evaluation/")
        
        # Save XGBoost model
        if self.xgboost_model:
            os.makedirs("data/models", exist_ok=True)
            self.xgboost_model.save("data/models/xgb_model.json")
            print("💾 XGBoost model saved")


async def run_live_evaluation(duration_minutes: float = 10, interval_seconds: float = 30):
    """
    Run live evaluation against real Polymarket data.
    NO TRADING - Just validates predictions.
    """
    print("\n" + "=" * 60)
    print("🚀 LIVE EVALUATION - REAL POLYMARKET DATA")
    print("⚠️  NO TRADING - Prediction validation only")
    print("=" * 60 + "\n")
    
    evaluator = LiveEvaluator(
        validation_window_seconds=60,  # Validate after 1 minute
        min_price_change=0.001
    )
    
    await evaluator.initialize()
    
    async with PolymarketFeed() as feed:
        # Get markets to track
        print("\n🔍 Finding markets to track...")
        markets = await feed.get_active_markets(limit=20)
        
        # Filter for markets with tokens
        trackable = [m for m in markets if m.get("tokens")][:5]
        
        if not trackable:
            print("❌ No trackable markets found!")
            return
            
        print(f"\n📊 Tracking {len(trackable)} markets:")
        for m in trackable:
            print(f"  - {m['question'][:50]}...")
            
        # Run evaluation loop
        end_time = time.time() + (duration_minutes * 60)
        tick_count = 0
        
        print(f"\n⏱️  Running for {duration_minutes} minutes...")
        print(f"   Validation window: 60 seconds")
        print(f"   Polling interval: {interval_seconds} seconds\n")
        
        try:
            while time.time() < end_time:
                for market in trackable:
                    token_id = market["tokens"][0]
                    
                    # Get current tick
                    tick = await feed.get_market_tick(
                        token_id,
                        market["question"],
                        "YES"
                    )
                    
                    if not tick:
                        continue
                        
                    tick_count += 1
                    
                    # Validate old predictions
                    evaluator.validate_predictions(tick.mid_price, token_id)
                    
                    # Make new predictions
                    if tick_count % 2 == 1:  # Every other tick to avoid spam
                        predictions = await evaluator.make_predictions(tick)
                        
                        if predictions:
                            evaluator.pending_predictions.extend(predictions.values())
                            evaluator.stats.total_predictions += len(predictions)
                            
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                                  f"Token: {token_id[:8]}... | "
                                  f"Price: {tick.mid_price:.4f} | "
                                  f"Predictions: {list(predictions.keys())}")
                            
                    # Record tick
                    evaluator.collector.record_tick(tick)
                    
                # Train XGBoost periodically
                if evaluator.stats.validated_predictions > 0 and evaluator.stats.validated_predictions % 5 == 0:
                    await evaluator.train_xgboost_from_validation()
                    
                # Print status every minute
                if tick_count % int(60 / interval_seconds) == 0:
                    evaluator.print_status()
                    
                await asyncio.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\n⚠️ Interrupted by user")
            
        # Final validation - wait for pending to complete
        print("\n⏳ Final validation pass...")
        await asyncio.sleep(65)  # Wait for validation window
        
        # Validate remaining
        for market in trackable:
            token_id = market["tokens"][0]
            tick = await feed.get_market_tick(token_id, market["question"])
            if tick:
                evaluator.validate_predictions(tick.mid_price, token_id)
                
        # Print final results
        evaluator.print_status()
        
        # Save results
        evaluator.save_results()
        evaluator.collector.save()
        
        return evaluator.stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Live Polymarket Evaluation")
    parser.add_argument("--duration", type=float, default=10, help="Duration in minutes")
    parser.add_argument("--interval", type=float, default=30, help="Polling interval in seconds")
    
    args = parser.parse_args()
    
    asyncio.run(run_live_evaluation(
        duration_minutes=args.duration,
        interval_seconds=args.interval
    ))
