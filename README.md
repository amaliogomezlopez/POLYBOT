# Polymarket Tail Betting Bot

🎯 **Automated tail betting system** for Polymarket prediction markets.

> **Strategy Pivot**: After discovering no flash markets exist (all spreads 98%+), we pivoted to **tail betting** - the optimal strategy for low-capital traders.

## 📊 Current Status (December 2025)

| Metric | Value |
|--------|-------|
| **Paper Bets** | 100 |
| **Invested** | $200 (paper) |
| **Avg Multiplier** | 252x |
| **Required Hit Rate** | 0.4% |

## 📚 Documentation

- [**Current Status & Roadmap**](docs/current_status.md) ⭐
- [Architecture & Design](docs/architecture.md)
- [Trading Strategy](docs/strategy.md)
- [Installation & Setup](docs/setup.md)
- [Competitor Analysis (@RN1)](docs/competitor_analysis.md)

## 🎯 Strategy: Tail Betting

Buy YES tokens priced < $0.04 for potential **25x-1000x returns**.

- **Stake**: $2 per bet (fixed)
- **Target**: YES < 4¢ (potential 25x+)
- **ML Scoring**: Category-weighted selection
- **Required hit rate**: 0.4% (1 win per 250 bets)

### Why Tail Betting?
1. **No flash markets** on Polymarket - HFT arbitrage not viable
2. **@RN1 analysis** showed $774k profit requires $500k+ capital
3. **Monte Carlo**: 30% chance to 2x vs 0% copying pros
4. **Low risk**: Only $2 per bet, diversified across 100+ bets

## Installation

```bash
# Install Poetry (if not installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Copy environment file
cp .env.example .env
## Installation

```bash
# Install dependencies
pip install httpx

# Or with Poetry
poetry install

# Copy environment file
cp .env.example .env
```

## Configuration

Edit `.env` with your settings:

```env
PAPER_TRADING=true
POLYMARKET_PRIVATE_KEY=your_private_key
```

## 🚀 Quick Start

```bash
# View dashboard
python tools/tail_dashboard.py

# Place new tail bets
python tools/place_tail_bets.py --max 25

# Scan for opportunities
python tools/scan_tails.py

# Run scheduled monitor (daemon)
python scripts/scheduled_monitor.py --daemon --interval 30
```

## 🖥️ Server Deployment

### Windows Scheduled Task
```powershell
.\scripts\create_windows_task.ps1
```

### Linux Server (systemd)
```bash
./scripts/deploy_server.sh systemd
sudo systemctl enable polymarket-tail-monitor
sudo systemctl start polymarket-tail-monitor
```

## Project Structure

```
src/
├── trading/     # TailBot, order execution
├── ai/          # XGBoost tail scorer
├── risk/        # Risk management
└── monitoring/  # Dashboard, alerts

tools/
├── tail_dashboard.py    # Real-time monitoring
├── place_tail_bets.py   # ML-scored betting
├── scan_tails.py        # Market scanner
└── analyze_rn1.py       # Competitor analysis

scripts/
├── scheduled_monitor.py     # Daemon monitor
├── create_windows_task.ps1  # Windows task
└── deploy_server.sh         # Linux deploy

data/tail_bot/
├── bets.json            # Paper bets (100)
├── resolved.json        # Resolved bets
└── training_data.json   # XGBoost training
```

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black src tests

# Type checking
poetry run mypy src
```

## Risk Warning

⚠️ **USE AT YOUR OWN RISK**

- This bot trades real money
- Always start with small position sizes
- Past performance does not guarantee future results
- Execution latency and slippage can affect profitability

## License

MIT
