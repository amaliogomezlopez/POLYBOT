"""
The Harvester: Async Mass Data Collection from Polymarket Gamma API.

This module downloads the complete trading history for specified whale accounts
and stores the data in efficient Parquet format.
"""

import asyncio
import aiohttp
import pandas as pd
from pathlib import Path
from datetime import datetime
import time
import structlog

logger = structlog.get_logger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Target whales to analyze
WHALE_LIST = [
    "whaatttt",
    "HaileyWelch", 
    "Account88888",
    "Theo4",
    "SilverLining",
    "Fredi9999",
    "PredictIt_bettor",
]

# API Configuration
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
TRADES_ENDPOINT = f"{GAMMA_API_BASE}/trades"
POSITIONS_ENDPOINT = f"{GAMMA_API_BASE}/positions"

# Rate limiting
REQUESTS_PER_SECOND = 3
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND

# Output directory
DATA_DIR = Path(__file__).parent / "data"


# ============================================================================
# HARVESTER CLASS
# ============================================================================

class WhaleHarvester:
    """Asynchronous data harvester for Polymarket whale accounts."""

    def __init__(self, usernames: list[str] | None = None):
        self.usernames = usernames or WHALE_LIST
        self.session: aiohttp.ClientSession | None = None
        self._last_request_time = 0.0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "WhaleHunter/1.0 Research Bot"}
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def _rate_limit(self):
        """Ensure we don't exceed rate limits."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    async def _fetch_page(
        self,
        endpoint: str,
        params: dict,
        max_retries: int = 3,
    ) -> list[dict]:
        """Fetch a single page of results with retry logic."""
        await self._rate_limit()

        for attempt in range(max_retries):
            try:
                async with self.session.get(endpoint, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data if isinstance(data, list) else []
                    elif resp.status == 429:
                        # Rate limited - back off exponentially
                        wait_time = (2 ** attempt) * 2
                        logger.warning(f"Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"API error {resp.status}: {await resp.text()}")
                        return []
            except Exception as e:
                logger.error(f"Request failed: {e}")
                await asyncio.sleep(1)

        return []

    async def harvest_trades(self, username: str) -> pd.DataFrame:
        """
        Download ALL trades for a given username using pagination.
        
        The Gamma API uses offset-based pagination with a limit of ~100 per page.
        """
        logger.info(f"Harvesting trades for: {username}")
        
        all_trades = []
        offset = 0
        limit = 100
        
        while True:
            params = {
                "user": username,
                "limit": limit,
                "offset": offset,
            }
            
            page = await self._fetch_page(TRADES_ENDPOINT, params)
            
            if not page:
                break
                
            all_trades.extend(page)
            logger.info(f"  [{username}] Fetched {len(page)} trades (total: {len(all_trades)})")
            
            if len(page) < limit:
                # Last page
                break
                
            offset += limit

        if all_trades:
            df = pd.DataFrame(all_trades)
            df["_harvested_at"] = datetime.utcnow().isoformat()
            df["_username"] = username
            return df
        
        return pd.DataFrame()

    async def harvest_positions(self, username: str) -> pd.DataFrame:
        """Download current positions for a user."""
        logger.info(f"Harvesting positions for: {username}")
        
        params = {"user": username, "limit": 500}
        positions = await self._fetch_page(POSITIONS_ENDPOINT, params)
        
        if positions:
            df = pd.DataFrame(positions)
            df["_harvested_at"] = datetime.utcnow().isoformat()
            df["_username"] = username
            return df
        
        return pd.DataFrame()

    async def harvest_all(self) -> dict[str, pd.DataFrame]:
        """Harvest data for all configured whales."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        for username in self.usernames:
            try:
                # Harvest trades
                trades_df = await self.harvest_trades(username)
                
                if not trades_df.empty:
                    output_path = DATA_DIR / f"{username}_trades.parquet"
                    trades_df.to_parquet(output_path, engine="pyarrow", index=False)
                    logger.info(f"Saved {len(trades_df)} trades to {output_path}")
                    results[username] = trades_df
                else:
                    logger.warning(f"No trades found for {username}")
                    
                # Small delay between users
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Failed to harvest {username}: {e}")
                
        return results


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

async def main():
    """Main entry point for the harvester."""
    print("=" * 60)
    print("🐋 WHALE HARVESTER - Polymarket Data Collection")
    print("=" * 60)
    print(f"Targets: {WHALE_LIST}")
    print(f"Output: {DATA_DIR}")
    print()

    async with WhaleHarvester() as harvester:
        results = await harvester.harvest_all()

    print()
    print("=" * 60)
    print("✅ HARVEST COMPLETE")
    print("=" * 60)
    for username, df in results.items():
        print(f"  {username}: {len(df)} trades")


if __name__ == "__main__":
    asyncio.run(main())
