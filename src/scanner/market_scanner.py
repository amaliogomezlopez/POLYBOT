"""Market scanner for discovering and filtering 15-minute flash markets."""

import asyncio
import re
from datetime import datetime
from typing import Any

import httpx
import structlog

from src.config.constants import (
    CLOB_HOST,
    FLASH_MARKET_KEYWORDS,
    GAMMA_API_HOST,
    TARGET_ASSETS,
    MarketType,
)
from src.models import Market, TokenPair

logger = structlog.get_logger(__name__)


class MarketScanner:
    """Scans and filters Polymarket markets for flash arbitrage opportunities."""

    def __init__(self, client: Any | None = None) -> None:
        """
        Initialize market scanner.

        Args:
            client: Optional py-clob-client instance for authenticated requests.
        """
        self.client = client
        self._http_client: httpx.AsyncClient | None = None
        self._market_cache: dict[str, Market] = {}
        self._last_scan: datetime | None = None

    async def __aenter__(self) -> "MarketScanner":
        """Async context manager entry."""
        self._http_client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._http_client:
            await self._http_client.aclose()

    async def get_all_markets(self) -> list[dict[str, Any]]:
        """
        Fetch all active markets from Gamma API.

        Returns:
            List of market data dictionaries.
        """
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        markets: list[dict[str, Any]] = []
        next_cursor = None

        try:
            while True:
                url = f"{GAMMA_API_HOST}/markets"
                params: dict[str, Any] = {"active": "true", "limit": 100}
                if next_cursor:
                    params["cursor"] = next_cursor

                response = await self._http_client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                markets.extend(data.get("data", data) if isinstance(data, dict) else data)

                # Check for pagination
                next_cursor = data.get("next_cursor") if isinstance(data, dict) else None
                if not next_cursor:
                    break

            logger.info("Fetched markets from Gamma API", count=len(markets))
            return markets

        except httpx.HTTPError as e:
            logger.error("Failed to fetch markets", error=str(e))
            return []

    def is_flash_market(self, market_data: dict[str, Any]) -> bool:
        """
        Check if a market is a 15-minute flash market.

        Args:
            market_data: Raw market data from API.

        Returns:
            True if market is a flash market.
        """
        question = market_data.get("question", "").lower()
        description = market_data.get("description", "").lower()
        tags = [t.lower() for t in market_data.get("tags", [])]

        # Check for flash market keywords
        text_to_check = f"{question} {description}"
        for keyword in FLASH_MARKET_KEYWORDS:
            if keyword in text_to_check:
                return True

        # Check tags
        flash_tags = {"flash", "15min", "15-minute", "crypto"}
        if flash_tags.intersection(tags):
            return True

        return False

    def extract_asset(self, market_data: dict[str, Any]) -> str | None:
        """
        Extract the crypto asset from market data.

        Args:
            market_data: Raw market data from API.

        Returns:
            Asset symbol (BTC, ETH, SOL) or None.
        """
        question = market_data.get("question", "").upper()

        for asset in TARGET_ASSETS:
            # Match asset with word boundaries
            pattern = rf"\b{asset}\b"
            if re.search(pattern, question):
                return asset

        return None

    def parse_market(self, market_data: dict[str, Any]) -> Market | None:
        """
        Parse raw market data into a Market object.

        Args:
            market_data: Raw market data from API.

        Returns:
            Market object or None if parsing fails.
        """
        try:
            market_id = market_data.get("id") or market_data.get("condition_id", "")
            condition_id = market_data.get("condition_id", market_id)

            if not market_id:
                return None

            # Parse timestamps
            end_time = None
            end_date_str = market_data.get("end_date_iso") or market_data.get("endDate")
            if end_date_str:
                try:
                    end_time = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            # Determine market type
            market_type = MarketType.FLASH_15MIN if self.is_flash_market(market_data) else MarketType.CUSTOM

            # Extract tokens
            tokens = None
            outcomes = market_data.get("outcomes", [])
            clob_token_ids = market_data.get("clobTokenIds", [])

            if len(outcomes) == 2 and len(clob_token_ids) == 2:
                # Determine which is UP and which is DOWN
                up_idx = 0
                down_idx = 1
                for i, outcome in enumerate(outcomes):
                    outcome_lower = outcome.lower()
                    if "up" in outcome_lower or "yes" in outcome_lower or "higher" in outcome_lower:
                        up_idx = i
                        down_idx = 1 - i
                        break
                    elif "down" in outcome_lower or "no" in outcome_lower or "lower" in outcome_lower:
                        down_idx = i
                        up_idx = 1 - i
                        break

                tokens = TokenPair(
                    up_token_id=clob_token_ids[up_idx],
                    down_token_id=clob_token_ids[down_idx],
                )

            market = Market(
                id=market_id,
                condition_id=condition_id,
                question=market_data.get("question", ""),
                slug=market_data.get("slug", ""),
                market_type=market_type,
                asset=self.extract_asset(market_data),
                tokens=tokens,
                end_time=end_time,
                volume=float(market_data.get("volume", 0) or 0),
                is_active=market_data.get("active", True),
                raw_data=market_data,
            )

            return market

        except Exception as e:
            logger.warning("Failed to parse market", error=str(e), market_id=market_data.get("id"))
            return None

    async def scan_flash_markets(self) -> list[Market]:
        """
        Scan for all active flash markets.

        Returns:
            List of flash markets suitable for arbitrage.
        """
        all_markets = await self.get_all_markets()
        flash_markets: list[Market] = []

        for market_data in all_markets:
            # Filter for flash markets
            if not self.is_flash_market(market_data):
                continue

            market = self.parse_market(market_data)
            if not market:
                continue

            # Must have tokens for trading
            if not market.tokens:
                continue

            # Skip closed markets
            if market.is_closed:
                continue

            # Must be a crypto asset we track
            if market.asset not in TARGET_ASSETS:
                continue

            flash_markets.append(market)
            self._market_cache[market.id] = market

        self._last_scan = datetime.now()
        logger.info(
            "Flash market scan complete",
            total_scanned=len(all_markets),
            flash_markets=len(flash_markets),
        )

        return flash_markets

    async def get_market_prices(self, market: Market) -> TokenPair | None:
        """
        Get current prices for a market's tokens.

        Args:
            market: Market to get prices for.

        Returns:
            Updated TokenPair with prices, or None on error.
        """
        if not market.tokens:
            return None

        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        try:
            # Fetch prices from CLOB
            up_url = f"{CLOB_HOST}/price"
            tasks = [
                self._http_client.get(up_url, params={"token_id": market.tokens.up_token_id, "side": "BUY"}),
                self._http_client.get(up_url, params={"token_id": market.tokens.down_token_id, "side": "BUY"}),
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            up_price = 0.0
            down_price = 0.0

            for i, resp in enumerate(responses):
                if isinstance(resp, Exception):
                    logger.warning("Price fetch failed", error=str(resp))
                    continue
                if resp.status_code == 200:
                    data = resp.json()
                    price = float(data.get("price", 0))
                    if i == 0:
                        up_price = price
                    else:
                        down_price = price

            market.tokens.up_price = up_price
            market.tokens.down_price = down_price

            return market.tokens

        except Exception as e:
            logger.error("Failed to get market prices", error=str(e), market_id=market.id)
            return None

    async def get_orderbook(self, token_id: str) -> dict[str, Any]:
        """
        Get orderbook for a token.

        Args:
            token_id: Token ID to get orderbook for.

        Returns:
            Orderbook data with bids and asks.
        """
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        try:
            url = f"{CLOB_HOST}/book"
            response = await self._http_client.get(url, params={"token_id": token_id})
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error("Failed to get orderbook", error=str(e), token_id=token_id)
            return {"bids": [], "asks": []}

    def get_cached_market(self, market_id: str) -> Market | None:
        """Get a market from cache."""
        return self._market_cache.get(market_id)

    def clear_cache(self) -> None:
        """Clear the market cache."""
        self._market_cache.clear()
