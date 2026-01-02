"""
📦 Trading Strategies Module
=============================
Multi-strategy trading system with Strategy Pattern.

Strategies:
- ArbitrageStrategy: Cross-exchange arbitrage (Polymarket vs PredictBase)
- SniperStrategy: Microstructure sniper (panic drop rebounds)
- TailStrategy: Tail betting (low price, high multiplier)

Usage:
    from src.trading.strategies import (
        ArbitrageStrategy,
        SniperStrategy, 
        TailStrategy,
        strategy_registry
    )
    
    # Register strategies
    strategy_registry.register(ArbitrageStrategy())
    strategy_registry.register(SniperStrategy())
    strategy_registry.register(TailStrategy())
    
    # Process market
    signals = await strategy_registry.process_all(market_data)
"""

from .base_strategy import (
    BaseStrategy,
    MarketData,
    TradeSignal,
    SignalType,
    StrategyRegistry,
    strategy_registry
)

from .arbitrage_strategy import ArbitrageStrategy, ArbitrageDetector
from .sniper_strategy import SniperStrategy
from .tail_strategy import TailStrategy, TailScorer

__all__ = [
    # Base
    'BaseStrategy',
    'MarketData',
    'TradeSignal',
    'SignalType',
    'StrategyRegistry',
    'strategy_registry',
    
    # Strategies
    'ArbitrageStrategy',
    'SniperStrategy',
    'TailStrategy',
    
    # Utilities
    'ArbitrageDetector',
    'TailScorer',
]
