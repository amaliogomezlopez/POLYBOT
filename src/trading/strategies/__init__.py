"""
📦 Trading Strategies Module
=============================
Multi-strategy trading system with Strategy Pattern.

Strategies:
- InternalArbStrategy: Internal arbitrage (orderbook inefficiencies) [NEW]
- SniperStrategy: Microstructure sniper (panic drop rebounds)
- TailStrategy: Tail betting (low price, high multiplier)
- EsportsOracleStrategy: Esports live betting with Riot API

DEPRECATED:
- ArbitrageStrategy: Cross-exchange arbitrage (PredictBase has 0 liquidity)

Usage:
    from src.trading.strategies import (
        InternalArbStrategy,
        SniperStrategy, 
        TailStrategy,
        strategy_registry
    )
    
    # Register strategies
    strategy_registry.register(InternalArbStrategy())
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

# ACTIVE STRATEGIES
from .internal_arb import (
    InternalArbStrategy,
    InternalArbDetector,
    InternalArbScanner,
    InternalArbOpportunity,
    calculate_internal_arb,
)
from .sniper_strategy import SniperStrategy
from .tail_strategy import TailStrategy, TailScorer
from .esports_oracle import (
    EsportsOracleStrategy,
    OracleStrategyRunner,
    OracleSignal,
    GameEvent,
    StrategyState,
)

# DEPRECATED - PredictBase has 0 liquidity (Jan 2026 analysis)
# Kept for backwards compatibility but should not be used
from .arbitrage_strategy import ArbitrageStrategy, ArbitrageDetector

__all__ = [
    # Base
    'BaseStrategy',
    'MarketData',
    'TradeSignal',
    'SignalType',
    'StrategyRegistry',
    'strategy_registry',
    
    # Active Strategies
    'InternalArbStrategy',
    'SniperStrategy',
    'TailStrategy',
    'EsportsOracleStrategy',
    'OracleStrategyRunner',
    
    # Internal ARB utilities
    'InternalArbDetector',
    'InternalArbScanner',
    'InternalArbOpportunity',
    'calculate_internal_arb',
    
    # Utilities
    'TailScorer',
    'OracleSignal',
    'GameEvent',
    'StrategyState',
    
    # DEPRECATED (PredictBase 0 liquidity)
    'ArbitrageStrategy',
    'ArbitrageDetector',
]
