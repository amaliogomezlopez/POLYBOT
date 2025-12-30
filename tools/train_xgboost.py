"""
XGBoost Model Trainer
Trains the XGBoost model on simulated data with realistic patterns.
"""
import sys
import os
import json
import time
from typing import Dict, List, Tuple
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.market_simulator import RealisticMarketSimulator, DatasetGenerator, SimulatedTick
from src.ai.xgboost_model import XGBoostPredictor, FeatureEngineer, FeatureVector


@dataclass
class TrainingResult:
    """Result of training session"""
    train_accuracy: float
    test_accuracy: float
    train_samples: int
    test_samples: int
    training_time: float
    feature_importance: Dict[str, float]


class XGBoostTrainer:
    """Trains XGBoost model on simulated market data"""
    
    def __init__(self, model_path: str = "data/models/xgb_trained.json"):
        self.model_path = model_path
        self.predictor = XGBoostPredictor()
        self.simulator = RealisticMarketSimulator()
        
    def prepare_sample(self, tick: SimulatedTick) -> Tuple[FeatureVector, int]:
        """Prepare a single training sample"""
        features_dict = self.simulator.tick_to_features(tick)
        features = FeatureEngineer.create_features(features_dict, tick.asset)
        label = 1 if tick.actual_direction == "UP" else 0
        return features, label
        
    def train_batch(self, samples: List[SimulatedTick]) -> None:
        """Train on a batch of samples"""
        for tick in samples:
            features, label = self.prepare_sample(tick)
            direction = "UP" if label == 1 else "DOWN"
            self.predictor.add_sample(features, direction)
            
    def evaluate(self, samples: List[SimulatedTick]) -> float:
        """Evaluate accuracy on samples"""
        correct = 0
        total = 0
        
        for tick in samples:
            features, label = self.prepare_sample(tick)
            direction, confidence = self.predictor.predict(features)
            
            pred_label = 1 if direction == "UP" else 0
            if pred_label == label:
                correct += 1
            total += 1
            
        return correct / total if total > 0 else 0.0
        
    def full_training(
        self,
        n_samples: int = 5000,
        batch_size: int = 100,
        eval_interval: int = 500
    ) -> TrainingResult:
        """Full training run with evaluation"""
        print("\n" + "=" * 60)
        print("🎓 XGBoost Training Session")
        print("=" * 60)
        
        start_time = time.time()
        
        # Generate dataset
        print(f"\n📊 Generating {n_samples} samples...")
        train_samples = self.simulator.generate_dataset(int(n_samples * 0.8))
        test_samples = self.simulator.generate_dataset(int(n_samples * 0.2))
        
        # Count class balance
        train_up = sum(1 for t in train_samples if t.actual_direction == "UP")
        print(f"  Training: {len(train_samples)} samples ({train_up} UP, {len(train_samples)-train_up} DOWN)")
        
        test_up = sum(1 for t in test_samples if t.actual_direction == "UP")
        print(f"  Test: {len(test_samples)} samples ({test_up} UP, {len(test_samples)-test_up} DOWN)")
        
        # Train in batches
        print(f"\n🏋️ Training...")
        
        for i in range(0, len(train_samples), batch_size):
            batch = train_samples[i:i+batch_size]
            self.train_batch(batch)
            
            # Progress
            progress = (i + len(batch)) / len(train_samples) * 100
            
            # Periodic evaluation
            if (i + batch_size) % eval_interval == 0 or i + len(batch) >= len(train_samples):
                # Quick eval on subset
                eval_subset = test_samples[:100]
                acc = self.evaluate(eval_subset)
                print(f"  [{progress:5.1f}%] Samples: {i+len(batch):5d} | Test Acc: {acc*100:.1f}%")
                
        # Final evaluation
        print(f"\n📈 Final Evaluation...")
        train_acc = self.evaluate(train_samples[:500])  # Subset to save time
        test_acc = self.evaluate(test_samples)
        
        training_time = time.time() - start_time
        
        # Feature importance
        try:
            importance = self.predictor.get_feature_importance()
        except:
            importance = {}
        
        # Save model
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        self.predictor.save(self.model_path)
        print(f"\n💾 Model saved to {self.model_path}")
        
        # Results
        result = TrainingResult(
            train_accuracy=train_acc,
            test_accuracy=test_acc,
            train_samples=len(train_samples),
            test_samples=len(test_samples),
            training_time=training_time,
            feature_importance=importance
        )
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TRAINING RESULTS")
        print("=" * 60)
        print(f"  Train Accuracy: {train_acc*100:.2f}%")
        print(f"  Test Accuracy:  {test_acc*100:.2f}%")
        print(f"  Training Time:  {training_time:.1f}s")
        print(f"  Samples Used:   {len(train_samples)}")
        
        print("\n🔑 Top 5 Features:")
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        for feat, imp in sorted_features[:5]:
            print(f"    {feat}: {imp:.3f}")
            
        return result
        

