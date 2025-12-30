"""Main arbitrage trading strategy."""

import asyncio
from datetime import datetime
from typing import Any

import structlog

from src.config.settings import Settings
from src.detector.dislocation_detector import DislocationDetector
from src.detector.spread_analyzer import SpreadAnalyzer
from src.models import ArbitrageOpportunity, Market
from src.scanner.market_scanner import MarketScanner
from src.scanner.websocket_feed import OrderbookSnapshot, WebSocketFeed
from src.trading.order_executor import OrderExecutor
from src.trading.position_manager import PositionManager

logger = structlog.get_logger(__name__)


class ArbitrageStrategy:
    """
    Main arbitrage strategy orchestrator.
    
    Coordinates market scanning, opportunity detection, and trade execution
    to implement the delta-neutral arbitrage strategy.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the arbitrage strategy.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._running = False
        self._scan_interval = 5.0  # seconds between market scans

        # Initialize components
        self.order_executor = OrderExecutor(
            private_key=settings.polymarket_private_key,
            funder_address=settings.polymarket_funder_address,
            signature_type=settings.signature_type,
            paper_trading=settings.paper_trading,
        )

        self.position_manager = PositionManager(self.order_executor)

        self.spread_analyzer = SpreadAnalyzer(
            min_profit_threshold=settings.min_profit_threshold,
            min_liquidity=100.0,
            max_position_size=settings.max_position_size_usdc,
        )

        self.dislocation_detector = DislocationDetector()
        self.market_scanner: MarketScanner | None = None
        self.websocket_feed: WebSocketFeed | None = None

        # Active opportunities
        self._opportunities: dict[str, ArbitrageOpportunity] = {}
        self._subscribed_markets: set[str] = set()

    async def start(self) -> None:
        """Start the trading strategy."""
        logger.info(
            "Starting arbitrage strategy",
            paper_trading=self.settings.paper_trading,
            max_position=self.settings.max_position_size_usdc,
            min_profit=self.settings.min_profit_threshold,
        )

        # Initialize components
        await self.order_executor.initialize()

        self._running = True

        # Start background tasks
        async with MarketScanner() as scanner:
            self.market_scanner = scanner

            self.websocket_feed = WebSocketFeed()
            self.websocket_feed.add_callback(self._on_orderbook_update)

            try:
                await asyncio.gather(
                    self._run_market_scan_loop(),
                    self._run_opportunity_processor(),
                    self.websocket_feed.run(),
                )
            except asyncio.CancelledError:
                logger.info("Strategy stopped")
            finally:
                await self.stop()

    async def stop(self) -> None:
        """Stop the trading strategy."""
        self._running = False

        if self.websocket_feed:
            await self.websocket_feed.disconnect()

        logger.info(
            "Strategy stopped",
            **self.position_manager.get_position_summary(),
        )

    async def _run_market_scan_loop(self) -> None:
        """Continuously scan for flash markets."""
        while self._running:
            try:
                await self._scan_markets()
            except Exception as e:
                logger.error("Market scan error", error=str(e))

            await asyncio.sleep(self._scan_interval)

    async def _scan_markets(self) -> None:
        """Scan for new flash markets and subscribe to their feeds."""
        if not self.market_scanner:
            return

        markets = await self.market_scanner.scan_flash_markets()

        for market in markets:
            if not market.tokens:
                continue

            market_id = market.id

            # Subscribe to new markets
            if market_id not in self._subscribed_markets and self.websocket_feed:
                await self.websocket_feed.subscribe(market.tokens.up_token_id)
                await self.websocket_feed.subscribe(market.tokens.down_token_id)
                self._subscribed_markets.add(market_id)

                logger.debug(
                    "Subscribed to market",
                    market_id=market_id,
                    asset=market.asset,
                )

            # Get current prices and analyze
            tokens = await self.market_scanner.get_market_prices(market)
            if tokens:
                await self._analyze_opportunity(market, tokens.up_price, tokens.down_price)

    def _on_orderbook_update(self, token_id: str, orderbook: OrderbookSnapshot) -> None:
        """Handle orderbook update from WebSocket."""
        # This is called synchronously from the WebSocket feed
        # We need to be careful not to block

        # Update dislocation detector
        # Note: We'd need to map token_id back to market to get both prices
        # For now, this is a placeholder for the callback mechanism
        pass

    async def _analyze_opportunity(
        self,
        market: Market,
        up_price: float,
        down_price: float,
    ) -> None:
        """Analyze a market for arbitrage opportunity."""
        if not market.tokens:
            return

        # Skip if we already have a position in this market
        existing = self.position_manager.get_positions_for_market(market.id)
        if existing:
            return

        # Skip if total exposure is too high
        if self.position_manager.total_exposure >= self.settings.max_total_exposure_usdc:
            return

        # Analyze spread
        result = self.spread_analyzer.analyze(
            market=market,
            up_price=up_price,
            down_price=down_price,
            up_liquidity=market.tokens.up_liquidity or 1000,  # Default if unknown
            down_liquidity=market.tokens.down_liquidity or 1000,
        )

        if not result.is_profitable:
            return

        # Create opportunity
        opportunity = self.spread_analyzer.create_opportunity(market, result)
        if opportunity:
            self._opportunities[market.id] = opportunity

    async def _run_opportunity_processor(self) -> None:
        """Process and execute opportunities."""
        while self._running:
            try:
                await self._process_opportunities()
            except Exception as e:
                logger.error("Opportunity processing error", error=str(e))

            await asyncio.sleep(1.0)

    async def _process_opportunities(self) -> None:
        """Process pending opportunities."""
        if not self._opportunities:
            return

        # Sort by score (best first)
        sorted_opps = sorted(
            self._opportunities.values(),
            key=lambda o: o.score,
            reverse=True,
        )

        for opportunity in sorted_opps:
            # Check if opportunity is still valid
            if opportunity.market.is_closed:
                self._opportunities.pop(opportunity.market.id, None)
                continue

            # Check exposure limit
            remaining_exposure = (
                self.settings.max_total_exposure_usdc -
                self.position_manager.total_exposure
            )

            if remaining_exposure <= 0:
                break

            # Calculate position size
            size = min(
                self.settings.max_position_size_usdc,
                remaining_exposure,
                opportunity.max_contracts * opportunity.total_cost,
            )

            if size < 10:  # Minimum position size
                continue

            # Execute the trade
            position = await self.position_manager.open_position(
                opportunity=opportunity,
                size_usdc=size,
            )

            if position:
                self._opportunities.pop(opportunity.market.id, None)

                logger.info(
                    "Position opened from opportunity",
                    market_id=opportunity.market.id,
                    asset=opportunity.market.asset,
                    size=size,
                    expected_profit=size * opportunity.profit_per_contract / opportunity.total_cost,
                )

    def get_status(self) -> dict[str, Any]:
        """Get current strategy status."""
        return {
            "running": self._running,
            "paper_trading": self.settings.paper_trading,
            "subscribed_markets": len(self._subscribed_markets),
            "pending_opportunities": len(self._opportunities),
            **self.position_manager.get_position_summary(),
        }
