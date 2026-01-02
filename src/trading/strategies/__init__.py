"""
📦 Trading Strategies Module
=============================
Multi-strategy trading system with Strategy Pattern.

Strategies:
- InternalArbStrategy: Internal arbitrage (orderbook inefficiencies)
- SniperStrategy: Microstructure sniper (panic drop rebounds)
- TailStrategy: Tail betting (low price, high multiplier)
- EsportsOracleStrategy: Esports live betting with Riot API
- FlashSniperStrategy: Ultra-HFT for 15-min crypto flash markets [NEW v2]
- ContrarianNoStrategy: "Nothing Ever Happens" mean reversion [NEW v2]

DEPRECATED:
- ArbitrageStrategy: Cross-exchange arbitrage (PredictBase has 0 liquidity)

Usage:
    from src.trading.strategies import (
        InternalArbStrategy,
        SniperStrategy, 
        TailStrategy,
        FlashSniperStrategy,
        ContrarianNoStrategy,
        strategy_registry
    )
"""

from .base_strategy import (
    BaseStrategy,
    MarketData,
    TradeSignal,
    SignalType,
    StrategyRegistry,
    strategy_registry
)

# ACTIVE STRATEGIES (Legacy)
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

# NEW V2 STRATEGIES (from Whale Hunting research)
from .flash_sniper import FlashSniperStrategy
from .contrarian_no import ContrarianNoStrategy

__all__ = [
    # Base
    'BaseStrategy',
    'MarketData',
    'TradeSignal',
    'SignalType',
    'StrategyRegistry',
    'strategy_registry',
    
    # Legacy Strategies
    'InternalArbStrategy',
    'SniperStrategy',
    'TailStrategy',
    'EsportsOracleStrategy',
    'OracleStrategyRunner',
    
    # NEW V2 Strategies
    'FlashSniperStrategy',
    'ContrarianNoStrategy',
    
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
]

