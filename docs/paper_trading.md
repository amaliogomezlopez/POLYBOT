# Paper Trading System

## ❓ Why Paper Trading?

**Polymarket does NOT offer paper/demo accounts.** Every trade uses real USDC.

Our Paper Trading system solves this by:
- Simulating trades with virtual money ($100 default)
- Tracking hypothetical P&L with real market conditions
- Persisting trade history to JSON files
- Providing detailed statistics for strategy validation

## 🚀 Quick Start

### Interactive CLI

```bash
python tools/paper_trading_cli.py
```

This launches an interactive menu:
```
📊 POLYMARKET PAPER TRADING SYSTEM
Starting balance: $100.00

1. Place new trade
2. View pending trades
3. Resolve trade
4. View statistics
5. Trade history
6. AI market analysis
7. Reset portfolio
q. Quit
```

### Programmatic Usage

```python
from src.trading.paper_trader import PaperTrader

# Create paper trader
pt = PaperTrader(initial_balance=100.0)

# Place a simulated trade
trade = pt.place_trade(
    asset='BTC',
    market_id='btc_flash_12345',
    market_question='Will BTC go UP in 1 hour?',
    side='UP',
    entry_price=0.55,       # $0.55 per token
    size_usdc=5.0,          # Spend $5
    ai_bias='UP',           # AI prediction
    ai_confidence=0.75,     # 75% confidence
    notes='First test trade'
)

# Tokens bought = $5 / $0.55 = 9.09 tokens
print(f"Tokens bought: {trade.tokens_bought:.2f}")
print(f"Remaining balance: ${pt.balance:.2f}")

# Later: resolve the trade
# If BTC went UP and we bought UP tokens -> WIN
# Each token pays $1 if correct, $0 if wrong
pt.resolve_trade(trade.id, won=True)

# Check P&L
print(f"P&L: ${trade.pnl:+.2f}")  # +$4.09 (9.09 tokens × $0.45 profit each)
```

## 📊 Trade Lifecycle

```
1. PLACE TRADE
   ├── Deduct size_usdc from balance
   ├── Calculate tokens_bought = size_usdc / entry_price
   └── Status: PENDING

2. WAIT FOR MARKET RESOLUTION
   └── Status: PENDING (waiting)

3. RESOLVE TRADE
   ├── If WON: balance += tokens_bought × $1.00
   ├── If LOST: balance += tokens_bought × $0.00
   └── P&L = (exit_price - entry_price) × tokens_bought
```

## 💰 P&L Calculation

### Winning Trade Example
```
Entry price: $0.55
Size: $5.00
Tokens: 9.09

Exit price (WIN): $1.00
Return: 9.09 × $1.00 = $9.09
P&L: $9.09 - $5.00 = +$4.09
ROI: +81.8%
```

### Losing Trade Example
```
Entry price: $0.55
Size: $5.00
Tokens: 9.09

Exit price (LOSS): $0.00
Return: 9.09 × $0.00 = $0.00
P&L: $0.00 - $5.00 = -$5.00
ROI: -100%
```

## 📈 Statistics

```python
stats = pt.get_stats()
```

Returns:
```python
{
    "portfolio": {
        "initial_balance": 100.0,
        "current_balance": 104.09,
        "total_pnl": 4.09,
        "roi": "4.09%",
        "peak_balance": 108.00,
        "max_drawdown": "3.62%"
    },
    "trades": {
        "total": 10,
        "pending": 2,
        "resolved": 8,
        "winning": 5,
        "losing": 3,
        "win_rate": "62.5%"
    },
    "metrics": {
        "avg_win": "$3.50",
        "avg_loss": "$-2.80",
        "profit_factor": 1.25
    }
}
```

## 🗄️ Data Persistence

Trades are saved to:
```
data/paper_trading/
├── portfolio.json    # Balance and portfolio state
└── trades.json       # Trade history
```

Data persists between sessions. Reset with:
```python
pt.reset(initial_balance=100.0)
```

## 🤖 Integration with AI

The paper trading CLI integrates with our AI module:

```python
from src.ai.bias_analyzer import BiasAnalyzer
from src.ai.gemini_client import GeminiClient

# Get AI prediction before trading
bias = await bias_analyzer.get_bias(asset="BTC")

if bias.confidence >= 0.7:
    pt.place_trade(
        asset='BTC',
        side=bias.direction,  # AI-recommended direction
        ai_bias=bias.direction,
        ai_confidence=bias.confidence,
        ...
    )
```

## 📝 Trade Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Unique trade ID |
| `timestamp` | float | Unix timestamp |
| `asset` | str | BTC, ETH |
| `market_id` | str | Polymarket market ID |
| `side` | str | "UP" or "DOWN" |
| `entry_price` | float | Price per token |
| `size_usdc` | float | Total USDC spent |
| `tokens_bought` | float | Number of tokens |
| `ai_bias` | str | AI prediction |
| `ai_confidence` | float | AI confidence |
| `status` | TradeStatus | pending/won/lost |
| `pnl` | float | Profit/Loss |

## ⚠️ Limitations

1. **No real order book simulation** - Assumes infinite liquidity
2. **No slippage** - Entry at exact specified price
3. **Manual resolution** - User decides win/loss (or integrate with market scanner)
4. **No time-based resolution** - Markets don't auto-resolve

## 🔮 Future Improvements

1. **Auto-resolution**: Connect to Polymarket API to check market outcomes
2. **Real orderbook**: Simulate slippage based on orderbook depth
3. **Time-based simulation**: Auto-resolve after market end time
4. **Backtesting**: Run strategy on historical data

## 📁 Files

- `src/trading/paper_trader.py` - Core paper trading logic
- `tools/paper_trading_cli.py` - Interactive CLI
- `tools/test_paper_trading.py` - Unit tests
- `data/paper_trading/` - Persisted trade data
