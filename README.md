# Polymarket Arbitrage Bot

Delta-neutral arbitrage bot for Polymarket's 15-minute crypto flash markets.

## 📚 Documentation
For detailed information, please refer to the [Documentation Index](docs/index.md).

- [Architecture & Design](docs/architecture.md)
- [Trading Strategy](docs/strategy.md)
- [Installation & Setup](docs/setup.md)
- [Competitor Reverse Engineering](docs/competitor_analysis.md)
- [Project Status & Roadmap](docs/current_status.md)

## Strategy

This bot replicates the "Jane Street" strategy: buying both UP and DOWN tokens when their combined cost is below $1.00, guaranteeing profit regardless of outcome.

- **Target**: 15-minute UP/DOWN crypto markets (BTC, ETH, SOL)
- **Mechanism**: Delta-neutral arbitrage
- **Expected profit**: 4-16 cents per $1 contract

## Installation

```bash
# Install Poetry (if not installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Copy environment file
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

Edit `.env` with your settings:

```env
POLYMARKET_PRIVATE_KEY=your_private_key
POLYMARKET_FUNDER_ADDRESS=your_funder_address
MAX_POSITION_SIZE_USDC=1000
MIN_PROFIT_THRESHOLD=0.04
```

## Usage

```bash
# Start the bot
poetry run polybot run

# Paper trading mode (no real orders)
poetry run polybot run --paper

# Check current positions
poetry run polybot status

# View trade history
poetry run polybot history
```

## Project Structure

```
src/
├── config/      # Settings and constants
├── scanner/     # Market discovery and WebSocket feeds
├── detector/    # Spread analysis and opportunity detection
├── trading/     # Order execution and position management
├── risk/        # Risk management and validation
├── db/          # Database models and repository
└── monitoring/  # P&L tracking, alerts, dashboard
```

## Development

```bash
# Run tests
poetry run pytest

# Format code
poetry run black src tests
poetry run ruff check src tests --fix

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
