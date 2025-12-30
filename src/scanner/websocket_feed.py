"""WebSocket feed for real-time market data."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from src.config.constants import (
    WS_PING_INTERVAL_SECONDS,
    WS_PING_TIMEOUT_SECONDS,
    WS_RECONNECT_DELAY_SECONDS,
)

logger = structlog.get_logger(__name__)

# Polymarket WebSocket endpoint
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


@dataclass
class OrderbookSnapshot:
    """Local orderbook snapshot."""

    token_id: str
    bids: list[tuple[float, float]] = field(default_factory=list)  # (price, size)
    asks: list[tuple[float, float]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def best_bid(self) -> float | None:
        """Best bid price."""
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> float | None:
        """Best ask price."""
        return self.asks[0][0] if self.asks else None

    @property
    def mid_price(self) -> float | None:
        """Mid price between best bid and ask."""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None


class WebSocketFeed:
    """
    Real-time WebSocket feed for Polymarket orderbook updates.
    
    Provides streaming price updates for subscribed markets.
    """

    def __init__(self) -> None:
        """Initialize WebSocket feed."""
        self._ws: Any | None = None
        self._subscriptions: set[str] = set()
        self._orderbooks: dict[str, OrderbookSnapshot] = {}
        self._callbacks: list[Callable[[str, OrderbookSnapshot], None]] = []
        self._running = False
        self._reconnect_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        try:
            self._ws = await websockets.connect(
                WS_URL,
                ping_interval=WS_PING_INTERVAL_SECONDS,
                ping_timeout=WS_PING_TIMEOUT_SECONDS,
            )
            self._running = True
            logger.info("WebSocket connected", url=WS_URL)

            # Resubscribe to previously subscribed markets
            for token_id in self._subscriptions:
                await self._send_subscribe(token_id)

        except Exception as e:
            logger.error("WebSocket connection failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("WebSocket disconnected")

    async def subscribe(self, token_id: str) -> None:
        """
        Subscribe to orderbook updates for a token.

        Args:
            token_id: Token ID to subscribe to.
        """
        self._subscriptions.add(token_id)
        if self._ws:
            await self._send_subscribe(token_id)

    async def unsubscribe(self, token_id: str) -> None:
        """
        Unsubscribe from orderbook updates for a token.

        Args:
            token_id: Token ID to unsubscribe from.
        """
        self._subscriptions.discard(token_id)
        if self._ws:
            await self._send_unsubscribe(token_id)

    async def _send_subscribe(self, token_id: str) -> None:
        """Send subscription message."""
        if not self._ws:
            return

        message = {
            "type": "subscribe",
            "channel": "book",
            "market": token_id,
        }
        await self._ws.send(json.dumps(message))
        logger.debug("Subscribed to token", token_id=token_id)

    async def _send_unsubscribe(self, token_id: str) -> None:
        """Send unsubscription message."""
        if not self._ws:
            return

        message = {
            "type": "unsubscribe",
            "channel": "book",
            "market": token_id,
        }
        await self._ws.send(json.dumps(message))
        logger.debug("Unsubscribed from token", token_id=token_id)

    def add_callback(self, callback: Callable[[str, OrderbookSnapshot], None]) -> None:
        """
        Add a callback for orderbook updates.

        Args:
            callback: Function called with (token_id, orderbook) on updates.
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[str, OrderbookSnapshot], None]) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_orderbook(self, token_id: str) -> OrderbookSnapshot | None:
        """Get cached orderbook for a token."""
        return self._orderbooks.get(token_id)

    def get_mid_price(self, token_id: str) -> float | None:
        """Get mid price for a token."""
        orderbook = self._orderbooks.get(token_id)
        return orderbook.mid_price if orderbook else None

    async def run(self) -> None:
        """Run the WebSocket feed (blocking)."""
        while self._running:
            try:
                if not self._ws:
                    await self.connect()

                await self._process_messages()

            except ConnectionClosed as e:
                logger.warning("WebSocket connection closed", code=e.code, reason=e.reason)
                await self._handle_reconnect()

            except Exception as e:
                logger.error("WebSocket error", error=str(e))
                await self._handle_reconnect()

    async def _process_messages(self) -> None:
        """Process incoming WebSocket messages."""
        if not self._ws:
            return

        async for message in self._ws:
            try:
                data = json.loads(message)
                await self._handle_message(data)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON message", message=message[:100])
            except Exception as e:
                logger.error("Message processing error", error=str(e))

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle a parsed WebSocket message."""
        msg_type = data.get("type", "")

        if msg_type == "book":
            await self._handle_book_update(data)
        elif msg_type == "price_change":
            await self._handle_price_change(data)
        elif msg_type == "subscribed":
            logger.debug("Subscription confirmed", market=data.get("market"))
        elif msg_type == "error":
            logger.error("WebSocket error message", error=data.get("message"))

    async def _handle_book_update(self, data: dict[str, Any]) -> None:
        """Handle orderbook update message."""
        token_id = data.get("market", "")
        if not token_id:
            return

        # Parse bids and asks
        bids = []
        asks = []

        for bid in data.get("bids", []):
            try:
                price = float(bid.get("price", 0))
                size = float(bid.get("size", 0))
                if price > 0 and size > 0:
                    bids.append((price, size))
            except (ValueError, TypeError):
                continue

        for ask in data.get("asks", []):
            try:
                price = float(ask.get("price", 0))
                size = float(ask.get("size", 0))
                if price > 0 and size > 0:
                    asks.append((price, size))
            except (ValueError, TypeError):
                continue

        # Sort: bids descending, asks ascending
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        # Update orderbook
        orderbook = OrderbookSnapshot(
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(),
        )
        self._orderbooks[token_id] = orderbook

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(token_id, orderbook)
            except Exception as e:
                logger.error("Callback error", error=str(e))

    async def _handle_price_change(self, data: dict[str, Any]) -> None:
        """Handle price change message."""
        # Price change messages are simpler updates
        token_id = data.get("market", "")
        if not token_id or token_id not in self._orderbooks:
            return

        # Update with new price data if available
        orderbook = self._orderbooks[token_id]
        orderbook.timestamp = datetime.now()

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(token_id, orderbook)
            except Exception as e:
                logger.error("Callback error", error=str(e))

    async def _handle_reconnect(self) -> None:
        """Handle reconnection with backoff."""
        self._ws = None
        if not self._running:
            return

        logger.info(
            "Attempting reconnection",
            delay_seconds=WS_RECONNECT_DELAY_SECONDS,
        )
        await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)

    async def __aenter__(self) -> "WebSocketFeed":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()
