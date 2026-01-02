"""
The Harvester: Async Mass Data Collection from Polymarket Data API.

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

# Target whales to analyze - using wallet addresses from Polymarket profiles
# Format: {display_name: wallet_address}
WHALE_LIST = {
    "Account88888": "0x7f69983eb28245bba0d5083502a78744a8f66162",
}

# API Configuration - using data-api (same as browser network calls)
GAMMA_API_BASE = "https://data-api.polymarket.com"

# Rate limiting
REQUESTS_PER_SECOND = 2
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND

# Output directory
DATA_DIR = Path(__file__).parent / "data"


# ============================================================================
# HARVESTER CLASS
# ============================================================================

class WhaleHarvester:
    """Asynchronous data harvester for Polymarket whale accounts."""

    def __init__(self, whales: dict[str, str] | None = None):
        self.whales = whales or WHALE_LIST
        self.session: aiohttp.ClientSession | None = None
        self._last_request_time = 0.0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 WhaleHunter/1.0"}
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
                        wait_time = (2 ** attempt) * 2
                        logger.warning(f"Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        text = await resp.text()
                        logger.error(f"API error {resp.status}: {text[:200]}")
                        return []
            except Exception as e:
                logger.error(f"Request failed: {e}")
                await asyncio.sleep(1)

        return []

    async def harvest_activity(self, name: str, wallet: str) -> pd.DataFrame:
        """
        Download ALL activity (trades) for a given wallet using pagination.
        Uses data-api.polymarket.com/activity endpoint.
        """
        logger.info(f"Harvesting activity for: {name} ({wallet[:10]}...)")
        
        all_activity = []
        offset = 0
        limit = 25  # API typically returns 25 per page
        
        while True:
            params = {
                "user": wallet,
                "limit": limit,
                "offset": offset,
            }
            
            endpoint = f"{GAMMA_API_BASE}/activity"
            page = await self._fetch_page(endpoint, params)
            
            if not page:
                break
                
            all_activity.extend(page)
            logger.info(f"  [{name}] Fetched {len(page)} records (total: {len(all_activity)})")
            
            if len(page) < limit:
                break
                
            offset += limit
            
            # Safety limit to avoid infinite loops
            if offset > 5000:
                logger.warning(f"  [{name}] Reached safety limit at {offset}")
                break

        if all_activity:
            df = pd.DataFrame(all_activity)
            df["_harvested_at"] = datetime.utcnow().isoformat()
            df["_display_name"] = name
            df["_wallet"] = wallet
            return df
        
        return pd.DataFrame()

    async def harvest_positions(self, name: str, wallet: str) -> pd.DataFrame:
        """Download current positions for a wallet."""
        logger.info(f"Harvesting positions for: {name}")
        
        params = {
            "user": wallet,
            "sortby": "current",
            "sortdirection": "desc",
            "sizethreshold": ".1",
            "limit": 100,
            "offset": 0,
        }
        
        endpoint = f"{GAMMA_API_BASE}/positions"
        positions = await self._fetch_page(endpoint, params)
        
        if positions:
            df = pd.DataFrame(positions)
            df["_harvested_at"] = datetime.utcnow().isoformat()
            df["_display_name"] = name
            df["_wallet"] = wallet
            return df
        
        return pd.DataFrame()

    async def harvest_all(self) -> dict[str, dict[str, pd.DataFrame]]:
        """Harvest data for all configured whales."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        for name, wallet in self.whales.items():
            try:
                # Harvest activity (trades)
                activity_df = await self.harvest_activity(name, wallet)
                
                # Harvest positions
                positions_df = await self.harvest_positions(name, wallet)
                
                if not activity_df.empty:
                    output_path = DATA_DIR / f"{name}_activity.parquet"
                    activity_df.to_parquet(output_path, engine="pyarrow", index=False)
                    logger.info(f"Saved {len(activity_df)} activity records to {output_path}")
                
                if not positions_df.empty:
                    output_path = DATA_DIR / f"{name}_positions.parquet"
                    positions_df.to_parquet(output_path, engine="pyarrow", index=False)
                    logger.info(f"Saved {len(positions_df)} positions to {output_path}")
                
                results[name] = {
                    "activity": activity_df,
                    "positions": positions_df,
                }
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to harvest {name}: {e}")
                import traceback
                traceback.print_exc()
                
        return results


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

async def main():
    """Main entry point for the harvester."""
    print("=" * 60)
    print("🐋 WHALE HARVESTER - Polymarket Data Collection")
    print("=" * 60)
    print(f"Targets: {list(WHALE_LIST.keys())}")
    print(f"Output: {DATA_DIR}")
    print()

    async with WhaleHarvester() as harvester:
        results = await harvester.harvest_all()

    print()
    print("=" * 60)
    print("✅ HARVEST COMPLETE")
    print("=" * 60)
    for name, data in results.items():
        activity_count = len(data.get("activity", []))
        positions_count = len(data.get("positions", []))
        print(f"  {name}: {activity_count} trades, {positions_count} positions")


if __name__ == "__main__":
    asyncio.run(main())