class HybridModelTrainer:
    """Trains both XGBoost and evaluates hybrid ensemble"""
    
    def __init__(self):
        self.xgb_trainer = XGBoostTrainer()
        
    def train_and_evaluate_all(self, n_samples: int = 3000) -> Dict:
        """Train XGBoost and compare all methods"""
        print("\n" + "=" * 60)
        print("🔬 FULL ML PIPELINE TRAINING")
        print("=" * 60)
        
        # 1. Train XGBoost
        xgb_result = self.xgb_trainer.full_training(n_samples=n_samples)
        
        # 2. Generate evaluation set
        print("\n" + "=" * 60)
        print("🧪 COMPARATIVE EVALUATION")
        print("=" * 60)
        
        eval_samples = self.xgb_trainer.simulator.generate_dataset(500)
        
        # Initialize predictors
        from src.ai.hybrid_predictor import HybridPredictor
        
        hybrid = HybridPredictor(use_llm=False, use_xgboost=True, use_rules=True)  # No LLM for speed
        
        results = {
            "XGB": {"correct": 0, "total": 0},
            "HYBRID": {"correct": 0, "total": 0}
        }
        
        print("\n🔄 Evaluating methods...")
        
        for i, tick in enumerate(eval_samples):
            features_dict = self.xgb_trainer.simulator.tick_to_features(tick)
            actual = tick.actual_direction
            
            # XGBoost
            features = FeatureEngineer.create_features(features_dict, tick.asset)
            direction, confidence = self.xgb_trainer.predictor.predict(features)
            results["XGB"]["total"] += 1
            if direction == actual:
                results["XGB"]["correct"] += 1
                
            # Hybrid (XGB + Rules only, no LLM)
            hybrid_pred = hybrid.predict(features_dict, tick.asset)
            results["HYBRID"]["total"] += 1
            if hybrid_pred.direction == actual:
                results["HYBRID"]["correct"] += 1
                
            # Progress
            if (i + 1) % 100 == 0:
                print(f"  Evaluated {i+1}/{len(eval_samples)} samples...")
                
        # Print results
        print("\n" + "=" * 60)
        print("📊 FINAL RESULTS")
        print("=" * 60)
        
        for method, stats in results.items():
            acc = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
            print(f"  {method:8s}: {acc:5.1f}% ({stats['correct']}/{stats['total']})")
            
        # Best method
        best_method = max(results.items(), key=lambda x: x[1]["correct"]/x[1]["total"])
        print(f"\n🏆 Best Method: {best_method[0]} ({best_method[1]['correct']/best_method[1]['total']*100:.1f}%)")
        
        return {
            "xgb_training": {
                "train_acc": xgb_result.train_accuracy,
                "test_acc": xgb_result.test_accuracy,
                "samples": xgb_result.train_samples,
                "time": xgb_result.training_time
            },
            "evaluation": results,
            "best_method": best_method[0]
        }


def main():
    """Main training entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Train XGBoost model")
    parser.add_argument("--samples", type=int, default=3000, help="Number of training samples")
    parser.add_argument("--compare", action="store_true", help="Compare all methods")
    
    args = parser.parse_args()
    
    if args.compare:
        trainer = HybridModelTrainer()
        results = trainer.train_and_evaluate_all(n_samples=args.samples)
    else:
        trainer = XGBoostTrainer()
        trainer.full_training(n_samples=args.samples)


if __name__ == "__main__":
    main()
