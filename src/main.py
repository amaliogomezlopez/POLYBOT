"""Main application entry point."""

import asyncio
import signal
import sys
from typing import Any

import structlog

from src.config.settings import get_settings
from src.monitoring.alerts import AlertManager
from src.monitoring.dashboard import Dashboard
from src.monitoring.pnl_tracker import PnLTracker
from src.risk.risk_manager import RiskManager
from src.trading.strategy import ArbitrageStrategy


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    import logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level),
    )


logger = structlog.get_logger(__name__)


class Application:
    """Main application class."""

    def __init__(self) -> None:
        """Initialize the application."""
        self.settings = get_settings()
        self._shutdown_event = asyncio.Event()
        self._strategy: ArbitrageStrategy | None = None
        self._pnl_tracker: PnLTracker | None = None
        self._risk_manager: RiskManager | None = None
        self._alert_manager: AlertManager | None = None
        self._dashboard: Dashboard | None = None

    async def start(self) -> None:
        """Start the application."""
        logger.info(
            "Starting Polymarket Arbitrage Bot",
            environment=self.settings.environment,
            paper_trading=self.settings.paper_trading,
        )

        # Initialize components
        self._pnl_tracker = PnLTracker()
        self._risk_manager = RiskManager(self.settings)
        self._alert_manager = AlertManager(
            telegram_token=self.settings.telegram_bot_token,
            telegram_chat_id=self.settings.telegram_chat_id,
        )
        self._dashboard = Dashboard(
            pnl_tracker=self._pnl_tracker,
            risk_manager=self._risk_manager,
        )

        # Start alert manager
        await self._alert_manager.start()

        # Create and run strategy
        self._strategy = ArbitrageStrategy(self.settings)

        try:
            await self._strategy.start()
        except asyncio.CancelledError:
            logger.info("Application cancelled")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down...")

        if self._strategy:
            await self._strategy.stop()

        if self._alert_manager:
            await self._alert_manager.stop()

        # Print final summary
        if self._strategy:
            status = self._strategy.get_status()
            logger.info("Final status", **status)

        logger.info("Shutdown complete")

    def print_status(self) -> None:
        """Print current status to console."""
        if not self._strategy or not self._dashboard:
            return

        positions = self._strategy.position_manager.open_positions
        opportunities = [
            {
                "asset": opp.market.asset,
                "up_price": opp.up_price,
                "down_price": opp.down_price,
                "total_cost": opp.total_cost,
                "profit": opp.profit_per_contract,
                "score": opp.score,
            }
            for opp in self._strategy._opportunities.values()
        ]

        self._dashboard.print_status(positions, opportunities)


async def run_bot(paper_trading: bool = False) -> None:
    """
    Run the trading bot.

    Args:
        paper_trading: Enable paper trading mode
    """
    # Override settings if paper trading specified
    if paper_trading:
        import os
        os.environ["PAPER_TRADING"] = "true"

    app = Application()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        asyncio.create_task(app.shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await app.start()


def main() -> None:
    """Main entry point."""
    setup_logging()

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception("Fatal error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
