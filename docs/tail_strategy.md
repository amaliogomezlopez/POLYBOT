# Tail Betting Strategy - @Spon Implementation

## 🎯 Strategy Overview

Based on @Spon's Polymarket strategy that turned ~$2 bets into $100k+:

- **Scan** all markets every 60 seconds
- **Hunt** tail outcomes (very unlikely events)
- **Buy** YES tokens at 1-4 cents
- **Fixed** $2 downside per bet
- **Target** 100x-1000x potential returns

## 📊 Current Status

```
╔════════════════════════════════════════════════════════════════════╗
║                    🎲 TAIL BETTING BOT                             ║
╠════════════════════════════════════════════════════════════════════╣
║   Total Bets:      44                                              ║
║   Investment:      $88.00                                          ║
║   Potential:       154x - 1333x (avg 497x)                         ║
║   Markets Found:   201 tail markets                                ║
╚════════════════════════════════════════════════════════════════════╝
```

## 🧮 Mathematical Analysis

### Monte Carlo Simulation Results (10,000 simulations, 100 bets each)

| Scenario | Hit Rate | Multiplier | Avg Profit | P(Profit) |
|----------|----------|------------|------------|-----------|
| Conservative | 1% | 40x | -$120 | 9% ❌ |
| Moderate | 2% | 50x | -$1 | 46% ⚠️ |
| **Optimistic** | 3% | 60x | **+$162** | **76%** ✅ |

### Kelly Criterion Analysis

For 2% hit rate with 50x average multiplier:
- Expected Value per bet: ~0% (break-even)
- Need >2.5% hit rate to be consistently profitable

### Key Insight

The strategy works if we can achieve **>2.5% hit rate** with **50x+ average multiplier**.

## 🛠️ Quick Commands

```bash
# Run the bot (paper trading)
python -m src.trading.tail_bot

# Check resolution status
python -m src.trading.resolution_tracker

# View dashboard
python tools/dashboard.py

# Find tail markets
python tools/find_tails.py

# Run backtest simulation
python tools/backtest_tails.py
```

## 📁 File Structure

```
src/
├── trading/
│   ├── tail_bot.py           # Main bot implementation
│   └── resolution_tracker.py # Track bet outcomes
├── scanner/
│   └── tail_scanner.py       # Scan for tail markets
└── ai/
    └── tail_scorer.py        # XGBoost ML scorer

tools/
├── dashboard.py              # Status dashboard
├── find_tails.py             # Quick tail finder
└── backtest_tails.py         # Monte Carlo backtest

data/
└── tail_bot/
    ├── bets.json             # All placed bets
    ├── state.json            # Bot state
    ├── stats.json            # Performance stats
    └── results.json          # Resolved bets
```

## 📈 Strategy Logic

1. **Scanning**: Every 60 seconds, query CLOB API for all markets
2. **Filtering**: Find YES tokens priced at $0.01-$0.04
3. **Scoring**: Use XGBoost to rank opportunities by expected value
4. **Execution**: Place $2 bet on highest-scored opportunities
5. **Tracking**: Monitor for resolution, update statistics
6. **Learning**: Feed outcomes back to XGBoost for improvement

## ⚠️ Risk Management

- **Fixed stake**: $2 per bet (never more)
- **Paper trading**: Currently in paper mode, no real money
- **Diversification**: Bet on many markets (44+ currently)
- **Expected loss**: ~$0-2 per bet on average
- **Tail risk**: One 100x+ winner covers 50 losses

## 🎰 Expected Performance

With 100 bets at $2 each ($200 total investment):

| Hit Rate | Expected Wins | Expected Return | Expected Profit |
|----------|---------------|-----------------|-----------------|
| 1% | 1 win | $50 | -$150 |
| 2% | 2 wins | $100 | -$100 |
| 3% | 3 wins | $180 | -$20 |
| 4% | 4 wins | $240 | +$40 |
| 5% | 5 wins | $300 | +$100 |

**Target**: Achieve 3-5% hit rate through smart market selection.

## 🔮 Next Steps

1. Run paper trading for 1-2 weeks to gather resolution data
2. Analyze actual hit rate vs expected
3. Train XGBoost on real outcomes
4. If profitable, consider small real bets
5. Continue iterating on market selection criteria
