"""
Realistic Market Simulator for ML Training
Generates synthetic market data with realistic patterns.
Used when real flash markets are unavailable.
"""
import random
import math
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import json
import os


@dataclass
class SimulatedTick:
    """Simulated market tick"""
    timestamp: float
    asset: str
    price: float
    bid: float
    ask: float
    spread: float
    volume: float
    momentum: float
    volatility: float
    trend: str  # BULLISH, BEARISH, SIDEWAYS
    
    # Ground truth for ML training
    future_price: float = 0.0
    actual_direction: str = ""  # UP, DOWN


@dataclass
class MarketRegime:
    """Market regime with specific characteristics"""
    name: str
    trend_strength: float  # -1 to 1 (bearish to bullish)
    volatility: float  # 0 to 1
    mean_reversion: float  # 0 to 1 (how much price reverts)
    momentum_persistence: float  # 0 to 1
    jump_probability: float  # Probability of sudden moves
    duration_minutes: int = 30


class RealisticMarketSimulator:
    """
    Generates realistic market data with various patterns.
    
    Features:
    - Multiple market regimes (trending, ranging, volatile)
    - Mean reversion and momentum
    - Support/resistance levels
    - News-like jumps
    - Realistic volume patterns
    """
    
    ASSETS = {
        "BTC": {"base_price": 0.50, "volatility": 0.02, "volume_base": 50000},
        "ETH": {"base_price": 0.50, "volatility": 0.025, "volume_base": 30000},
        "SOL": {"base_price": 0.50, "volatility": 0.03, "volume_base": 20000},
        "DOGE": {"base_price": 0.50, "volatility": 0.04, "volume_base": 10000}
    }
    
    REGIMES = [
        MarketRegime("STRONG_BULL", 0.7, 0.3, 0.2, 0.8, 0.05, 20),
        MarketRegime("WEAK_BULL", 0.3, 0.4, 0.4, 0.5, 0.03, 30),
        MarketRegime("SIDEWAYS", 0.0, 0.5, 0.7, 0.3, 0.02, 40),
        MarketRegime("WEAK_BEAR", -0.3, 0.4, 0.4, 0.5, 0.03, 30),
        MarketRegime("STRONG_BEAR", -0.7, 0.3, 0.2, 0.8, 0.05, 20),
        MarketRegime("HIGH_VOL", 0.0, 0.8, 0.3, 0.4, 0.1, 15),
        MarketRegime("LOW_VOL", 0.1, 0.2, 0.6, 0.3, 0.01, 45),
    ]
    
    def __init__(self, seed: int = None):
        if seed:
            random.seed(seed)
        
        self.current_prices: Dict[str, float] = {}
        self.price_history: Dict[str, List[float]] = {}
        self.current_regime: MarketRegime = random.choice(self.REGIMES)
        self.regime_start: float = time.time()
        self.support_levels: Dict[str, List[float]] = {}
        self.resistance_levels: Dict[str, List[float]] = {}
        
        # Initialize
        self._initialize_markets()
        
    def _initialize_markets(self):
        """Initialize market state"""
        for asset, config in self.ASSETS.items():
            # Start with random price around base
            self.current_prices[asset] = config["base_price"] + random.uniform(-0.1, 0.1)
            self.price_history[asset] = [self.current_prices[asset]]
            
            # Set support/resistance
            base = config["base_price"]
            self.support_levels[asset] = [base - 0.15, base - 0.25]
            self.resistance_levels[asset] = [base + 0.15, base + 0.25]
            
    def _check_regime_change(self):
        """Check if we should change market regime"""
        elapsed = time.time() - self.regime_start
        if elapsed > self.current_regime.duration_minutes * 60:
            self.current_regime = random.choice(self.REGIMES)
            self.regime_start = time.time()
            return True
        return False
        
    def _calculate_next_price(self, asset: str, current: float) -> Tuple[float, str]:
        """Calculate next price based on regime and patterns"""
        config = self.ASSETS[asset]
        regime = self.current_regime
        
        # Base volatility
        vol = config["volatility"] * regime.volatility
        
        # Trend component
        trend_move = regime.trend_strength * vol * 0.5
        
        # Random component
        random_move = random.gauss(0, vol)
        
        # Momentum (from recent price history)
        history = self.price_history[asset][-20:]
        if len(history) >= 2:
            recent_momentum = (history[-1] - history[0]) / len(history)
            momentum_move = recent_momentum * regime.momentum_persistence * 10
        else:
            momentum_move = 0
            
        # Mean reversion
        mean_price = config["base_price"]
        reversion_move = (mean_price - current) * regime.mean_reversion * 0.1
        
        # Support/resistance bounce
        bounce = 0
        for support in self.support_levels[asset]:
            if current < support + 0.02 and current > support - 0.02:
                bounce += 0.01 * random.random()  # Bounce up from support
        for resistance in self.resistance_levels[asset]:
            if current > resistance - 0.02 and current < resistance + 0.02:
                bounce -= 0.01 * random.random()  # Bounce down from resistance
                
        # Jump/news event
        jump = 0
        if random.random() < regime.jump_probability:
            jump = random.choice([-1, 1]) * random.uniform(0.02, 0.05)
            
        # Combine
        total_move = trend_move + random_move + momentum_move + reversion_move + bounce + jump
        
        # Apply
        new_price = current + total_move
        
        # Clamp to valid range
        new_price = max(0.01, min(0.99, new_price))
        
        # Determine actual direction
        direction = "UP" if new_price > current else "DOWN"
        if abs(new_price - current) < 0.0005:
            direction = random.choice(["UP", "DOWN"])  # Coin flip for tiny moves
            
        return new_price, direction
        
    def generate_tick(
        self, 
        asset: str = None,
        prediction_horizon_seconds: float = 60.0
    ) -> SimulatedTick:
        """Generate a single market tick with future price"""
        if asset is None:
            asset = random.choice(list(self.ASSETS.keys()))
            
        if asset not in self.current_prices:
            self._initialize_markets()
            
        # Check regime change
        self._check_regime_change()
        
        # Current state
        current = self.current_prices[asset]
        config = self.ASSETS[asset]
        regime = self.current_regime
        
        # Calculate bid/ask
        spread_pct = 0.01 + regime.volatility * 0.02  # 1-3% spread
        spread = current * spread_pct
        bid = current - spread / 2
        ask = current + spread / 2
        
        # Volume
        base_vol = config["volume_base"]
        vol_mult = 1 + regime.volatility * random.uniform(0.5, 2)
        volume = base_vol * vol_mult
        
        # Momentum from history
        history = self.price_history[asset]
        if len(history) >= 5:
            momentum = (history[-1] - history[-5]) / 5
        else:
            momentum = 0
            
        # Trend string
        if regime.trend_strength > 0.3:
            trend = "BULLISH"
        elif regime.trend_strength < -0.3:
            trend = "BEARISH"
        else:
            trend = "SIDEWAYS"
            
        # Calculate future price (for ground truth)
        future = current
        steps = int(prediction_horizon_seconds / 2)  # 2 second steps
        for _ in range(steps):
            future, _ = self._calculate_next_price(asset, future)
            
        actual_direction = "UP" if future > current else "DOWN"
        if abs(future - current) < 0.001:
            actual_direction = random.choice(["UP", "DOWN"])
            
        # Update state
        next_price, _ = self._calculate_next_price(asset, current)
        self.current_prices[asset] = next_price
        self.price_history[asset].append(next_price)
        
        # Keep history bounded
        if len(self.price_history[asset]) > 1000:
            self.price_history[asset] = self.price_history[asset][-500:]
            
        return SimulatedTick(
            timestamp=time.time(),
            asset=asset,
            price=current,
            bid=bid,
            ask=ask,
            spread=spread,
            volume=volume,
            momentum=momentum,
            volatility=regime.volatility,
            trend=trend,
            future_price=future,
            actual_direction=actual_direction
        )
        
    def generate_dataset(
        self,
        n_samples: int = 1000,
        assets: List[str] = None
    ) -> List[SimulatedTick]:
        """Generate a dataset of ticks for training"""
        if assets is None:
            assets = list(self.ASSETS.keys())
            
        dataset = []
        for i in range(n_samples):
            asset = random.choice(assets)
            tick = self.generate_tick(asset)
            dataset.append(tick)
            
            # Small delay to simulate time passing
            if i % 10 == 0:
                self._check_regime_change()
                
        return dataset
        
    def tick_to_features(self, tick: SimulatedTick) -> Dict:
        """Convert tick to feature dict for ML"""
        return {
            "current_price": tick.price,
            "price_1m_ago": tick.price - tick.momentum * 30,  # Approximate
            "price_5m_ago": tick.price - tick.momentum * 150,
            "spread": tick.spread,
            "volume": tick.volume,
            "liquidity": tick.volume * 2,
            "best_bid": tick.bid,
            "best_ask": tick.ask,
            "bid_size": tick.volume * 0.6,
            "ask_size": tick.volume * 0.4,
            "momentum": tick.momentum,
            "volatility": tick.volatility,
            "timestamp": tick.timestamp
        }


