# Whale Hunting Research Suite

## Overview
This research module provides tools for reverse-engineering the trading strategies of top Polymarket traders ("Whales"). The goal is to identify profitable patterns that can inform our own bot development.

> **⚠️ Isolation Notice**: This module is completely isolated from the production codebase in `src/`. All code and data reside in `research/whale_hunting/`.

## Architecture

```
research/whale_hunting/
├── harvester.py    # Async data collection from Gamma API
├── analyzer.py     # Behavioral analysis & classification
├── data/           # Parquet files (gitignored)
└── report.md       # Auto-generated analysis report
```

## Quick Start

### 1. Install Dependencies
```bash
pip install pandas pyarrow aiohttp structlog matplotlib polars
```

### 2. Run the Harvester
```bash
cd research/whale_hunting
python harvester.py
```
This will download trade history for all configured whales and save to `data/*.parquet`.

### 3. Run the Analyzer
```bash
python analyzer.py
```
This generates `report.md` with classifications and insights.

## Configured Targets
The default whale list includes:
- `Account88888` - Known flash arbitrageur
- `whaatttt` - High-volume trader
- `HaileyWelch` - Celebrity account
- `Theo4`, `SilverLining`, `Fredi9999` - Top leaderboard accounts

## Metrics Computed

### Frequency Analysis
- **Trades per hour**: Detect bot vs human behavior
- **Median interval**: Time between consecutive trades
- **Peak activity hours**: When is the trader most active?

### P&L Attribution
- **Delta-neutral ratio**: Percentage of markets where user trades both sides
- **Buy/Sell balance**: Directional bias detection

### Category Focus
- Crypto vs Sports vs Politics market preference

### Classification
Traders are classified into archetypes:
- 🤖 **Arbitrageur**: High-frequency, delta-neutral, crypto-focused
- 💹 **Market Maker**: Balanced buys/sells, liquidity provision
- 📰 **News Trader**: Politics-focused, directional bets
- 🎰 **Gambler**: Sports-focused, low frequency

## Output Files
- `data/{username}_trades.parquet` - Raw trade data
- `report.md` - Human-readable analysis report

## Extending the Suite
To add new whales, edit the `WHALE_LIST` in `harvester.py`.
To add new metrics, extend the `analyze_*` functions in `analyzer.py`.
