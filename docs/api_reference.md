# API Reference & Module Index

The bot is organized into functional packages under `src/`.

## `src.scanner`
- **`MarketScanner`**: Query Gamma API for new markers. Filters for `crypto` assets and `15m` durations.
- **`WebsocketFeed`**: Async generator that yields order book L2 snapshots from Polymarket CLOB.

## `src.detector`
- **`SpreadAnalyzer`**: Pure logic class for calculating arbitrage math. Returns `ArbitrageOpportunity` objects.
- **`DislocationDetector`**: Tracks price movements and calculates z-scores for spread instability.

## `src.trading`
- **`OrderExecutor`**: High-level interface for placing orders. Handles the complex signing logic of EIP-712.
- **`PositionManager`**: Singleton responsible for the lifecycle of a trade. Ensures an UP buy is paired with a DOWN buy.
- **`ArbitrageStrategy`**: The loop orchestrator.

## `src.risk`
- **`RiskManager`**: Core safeguard. All trades pass through `can_open_position()`.
- **`Validators`**: Static checks (e.g., minimum balance, market expiration time).

## `src.monitoring`
- **`PnLTracker`**: Tracks USDC balances and token valuations to calculate realized and unrealized P&L.
- **`Dashboard`**: TUI interface built with `rich`.
- **`AlertManager`**: Async notification worker for Telegram.

## `src.db`
- **`Repository`**: Async CRUD operations using SQLAlchemy and `aiosqlite`.
- **`models`**: Declarative base classes for Markets, Trades, and Positions.

## `src.reporting`
- **`PerformanceReporter`**: Logic to aggregate historical trades into human-readable performance reports.