class DatasetGenerator:
    """Generate training datasets for ML models"""
    
    def __init__(self, output_dir: str = "data/training"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.simulator = RealisticMarketSimulator()
        
    def generate_training_set(
        self,
        n_samples: int = 5000,
        train_ratio: float = 0.8
    ) -> Tuple[str, str]:
        """Generate train/test split datasets"""
        print(f"🎲 Generating {n_samples} samples...")
        
        dataset = self.simulator.generate_dataset(n_samples)
        
        # Split
        split_idx = int(len(dataset) * train_ratio)
        train_data = dataset[:split_idx]
        test_data = dataset[split_idx:]
        
        # Convert to dicts
        train_dicts = []
        for tick in train_data:
            train_dicts.append({
                "features": self.simulator.tick_to_features(tick),
                "asset": tick.asset,
                "actual_direction": tick.actual_direction,
                "price_change": tick.future_price - tick.price
            })
            
        test_dicts = []
        for tick in test_data:
            test_dicts.append({
                "features": self.simulator.tick_to_features(tick),
                "asset": tick.asset,
                "actual_direction": tick.actual_direction,
                "price_change": tick.future_price - tick.price
            })
            
        # Save
        timestamp = int(time.time())
        train_file = os.path.join(self.output_dir, f"train_{timestamp}.json")
        test_file = os.path.join(self.output_dir, f"test_{timestamp}.json")
        
        with open(train_file, 'w') as f:
            json.dump(train_dicts, f)
        with open(test_file, 'w') as f:
            json.dump(test_dicts, f)
            
        print(f"✅ Saved {len(train_dicts)} training samples to {train_file}")
        print(f"✅ Saved {len(test_dicts)} test samples to {test_file}")
        
        # Stats
        up_count = sum(1 for d in train_dicts if d["actual_direction"] == "UP")
        print(f"\n📊 Dataset Stats:")
        print(f"  UP: {up_count} ({up_count/len(train_dicts)*100:.1f}%)")
        print(f"  DOWN: {len(train_dicts) - up_count} ({(len(train_dicts)-up_count)/len(train_dicts)*100:.1f}%)")
        
        return train_file, test_file


def main():
    """Generate training data"""
    generator = DatasetGenerator()
    train_file, test_file = generator.generate_training_set(n_samples=5000)
    
    # Quick test
    print("\n🧪 Sample from training data:")
    with open(train_file) as f:
        data = json.load(f)
        for sample in data[:3]:
            print(f"  Asset: {sample['asset']} | Direction: {sample['actual_direction']} | Change: {sample['price_change']:.4f}")


if __name__ == "__main__":
    main()
