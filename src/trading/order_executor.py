"""Order executor for Polymarket CLOB API."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from pydantic import SecretStr

from src.config.constants import (
    CHAIN_ID,
    CLOB_HOST,
    MAX_RETRIES,
    RETRY_BACKOFF_MULTIPLIER,
    RETRY_DELAY_SECONDS,
    OrderType,
    Side,
)
from src.models import Order

logger = structlog.get_logger(__name__)


@dataclass
class OrderResult:
    """Result of an order operation."""

    success: bool
    order_id: str | None = None
    filled_size: float = 0.0
    avg_price: float = 0.0
    error: str | None = None
    raw_response: dict[str, Any] | None = None


class OrderExecutor:
    """
    Executes orders on Polymarket CLOB.
    
    Wraps py-clob-client with retry logic, error handling, and paper trading support.
    """

    def __init__(
        self,
        private_key: SecretStr,
        funder_address: str,
        signature_type: int = 1,
        paper_trading: bool = False,
    ) -> None:
        """
        Initialize order executor.

        Args:
            private_key: Wallet private key for signing
            funder_address: Address that holds funds
            signature_type: 0=EOA, 1=Magic/Email, 2=Browser proxy
            paper_trading: If True, simulate orders without executing
        """
        self.private_key = private_key
        self.funder_address = funder_address
        self.signature_type = signature_type
        self.paper_trading = paper_trading
        self._client: Any = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the CLOB client."""
        if self._initialized:
            return

        try:
            # Import here to avoid import errors if py-clob-client not installed
            from py_clob_client.client import ClobClient

            self._client = ClobClient(
                CLOB_HOST,
                key=self.private_key.get_secret_value(),
                chain_id=CHAIN_ID,
                signature_type=self.signature_type,
                funder=self.funder_address,
            )

            # Set API credentials
            self._client.set_api_creds(self._client.create_or_derive_api_creds())
            self._initialized = True

            logger.info(
                "Order executor initialized",
                funder=self.funder_address[:10] + "...",
                paper_trading=self.paper_trading,
            )

        except ImportError:
            logger.error("py-clob-client not installed. Run: pip install py-clob-client")
            raise
        except Exception as e:
            logger.error("Failed to initialize order executor", error=str(e))
            raise

    async def place_market_order(
        self,
        token_id: str,
        side: Side,
        amount: float,
        order_type: OrderType = OrderType.FOK,
        price_limit: float | None = None,
    ) -> OrderResult:
        """
        Place a market order.

        Args:
            token_id: The token ID to trade
            side: Side.BUY or Side.SELL
            amount: Amount in USDC (for BUY) or Tokens (for SELL)
            order_type: FOK or GTC
            price_limit: Max price (BUY) or Min price (SELL)

        Returns:
            OrderResult object
        """
        if not self._initialized:
            await self.initialize()

        if self.paper_trading:
            return await self._simulate_market_order_enhanced(token_id, side, amount)

        try:
            from py_clob_client.clob_types import MarketOrderArgs
            from py_clob_client.order_builder.constants import BUY, SELL

            side_const = BUY if side == Side.BUY else SELL

            for attempt in range(MAX_RETRIES):
                try:
                    order_args = MarketOrderArgs(
                        token_id=token_id,
                        amount=amount,
                        side=side_const,
                        order_type=order_type.value,
                    )

                    signed_order = self._client.create_market_order(order_args)
                    response = self._client.post_order(signed_order, order_type.value)

                    order_id = response.get("orderID") or response.get("id", "")
                    filled = float(response.get("filledSize", 0) or response.get("filled", 0))

                    logger.info(
                        "Market order placed",
                        token_id=token_id[:20] + "...",
                        side=side.value,
                        amount=amount,
                        order_id=order_id,
                        filled=filled,
                    )

                    return OrderResult(
                        success=True,
                        order_id=order_id,
                        filled_size=filled,
                        raw_response=response,
                    )

                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY_SECONDS * (RETRY_BACKOFF_MULTIPLIER ** attempt)
                        logger.warning(
                            "Order attempt failed, retrying",
                            attempt=attempt + 1,
                            delay=delay,
                            error=str(e),
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

        except Exception as e:
            logger.error("Market order failed", error=str(e))
            return OrderResult(success=False, error=str(e))

        return OrderResult(success=False, error="Max retries exceeded")

    async def place_limit_order(
        self,
        token_id: str,
        side: Side,
        price: float,
        size: float,
        order_type: OrderType = OrderType.GTC,
    ) -> OrderResult:
        """
        Place a limit order.

        Args:
            token_id: Token ID to trade
            side: BUY or SELL
            price: Price per share (0-1)
            size: Number of shares
            order_type: GTC, GTD, etc.

        Returns:
            OrderResult with execution details
        """
        if not self._initialized:
            await self.initialize()

        if self.paper_trading:
            return await self._simulate_limit_order(token_id, side, price, size)

        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY, SELL

            side_const = BUY if side == Side.BUY else SELL

            for attempt in range(MAX_RETRIES):
                try:
                    order_args = OrderArgs(
                        token_id=token_id,
                        price=price,
                        size=size,
                        side=side_const,
                    )

                    signed_order = self._client.create_order(order_args)
                    response = self._client.post_order(signed_order, order_type.value)

                    order_id = response.get("orderID") or response.get("id", "")

                    logger.info(
                        "Limit order placed",
                        token_id=token_id[:20] + "...",
                        side=side.value,
                        price=price,
                        size=size,
                        order_id=order_id,
                    )

                    return OrderResult(
                        success=True,
                        order_id=order_id,
                        raw_response=response,
                    )

                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY_SECONDS * (RETRY_BACKOFF_MULTIPLIER ** attempt)
                        logger.warning(
                            "Limit order attempt failed, retrying",
                            attempt=attempt + 1,
                            delay=delay,
                            error=str(e),
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

        except Exception as e:
            logger.error("Limit order failed", error=str(e))
            return OrderResult(success=False, error=str(e))

        return OrderResult(success=False, error="Max retries exceeded")

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        if not self._initialized:
            await self.initialize()

        if self.paper_trading:
            logger.info("Paper trade: Order cancelled", order_id=order_id)
            return True

        try:
            self._client.cancel(order_id)
            logger.info("Order cancelled", order_id=order_id)
            return True
        except Exception as e:
            logger.error("Cancel order failed", order_id=order_id, error=str(e))
            return False

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        if not self._initialized:
            await self.initialize()

        if self.paper_trading:
            logger.info("Paper trade: All orders cancelled")
            return True

        try:
            self._client.cancel_all()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error("Cancel all orders failed", error=str(e))
            return False

    async def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        if not self._initialized:
            await self.initialize()

        if self.paper_trading:
            return []

        try:
            from py_clob_client.clob_types import OpenOrderParams

            raw_orders = self._client.get_orders(OpenOrderParams())
            orders = []

            for raw in raw_orders:
                order = Order(
                    id=raw.get("id", ""),
                    market_id=raw.get("market", ""),
                    token_id=raw.get("asset_id", ""),
                    side=raw.get("side", "BUY"),
                    price=float(raw.get("price", 0)),
                    size=float(raw.get("original_size", 0)),
                    filled_size=float(raw.get("size_matched", 0)),
                    status=raw.get("status", "open"),
                )
                orders.append(order)

            return orders

        except Exception as e:
            logger.error("Failed to get open orders", error=str(e))
            return []

    async def get_balance(self) -> float:
        """Get USDC balance."""
        if not self._initialized:
            await self.initialize()

        if self.paper_trading:
            return 10000.0  # Simulated balance

        try:
            # This would need to query the blockchain for actual balance
            # For now, return a placeholder
            logger.warning("Balance check not fully implemented")
            return 0.0
        except Exception as e:
            logger.error("Failed to get balance", error=str(e))
            return 0.0

    async def _simulate_market_order(
        self,
        token_id: str,
        side: Side,
        amount: float,
    ) -> OrderResult:
        """Simulate a market order for paper trading."""
        # Simulate some latency
        await asyncio.sleep(0.1)

        order_id = f"paper_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        logger.info(
            "Paper trade: Market order simulated",
            token_id=token_id[:20] + "...",
            side=side.value,
            amount=amount,
            order_id=order_id,
        )

        return OrderResult(
            success=True,
            order_id=order_id,
            filled_size=amount,
            avg_price=0.5,  # Simulated price
        )

    async def _simulate_market_order_enhanced(
        self,
        token_id: str,
        side: Side,
        amount: float,
    ) -> OrderResult:
        """
        Enhanced market order simulation with realistic slippage and latency.
        
        Uses the SlippageSimulator for realistic execution modeling.
        """
        from src.monitoring.latency_logger import get_latency_logger
        from src.trading.slippage_simulator import get_simulator
        
        latency_logger = get_latency_logger()
        simulator = get_simulator()
        
        # Start timing
        start_time = latency_logger.start_timer()
        
        # Run simulation
        result = simulator.simulate_market_order(
            token_id=token_id,
            side=side.value,
            amount_usdc=amount,
        )
        
        # Simulate the latency by sleeping
        await asyncio.sleep(result.latency_ms / 1000)
        
        # Record latency
        latency_logger.record(
            operation="order_placement",
            start_time=start_time,
            success=result.success,
            side=side.value,
            amount=amount,
            slippage_pct=result.slippage_pct,
        )
        
        if result.success:
            logger.info(
                "Paper trade executed (enhanced)",
                token_id=token_id[:20] + "..." if len(token_id) > 20 else token_id,
                side=side.value,
                amount=amount,
                filled_size=result.filled_size,
                avg_price=result.avg_price,
                slippage_pct=result.slippage_pct,
                fee=result.fee,
                latency_ms=result.latency_ms,
            )
        else:
            logger.warning(
                "Paper trade failed",
                token_id=token_id[:20] + "..." if len(token_id) > 20 else token_id,
                error=result.error,
            )
        
        return OrderResult(
            success=result.success,
            order_id=result.order_id,
            filled_size=result.filled_size,
            avg_price=result.avg_price,
            error=result.error,
        )

    async def _simulate_limit_order(
        self,
        token_id: str,
        side: Side,
        price: float,
        size: float,
    ) -> OrderResult:
        """Simulate a limit order for paper trading."""
        from src.monitoring.latency_logger import get_latency_logger
        from src.trading.slippage_simulator import get_simulator
        
        latency_logger = get_latency_logger()
        simulator = get_simulator()
        
        start_time = latency_logger.start_timer()
        
        result = simulator.simulate_limit_order(
            token_id=token_id,
            side=side.value,
            price=price,
            size=size,
        )
        
        await asyncio.sleep(result.latency_ms / 1000)
        
        latency_logger.record(
            operation="limit_order",
            start_time=start_time,
            success=result.success,
            side=side.value,
            price=price,
            size=size,
        )

        logger.info(
            "Paper trade: Limit order simulated (enhanced)",
            token_id=token_id[:20] + "..." if len(token_id) > 20 else token_id,
            side=side.value,
            price=price,
            size=size,
            order_id=result.order_id,
            filled=result.filled_size,
        )

        return OrderResult(
            success=result.success,
            order_id=result.order_id,
            filled_size=result.filled_size,
            avg_price=result.avg_price,
            error=result.error,
        )
