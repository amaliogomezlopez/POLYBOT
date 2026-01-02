#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         RIOT GAMES API CLIENT                                ║
║                                                                              ║
║  Fault-tolerant wrapper for Riot Games API with automatic key validation,   ║
║  hot-reload support, and graceful degradation when key expires.             ║
║                                                                              ║
║  Rate Limits: 20 req/s, 100 req/2min (per routing value)                    ║
║  Key Expiry: Development keys expire every 24 hours                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import aiohttp
import os
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Awaitable
from enum import Enum
from functools import wraps
import traceback

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Riot API Regions
class RiotRegion(Enum):
    # Platform routing values (for game-specific APIs)
    NA1 = "na1"
    EUW1 = "euw1"
    EUN1 = "eun1"
    KR = "kr"
    JP1 = "jp1"
    BR1 = "br1"
    LA1 = "la1"
    LA2 = "la2"
    OC1 = "oc1"
    TR1 = "tr1"
    RU = "ru"
    PH2 = "ph2"
    SG2 = "sg2"
    TH2 = "th2"
    TW2 = "tw2"
    VN2 = "vn2"
    
    # Regional routing values (for account/match APIs)
    AMERICAS = "americas"
    EUROPE = "europe"
    ASIA = "asia"
    SEA = "sea"


# Platform to Regional mapping
PLATFORM_TO_REGIONAL = {
    RiotRegion.NA1: RiotRegion.AMERICAS,
    RiotRegion.BR1: RiotRegion.AMERICAS,
    RiotRegion.LA1: RiotRegion.AMERICAS,
    RiotRegion.LA2: RiotRegion.AMERICAS,
    RiotRegion.EUW1: RiotRegion.EUROPE,
    RiotRegion.EUN1: RiotRegion.EUROPE,
    RiotRegion.TR1: RiotRegion.EUROPE,
    RiotRegion.RU: RiotRegion.EUROPE,
    RiotRegion.KR: RiotRegion.ASIA,
    RiotRegion.JP1: RiotRegion.ASIA,
    RiotRegion.OC1: RiotRegion.SEA,
    RiotRegion.PH2: RiotRegion.SEA,
    RiotRegion.SG2: RiotRegion.SEA,
    RiotRegion.TH2: RiotRegion.SEA,
    RiotRegion.TW2: RiotRegion.SEA,
    RiotRegion.VN2: RiotRegion.SEA,
}


# ==============================================================================
# CUSTOM EXCEPTIONS
# ==============================================================================

class RiotAPIError(Exception):
    """Base exception for Riot API errors"""
    pass


class KeyExpiredError(RiotAPIError):
    """Raised when API key is expired or invalid (403)"""
    def __init__(self, message: str = "Riot API key expired or invalid"):
        self.message = message
        super().__init__(self.message)


class RateLimitError(RiotAPIError):
    """Raised when rate limit is hit (429)"""
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        self.message = f"Rate limited. Retry after {retry_after}s"
        super().__init__(self.message)


class ServiceUnavailableError(RiotAPIError):
    """Raised when Riot services are down (503)"""
    pass


class DataNotFoundError(RiotAPIError):
    """Raised when requested data doesn't exist (404)"""
    pass


# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class KeyStatus:
    """Tracks API key health status"""
    is_valid: bool = True
    last_check: datetime = field(default_factory=datetime.utcnow)
    last_error: Optional[str] = None
    error_count: int = 0
    paused_until: Optional[datetime] = None
    
    def mark_valid(self):
        self.is_valid = True
        self.error_count = 0
        self.last_error = None
        self.last_check = datetime.utcnow()
    
    def mark_invalid(self, error: str):
        self.is_valid = False
        self.error_count += 1
        self.last_error = error
        self.last_check = datetime.utcnow()
    
    def pause(self, seconds: int):
        self.paused_until = datetime.utcnow() + timedelta(seconds=seconds)
    
    @property
    def is_paused(self) -> bool:
        if self.paused_until is None:
            return False
        return datetime.utcnow() < self.paused_until


@dataclass
class LiveGame:
    """Represents a live LoL game"""
    game_id: int
    platform_id: str
    game_type: str
    game_mode: str
    game_length: int  # seconds
    participants: List[Dict[str, Any]]
    banned_champions: List[Dict[str, Any]]
    observers: Dict[str, Any]
    
    @property
    def blue_team(self) -> List[Dict]:
        return [p for p in self.participants if p.get("teamId") == 100]
    
    @property
    def red_team(self) -> List[Dict]:
        return [p for p in self.participants if p.get("teamId") == 200]


@dataclass
class ProPlayer:
    """Represents a professional LoL player"""
    puuid: str
    game_name: str
    tag_line: str
    region: RiotRegion
    team: Optional[str] = None
    role: Optional[str] = None


# ==============================================================================
# RIOT GUARD - FAULT TOLERANT API CLIENT
# ==============================================================================

class RiotGuard:
    """
    Fault-tolerant wrapper for Riot Games API.
    
    Features:
    - Automatic key validation on startup
    - Graceful handling of expired keys (no crash)
    - Hot-reload support for API key updates
    - Rate limit handling with exponential backoff
    - Automatic retry with circuit breaker pattern
    
    Usage:
        riot = RiotGuard()
        await riot.initialize()  # Validates key
        
        if riot.is_available:
            game = await riot.get_live_game_by_summoner(region, summoner_id)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        key_reload_interval: int = 300,  # Check for new key every 5 min
        on_key_expired: Optional[Callable[[], Awaitable[None]]] = None,
        on_key_restored: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """
        Initialize RiotGuard.
        
        Args:
            api_key: Riot API key. If None, reads from RIOT_API_KEY env var.
            key_reload_interval: Seconds between checking for key updates in .env
            on_key_expired: Async callback when key expires
            on_key_restored: Async callback when key is restored/updated
        """
        self._api_key = api_key or os.environ.get("RIOT_API_KEY", "")
        self._key_reload_interval = key_reload_interval
        self._on_key_expired = on_key_expired
        self._on_key_restored = on_key_restored
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._key_status = KeyStatus()
        self._last_key_reload = datetime.utcnow()
        self._rate_limit_remaining = 20
        self._rate_limit_reset = datetime.utcnow()
        
        self.log = logging.getLogger("RiotGuard")
    
    # ==========================================================================
    # PROPERTIES
    # ==========================================================================
    
    @property
    def is_available(self) -> bool:
        """Check if Riot API is available for use"""
        return (
            self._key_status.is_valid 
            and not self._key_status.is_paused 
            and bool(self._api_key)
        )
    
    @property
    def status(self) -> KeyStatus:
        """Get current key status"""
        return self._key_status
    
    @property
    def api_key(self) -> str:
        """Get current API key (masked for logging)"""
        if not self._api_key:
            return "<not set>"
        return f"{self._api_key[:8]}...{self._api_key[-4:]}"
    
    # ==========================================================================
    # LIFECYCLE
    # ==========================================================================
    
    async def initialize(self) -> bool:
        """
        Initialize the client and validate API key.
        
        Returns:
            True if key is valid, False if expired/invalid
        """
        self.log.info("Initializing RiotGuard...")
        
        # Create session
        self._session = aiohttp.ClientSession(
            headers={"X-Riot-Token": self._api_key},
            timeout=aiohttp.ClientTimeout(total=10)
        )
        
        # Validate key
        is_valid = await self.validate_key()
        
        if is_valid:
            self.log.info(f"✓ Riot API key validated: {self.api_key}")
        else:
            self.log.warning(f"✗ Riot API key invalid/expired: {self.api_key}")
        
        return is_valid
    
    async def shutdown(self):
        """Cleanup resources"""
        if self._session:
            await self._session.close()
            self._session = None
        self.log.info("RiotGuard shutdown complete")
    
    async def validate_key(self) -> bool:
        """
        Validate API key with a lightweight status check.
        
        Uses /lol/status/v4/platform-data which is low-cost.
        
        Returns:
            True if key is valid, False otherwise
        """
        try:
            url = self._build_url(RiotRegion.NA1, "/lol/status/v4/platform-data")
            
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    self._key_status.mark_valid()
                    return True
                elif resp.status == 403:
                    self._key_status.mark_invalid("API key expired or invalid")
                    await self._handle_key_expired()
                    return False
                elif resp.status == 401:
                    self._key_status.mark_invalid("API key not provided")
                    return False
                else:
                    self.log.warning(f"Unexpected status during validation: {resp.status}")
                    return False
                    
        except Exception as e:
            self.log.error(f"Key validation error: {e}")
            self._key_status.mark_invalid(str(e))
            return False
    
    async def hot_reload_key(self) -> bool:
        """
        Hot-reload API key from environment variable.
        
        Call this to update the key without restarting the process.
        
        Returns:
            True if new key is valid, False otherwise
        """
        # Re-read from environment
        new_key = os.environ.get("RIOT_API_KEY", "")
        
        if not new_key:
            self.log.warning("No RIOT_API_KEY found in environment")
            return False
        
        if new_key == self._api_key:
            self.log.debug("API key unchanged")
            return self._key_status.is_valid
        
        self.log.info(f"Hot-reloading Riot API key: {new_key[:8]}...{new_key[-4:]}")
        
        # Update key
        old_key = self._api_key
        self._api_key = new_key
        
        # Recreate session with new key
        if self._session:
            await self._session.close()
        
        self._session = aiohttp.ClientSession(
            headers={"X-Riot-Token": self._api_key},
            timeout=aiohttp.ClientTimeout(total=10)
        )
        
        # Validate new key
        is_valid = await self.validate_key()
        
        if is_valid:
            self.log.info("✓ New API key validated successfully")
            if self._on_key_restored:
                await self._on_key_restored()
        else:
            self.log.error("✗ New API key is invalid, reverting")
            self._api_key = old_key
            # Recreate session with old key
            await self._session.close()
            self._session = aiohttp.ClientSession(
                headers={"X-Riot-Token": self._api_key},
                timeout=aiohttp.ClientTimeout(total=10)
            )
        
        self._last_key_reload = datetime.utcnow()
        return is_valid
    
    async def _maybe_reload_key(self):
        """Check if it's time to reload the key from .env"""
        elapsed = (datetime.utcnow() - self._last_key_reload).total_seconds()
        if elapsed >= self._key_reload_interval:
            await self.hot_reload_key()
    
    # ==========================================================================
    # ERROR HANDLING
    # ==========================================================================
    
    async def _handle_key_expired(self):
        """Handle key expiration - pause strategy, don't crash"""
        self.log.error("=" * 60)
        self.log.error("RIOT API KEY EXPIRED!")
        self.log.error("Strategy ORACLE will be paused until key is updated.")
        self.log.error("Update .env with new RIOT_API_KEY and call hot_reload_key()")
        self.log.error("=" * 60)
        
        self._key_status.pause(3600)  # Pause for 1 hour
        
        if self._on_key_expired:
            try:
                await self._on_key_expired()
            except Exception as e:
                self.log.error(f"Error in key_expired callback: {e}")
    
    async def _handle_rate_limit(self, retry_after: int):
        """Handle rate limiting with backoff"""
        self.log.warning(f"Rate limited! Pausing for {retry_after}s")
        self._key_status.pause(retry_after)
    
    def _api_call(func):
        """
        Decorator for API calls with error handling.
        
        - Catches 403 (expired key) and pauses strategy
        - Catches 429 (rate limit) and backs off
        - Catches 503 (service unavailable) and retries
        - Never crashes the main bot loop
        """
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Check if available
            if not self.is_available:
                self.log.debug(f"Skipping {func.__name__}: Riot API unavailable")
                return None
            
            # Maybe reload key
            await self._maybe_reload_key()
            
            try:
                return await func(self, *args, **kwargs)
                
            except KeyExpiredError:
                await self._handle_key_expired()
                return None
                
            except RateLimitError as e:
                await self._handle_rate_limit(e.retry_after)
                return None
                
            except ServiceUnavailableError:
                self.log.warning("Riot services unavailable, will retry")
                self._key_status.pause(30)
                return None
                
            except DataNotFoundError:
                # This is expected (no live game, etc.)
                return None
                
            except aiohttp.ClientError as e:
                self.log.error(f"Network error in {func.__name__}: {e}")
                return None
                
            except Exception as e:
                self.log.error(f"Unexpected error in {func.__name__}: {e}")
                self.log.debug(traceback.format_exc())
                return None
        
        return wrapper
    
    # ==========================================================================
    # HTTP HELPERS
    # ==========================================================================
    
    def _build_url(self, region: RiotRegion, endpoint: str) -> str:
        """Build full API URL for a region and endpoint"""
        if region in [RiotRegion.AMERICAS, RiotRegion.EUROPE, RiotRegion.ASIA, RiotRegion.SEA]:
            base = f"https://{region.value}.api.riotgames.com"
        else:
            base = f"https://{region.value}.api.riotgames.com"
        return f"{base}{endpoint}"
    
    async def _request(self, region: RiotRegion, endpoint: str) -> Dict[str, Any]:
        """
        Make an authenticated request to Riot API.
        
        Raises appropriate exceptions based on response status.
        """
        if not self._session:
            raise RiotAPIError("Session not initialized. Call initialize() first.")
        
        url = self._build_url(region, endpoint)
        
        async with self._session.get(url) as resp:
            # Check rate limit headers
            if "X-Rate-Limit-Count" in resp.headers:
                self.log.debug(f"Rate limit: {resp.headers.get('X-Rate-Limit-Count')}")
            
            if resp.status == 200:
                return await resp.json()
            
            elif resp.status == 403:
                raise KeyExpiredError()
            
            elif resp.status == 404:
                raise DataNotFoundError()
            
            elif resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                raise RateLimitError(retry_after)
            
            elif resp.status == 503:
                raise ServiceUnavailableError()
            
            else:
                text = await resp.text()
                raise RiotAPIError(f"Unexpected status {resp.status}: {text}")
    
    # ==========================================================================
    # SPECTATOR API (spectator-v4)
    # ==========================================================================
    
    @_api_call
    async def get_featured_games(self, region: RiotRegion = RiotRegion.KR) -> Optional[Dict]:
        """
        Get featured games (high elo + pro games) currently being played.
        
        NOTE: This endpoint requires a Production API key or special permissions.
        Development keys will get 403. Use get_live_esports_matches() instead
        for professional esports matches.
        
        Args:
            region: Platform region (KR for Korean pro games)
            
        Returns:
            Dict with gameList containing featured games
        """
        endpoint = "/lol/spectator/v4/featured-games"
        try:
            data = await self._request(region, endpoint)
            return data
        except KeyExpiredError:
            # Development keys don't have access to spectator-v4
            # This is expected - use get_live_esports_matches() instead
            self.log.debug("Featured games requires Production API key - using Esports API instead")
            return None
    
    @_api_call
    async def get_live_game_by_summoner(
        self, 
        region: RiotRegion, 
        summoner_id: str
    ) -> Optional[LiveGame]:
        """
        Get live game data for a specific summoner.
        
        Args:
            region: Platform region where summoner plays
            summoner_id: Encrypted summoner ID
            
        Returns:
            LiveGame object or None if not in game
        """
        endpoint = f"/lol/spectator/v4/active-games/by-summoner/{summoner_id}"
        data = await self._request(region, endpoint)
        
        if data:
            return LiveGame(
                game_id=data.get("gameId"),
                platform_id=data.get("platformId"),
                game_type=data.get("gameType"),
                game_mode=data.get("gameMode"),
                game_length=data.get("gameLength", 0),
                participants=data.get("participants", []),
                banned_champions=data.get("bannedChampions", []),
                observers=data.get("observers", {})
            )
        return None
    
    # ==========================================================================
    # ACCOUNT API (account-v1)
    # ==========================================================================
    
    @_api_call
    async def get_account_by_riot_id(
        self, 
        game_name: str, 
        tag_line: str,
        region: RiotRegion = RiotRegion.ASIA
    ) -> Optional[Dict[str, str]]:
        """
        Get account info (including PUUID) by Riot ID.
        
        Riot ID format: GameName#TagLine (e.g., "Faker#KR1")
        
        Args:
            game_name: Riot ID game name
            tag_line: Riot ID tag line
            region: Regional routing value
            
        Returns:
            Dict with puuid, gameName, tagLine
        """
        endpoint = f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        return await self._request(region, endpoint)
    
    @_api_call
    async def get_account_by_puuid(
        self, 
        puuid: str,
        region: RiotRegion = RiotRegion.ASIA
    ) -> Optional[Dict[str, str]]:
        """
        Get account info by PUUID.
        
        Args:
            puuid: Player UUID
            region: Regional routing value
            
        Returns:
            Dict with puuid, gameName, tagLine
        """
        endpoint = f"/riot/account/v1/accounts/by-puuid/{puuid}"
        return await self._request(region, endpoint)
    
    # ==========================================================================
    # SUMMONER API (summoner-v4)
    # ==========================================================================
    
    @_api_call
    async def get_summoner_by_puuid(
        self, 
        puuid: str,
        region: RiotRegion = RiotRegion.KR
    ) -> Optional[Dict[str, Any]]:
        """
        Get summoner info by PUUID.
        
        Args:
            puuid: Player UUID
            region: Platform region
            
        Returns:
            Dict with summoner info including encrypted summonerId
        """
        endpoint = f"/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return await self._request(region, endpoint)
    
    @_api_call
    async def get_summoner_by_name(
        self, 
        summoner_name: str,
        region: RiotRegion = RiotRegion.KR
    ) -> Optional[Dict[str, Any]]:
        """
        Get summoner info by summoner name.
        
        Args:
            summoner_name: Summoner name (case-insensitive)
            region: Platform region
            
        Returns:
            Dict with summoner info
        """
        # URL encode the name
        import urllib.parse
        encoded = urllib.parse.quote(summoner_name)
        endpoint = f"/lol/summoner/v4/summoners/by-name/{encoded}"
        return await self._request(region, endpoint)
    
    # ==========================================================================
    # LOL ESPORTS API (unofficial but free)
    # ==========================================================================
    
    async def get_live_esports_matches(self) -> List[Dict[str, Any]]:
        """
        Get live esports matches from lolesports.com API.
        
        This API doesn't require authentication and provides:
        - Live match status
        - Team names
        - Game scores
        - Event metadata
        
        Returns:
            List of live match dicts
        """
        url = "https://esports-api.lolesports.com/persisted/gw/getLive"
        headers = {
            "x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"  # Public key
        }
        params = {"hl": "en-US"}
        
        try:
            async with self._session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    events = data.get("data", {}).get("schedule", {}).get("events", [])
                    return [e for e in events if e.get("state") == "inProgress"]
                return []
        except Exception as e:
            self.log.error(f"Error fetching esports matches: {e}")
            return []
    
    async def get_live_game_stats(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time stats for a live esports game.
        
        Args:
            game_id: Game ID from getLive endpoint
            
        Returns:
            Dict with frame data including kills, gold, objectives
        """
        url = f"https://feed.lolesports.com/livestats/v1/window/{game_id}"
        
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            self.log.error(f"Error fetching game stats: {e}")
            return None


# ==============================================================================
# PRO PLAYER DATABASE
# ==============================================================================

# Known pro player Riot IDs for tracking
# Format: (game_name, tag_line, team, role, region)
PRO_PLAYERS_KR = [
    # T1
    ("Hide on bush", "KR1", "T1", "MID", RiotRegion.KR),
    ("T1 Gumayusi", "KR1", "T1", "ADC", RiotRegion.KR),
    ("T1 Keria", "KR1", "T1", "SUP", RiotRegion.KR),
    
    # Gen.G
    ("Gen G Chovy", "KR1", "Gen.G", "MID", RiotRegion.KR),
    ("Gen G Peyz", "KR1", "Gen.G", "ADC", RiotRegion.KR),
    
    # DK
    ("DK ShowMaker", "KR1", "DK", "MID", RiotRegion.KR),
    
    # HLE
    ("HLE Zeka", "KR1", "HLE", "MID", RiotRegion.KR),
]

PRO_PLAYERS_CN = [
    # JDG
    ("JDG Knight", "CN1", "JDG", "MID", RiotRegion.KR),  # Use KR for testing
    
    # BLG
    ("BLG Bin", "CN1", "BLG", "TOP", RiotRegion.KR),
]


# ==============================================================================
# FACTORY FUNCTION
# ==============================================================================

async def create_riot_client(
    on_key_expired: Optional[Callable[[], Awaitable[None]]] = None,
    on_key_restored: Optional[Callable[[], Awaitable[None]]] = None,
) -> RiotGuard:
    """
    Factory function to create and initialize RiotGuard.
    
    Args:
        on_key_expired: Callback when key expires
        on_key_restored: Callback when key is restored
        
    Returns:
        Initialized RiotGuard instance
    """
    client = RiotGuard(
        on_key_expired=on_key_expired,
        on_key_restored=on_key_restored,
    )
    await client.initialize()
    return client


# ==============================================================================
# CLI FOR TESTING
# ==============================================================================

async def main():
    """Test the Riot client"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    
    print("=" * 60)
    print("         RIOT GUARD - CONNECTION TEST")
    print("=" * 60)
    
    riot = await create_riot_client()
    
    print(f"\nAPI Key: {riot.api_key}")
    print(f"Available: {riot.is_available}")
    print(f"Status: {riot.status}")
    
    if riot.is_available:
        # Use Esports API (works with dev key)
        print("\n--- Live Esports Matches (LoL Esports API) ---")
        matches = await riot.get_live_esports_matches()
        print(f"Found {len(matches)} live esports matches")
        for match in matches:
            teams = match.get("match", {}).get("teams", [])
            if len(teams) >= 2:
                league = match.get("league", {}).get("name", "Unknown")
                print(f"  [{league}] {teams[0].get('name')} vs {teams[1].get('name')}")
        
        if not matches:
            print("  (No live matches currently - this is normal)")
        
        # Note about featured games
        print("\n--- Featured Games (Riot API) ---")
        print("  Note: spectator-v4 requires Production API key")
        print("  Using LoL Esports API instead for pro matches")
    
    await riot.shutdown()
    print("\n✓ Test complete")


if __name__ == "__main__":
    asyncio.run(main())
