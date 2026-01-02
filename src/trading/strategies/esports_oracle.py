#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                      ESPORTS ORACLE STRATEGY (ORACLE)                        ║
║                                                                              ║
║  Exploits Twitch stream delay (~30-60s) by using Riot's real-time APIs      ║
║  to detect game-ending events before stream viewers can react.               ║
║                                                                              ║
║  Target Events:                                                              ║
║  - Game End (Nexus destroyed) → Critical                                     ║
║  - Baron/Dragon → High impact                                                ║
║  - Ace (5 kills) → High impact                                               ║
║                                                                              ║
║  Edge Window: ~35 seconds                                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import aiohttp
import os
import re
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from difflib import SequenceMatcher
from enum import Enum

# Import our fault-tolerant Riot client
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from src.exchanges.riot_client import (
        RiotGuard, 
        RiotRegion, 
        KeyExpiredError,
        create_riot_client
    )
except ImportError:
    # Fallback for direct execution
    from exchanges.riot_client import (
        RiotGuard, 
        RiotRegion, 
        KeyExpiredError,
        create_riot_client
    )


# ==============================================================================
# CONFIGURATION
# ==============================================================================

POLYMARKET_API = "https://gamma-api.polymarket.com"

# Strategy parameters
POLLING_INTERVAL = 2.0  # seconds between checks
MIN_EDGE_THRESHOLD = 0.05  # 5% minimum edge to trade
MAX_STAKE_USDC = 25.0  # Maximum stake per trade
MIN_LIQUIDITY = 500.0  # Minimum market liquidity

# Fuzzy matching threshold
FUZZY_MATCH_THRESHOLD = 0.65


# ==============================================================================
# DATA MODELS
# ==============================================================================

class GameEvent(Enum):
    """Significant in-game events"""
    GAME_START = "game_start"
    FIRST_BLOOD = "first_blood"
    TOWER_DESTROYED = "tower_destroyed"
    DRAGON_TAKEN = "dragon_taken"
    BARON_TAKEN = "baron_taken"
    ACE = "ace"
    INHIBITOR_DESTROYED = "inhibitor_destroyed"
    GAME_END = "game_end"


class StrategyState(Enum):
    """Oracle strategy states"""
    IDLE = "idle"  # No active matches
    MONITORING = "monitoring"  # Watching live match
    SIGNAL_PENDING = "signal_pending"  # Signal generated, awaiting execution
    PAUSED = "paused"  # API key expired or error
    DISABLED = "disabled"  # Manually disabled


@dataclass
class LiveMatch:
    """Represents a live esports match"""
    match_id: str
    event_id: str
    league: str
    team_blue: str
    team_red: str
    score_blue: int
    score_red: int
    best_of: int
    current_game_id: Optional[str] = None
    game_state: Optional[Dict[str, Any]] = None
    last_update: datetime = field(default_factory=datetime.utcnow)


@dataclass  
class GameState:
    """Snapshot of current game state"""
    game_id: str
    game_time_seconds: int
    blue_kills: int
    red_kills: int
    blue_towers: int
    red_towers: int
    blue_dragons: int
    red_dragons: int
    blue_barons: int
    red_barons: int
    blue_gold: int
    red_gold: int
    game_over: bool = False
    winner: Optional[str] = None  # "blue" or "red"
    
    @property
    def gold_diff(self) -> int:
        """Blue team gold advantage"""
        return self.blue_gold - self.red_gold
    
    @property
    def kill_diff(self) -> int:
        """Blue team kill advantage"""
        return self.blue_kills - self.red_kills


@dataclass
class OracleSignal:
    """Trading signal from Oracle strategy"""
    signal_id: str
    strategy: str = "ORACLE"
    match_id: str = ""
    event_type: GameEvent = GameEvent.GAME_END
    match_description: str = ""
    team_blue: str = ""
    team_red: str = ""
    detected_winner: str = ""  # "blue" or "red"
    
    # Polymarket data
    market_question: str = ""
    market_condition_id: str = ""
    recommended_side: str = ""  # "YES" or "NO"
    token_id: str = ""
    
    # Pricing
    current_price: float = 0.0
    expected_price: float = 0.0
    edge: float = 0.0
    
    # Execution
    stake_usdc: float = 0.0
    confidence: float = 0.0
    
    # Timing
    api_timestamp: datetime = field(default_factory=datetime.utcnow)
    estimated_stream_time: datetime = field(default_factory=datetime.utcnow)
    window_seconds: float = 35.0


@dataclass
class PolymarketMatch:
    """Polymarket esports market"""
    condition_id: str
    question: str
    team1_outcome: str = ""
    team2_outcome: str = ""
    team1_token_id: str = ""
    team2_token_id: str = ""
    team1_price: float = 0.0
    team2_price: float = 0.0
    volume: float = 0.0
    liquidity: float = 0.0
    end_date: Optional[datetime] = None


# ==============================================================================
# TEAM NAME DATABASE
# ==============================================================================

TEAM_ALIASES = {
    # LCK (Korea)
    "t1": ["t1", "skt", "sk telecom", "skt t1"],
    "gen.g": ["gen", "geng", "gen.g", "gen g"],
    "dplus kia": ["dk", "damwon", "damwon kia", "dplus kia", "dplus"],
    "kt rolster": ["kt", "kt rolster", "rolster"],
    "hanwha life esports": ["hle", "hanwha", "hanwha life", "hanwha life esports"],
    "drx": ["drx"],
    "kwangdong freecs": ["kdf", "kwangdong", "freecs"],
    "liiv sandbox": ["lsb", "sandbox", "liiv sandbox"],
    "nongshim redforce": ["ns", "nongshim", "redforce"],
    "brion": ["bro", "brion", "fredit brion", "ok brion"],
    
    # LEC (Europe)
    "g2 esports": ["g2", "g2 esports"],
    "fnatic": ["fnc", "fnatic"],
    "mad lions": ["mad", "mad lions"],
    "team vitality": ["vit", "vitality", "team vitality"],
    "team bds": ["bds", "team bds"],
    "excel esports": ["xl", "excel"],
    "sk gaming": ["sk", "sk gaming"],
    "astralis": ["ast", "astralis"],
    "team heretics": ["th", "heretics"],
    "karmine corp": ["kc", "karmine", "karmine corp"],
    
    # LCS (North America)
    "cloud9": ["c9", "cloud9", "cloud 9"],
    "team liquid": ["tl", "liquid", "team liquid"],
    "100 thieves": ["100t", "100 thieves", "hundred thieves"],
    "flyquest": ["fly", "flyquest"],
    "dignitas": ["dig", "dignitas"],
    "nrg": ["nrg", "nrg esports"],
    "immortals": ["imt", "immortals"],
    "golden guardians": ["gg", "golden guardians"],
    
    # LPL (China)
    "jd gaming": ["jdg", "jd gaming", "jd"],
    "bilibili gaming": ["blg", "bilibili", "bilibili gaming"],
    "weibo gaming": ["wbg", "weibo", "weibo gaming"],
    "lng esports": ["lng", "lng esports"],
    "top esports": ["tes", "top", "top esports"],
    "edward gaming": ["edg", "edward gaming"],
    "royal never give up": ["rng", "royal", "royal never give up"],
    "funplus phoenix": ["fpx", "funplus", "funplus phoenix"],
    "invictus gaming": ["ig", "invictus gaming"],
    "oh my god": ["omg", "oh my god"],
    "anyone's legend": ["al", "anyone's legend"],
    "rare atom": ["ra", "rare atom"],
    "ninjas in pyjamas": ["nip", "ninjas in pyjamas"],
    "ultra prime": ["up", "ultra prime"],
}


# ==============================================================================
# ESPORTS ORACLE STRATEGY
# ==============================================================================

class EsportsOracleStrategy:
    """
    Esports Latency Oracle trading strategy.
    
    Monitors live LoL esports matches via Riot API and generates
    trading signals when game-ending events are detected before
    Twitch stream viewers can react.
    
    Features:
    - Fault-tolerant API client (no crash on key expiry)
    - Automatic market matching via fuzzy search
    - Real-time event detection
    - Hot-reload support for API key updates
    """
    
    def __init__(
        self,
        db_callback=None,  # Callback to save signals to database
        order_callback=None,  # Callback to execute orders
    ):
        """
        Initialize Oracle strategy.
        
        Args:
            db_callback: Async function(signal) to save signal to DB
            order_callback: Async function(signal) to execute trade
        """
        self.log = logging.getLogger("ORACLE")
        
        # State
        self.state = StrategyState.IDLE
        self.riot_client: Optional[RiotGuard] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Active monitoring
        self.active_matches: Dict[str, LiveMatch] = {}
        self.last_game_states: Dict[str, GameState] = {}
        self.polymarket_cache: List[PolymarketMatch] = []
        self.polymarket_cache_time: Optional[datetime] = None
        
        # Callbacks
        self.db_callback = db_callback
        self.order_callback = order_callback
        
        # Stats
        self.signals_generated = 0
        self.events_detected = 0
        self.markets_matched = 0
        
        # Control
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
    
    # ==========================================================================
    # LIFECYCLE
    # ==========================================================================
    
    async def start(self) -> bool:
        """
        Start the Oracle strategy.
        
        Returns:
            True if started successfully, False if API unavailable
        """
        self.log.info("=" * 50)
        self.log.info("Starting ORACLE Esports Strategy...")
        self.log.info("=" * 50)
        
        # Create HTTP session
        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        
        # Initialize Riot client with callbacks
        self.riot_client = await create_riot_client(
            on_key_expired=self._on_riot_key_expired,
            on_key_restored=self._on_riot_key_restored,
        )
        
        if not self.riot_client.is_available:
            self.log.warning("Riot API unavailable - ORACLE starting in PAUSED state")
            self.state = StrategyState.PAUSED
            return False
        
        self.state = StrategyState.IDLE
        self._running = True
        
        # Start monitoring loop
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        
        self.log.info("✓ ORACLE strategy started successfully")
        return True
    
    async def stop(self):
        """Stop the Oracle strategy"""
        self.log.info("Stopping ORACLE strategy...")
        
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        if self.riot_client:
            await self.riot_client.shutdown()
        
        if self.http_session:
            await self.http_session.close()
        
        self.state = StrategyState.DISABLED
        self.log.info("✓ ORACLE strategy stopped")
    
    async def hot_reload_api_key(self) -> bool:
        """
        Hot-reload Riot API key from environment.
        
        Call this after updating RIOT_API_KEY in .env
        
        Returns:
            True if new key is valid
        """
        if not self.riot_client:
            return False
        
        success = await self.riot_client.hot_reload_key()
        
        if success:
            self.state = StrategyState.IDLE
            self.log.info("ORACLE resumed with new API key")
        
        return success
    
    # ==========================================================================
    # CALLBACKS
    # ==========================================================================
    
    async def _on_riot_key_expired(self):
        """Called when Riot API key expires"""
        self.log.error("=" * 50)
        self.log.error("RIOT API KEY EXPIRED!")
        self.log.error("ORACLE strategy PAUSED")
        self.log.error("Update RIOT_API_KEY in .env and call hot_reload_api_key()")
        self.log.error("=" * 50)
        
        self.state = StrategyState.PAUSED
    
    async def _on_riot_key_restored(self):
        """Called when Riot API key is restored"""
        self.log.info("=" * 50)
        self.log.info("RIOT API KEY RESTORED!")
        self.log.info("ORACLE strategy RESUMED")
        self.log.info("=" * 50)
        
        self.state = StrategyState.IDLE
    
    # ==========================================================================
    # MONITORING LOOP
    # ==========================================================================
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        self.log.info("Starting monitoring loop...")
        
        while self._running:
            try:
                # Skip if paused
                if self.state == StrategyState.PAUSED:
                    await asyncio.sleep(30)
                    continue
                
                # 1. Get live esports matches
                await self._update_live_matches()
                
                # 2. Monitor each active match
                if self.active_matches:
                    self.state = StrategyState.MONITORING
                    
                    for match_id, match in list(self.active_matches.items()):
                        await self._monitor_match(match)
                else:
                    self.state = StrategyState.IDLE
                
                # 3. Sleep before next poll
                await asyncio.sleep(POLLING_INTERVAL)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)
    
    async def _update_live_matches(self):
        """Fetch and update live esports matches"""
        if not self.riot_client or not self.riot_client.is_available:
            return
        
        matches = await self.riot_client.get_live_esports_matches()
        
        # Update active matches
        current_ids = set()
        
        for event in matches:
            match_data = event.get("match", {})
            teams = match_data.get("teams", [])
            
            if len(teams) < 2:
                continue
            
            event_id = event.get("id", "")
            current_ids.add(event_id)
            
            if event_id not in self.active_matches:
                # New match found
                match = LiveMatch(
                    match_id=match_data.get("id", event_id),
                    event_id=event_id,
                    league=event.get("league", {}).get("name", "Unknown"),
                    team_blue=teams[0].get("name", "Team 1"),
                    team_red=teams[1].get("name", "Team 2"),
                    score_blue=teams[0].get("result", {}).get("gameWins", 0),
                    score_red=teams[1].get("result", {}).get("gameWins", 0),
                    best_of=match_data.get("strategy", {}).get("count", 3),
                )
                
                self.active_matches[event_id] = match
                self.log.info(f"📺 New match: {match.team_blue} vs {match.team_red} ({match.league})")
            else:
                # Update existing match
                match = self.active_matches[event_id]
                match.score_blue = teams[0].get("result", {}).get("gameWins", 0)
                match.score_red = teams[1].get("result", {}).get("gameWins", 0)
                match.last_update = datetime.utcnow()
        
        # Remove finished matches
        for match_id in list(self.active_matches.keys()):
            if match_id not in current_ids:
                match = self.active_matches.pop(match_id)
                self.log.info(f"🏁 Match ended: {match.team_blue} vs {match.team_red}")
    
    async def _monitor_match(self, match: LiveMatch):
        """Monitor a specific match for events"""
        # Get game stats if we have a game ID
        if match.current_game_id:
            stats = await self.riot_client.get_live_game_stats(match.current_game_id)
            
            if stats:
                game_state = self._parse_game_stats(stats)
                
                if game_state:
                    # Check for significant events
                    await self._check_events(match, game_state)
                    
                    # Update last known state
                    self.last_game_states[match.match_id] = game_state
    
    def _parse_game_stats(self, stats: Dict[str, Any]) -> Optional[GameState]:
        """Parse game stats into GameState object"""
        try:
            frames = stats.get("frames", [])
            if not frames:
                return None
            
            # Get latest frame
            frame = frames[-1]
            
            blue_team = frame.get("blueTeam", {})
            red_team = frame.get("redTeam", {})
            
            return GameState(
                game_id=stats.get("game_id", ""),
                game_time_seconds=frame.get("rfc460Timestamp", 0),
                blue_kills=blue_team.get("totalKills", 0),
                red_kills=red_team.get("totalKills", 0),
                blue_towers=blue_team.get("towers", 0),
                red_towers=red_team.get("towers", 0),
                blue_dragons=blue_team.get("dragons", 0),
                red_dragons=red_team.get("dragons", 0),
                blue_barons=blue_team.get("barons", 0),
                red_barons=red_team.get("barons", 0),
                blue_gold=blue_team.get("totalGold", 0),
                red_gold=red_team.get("totalGold", 0),
            )
        except Exception as e:
            self.log.error(f"Error parsing game stats: {e}")
            return None
    
    async def _check_events(self, match: LiveMatch, state: GameState):
        """Check for significant game events"""
        last_state = self.last_game_states.get(match.match_id)
        
        if not last_state:
            return  # Need previous state to detect changes
        
        # Check for Baron taken
        if state.blue_barons > last_state.blue_barons:
            self.log.info(f"🐉 BARON: {match.team_blue} (Blue) took Baron!")
            self.events_detected += 1
            await self._process_event(match, GameEvent.BARON_TAKEN, "blue", state)
        
        if state.red_barons > last_state.red_barons:
            self.log.info(f"🐉 BARON: {match.team_red} (Red) took Baron!")
            self.events_detected += 1
            await self._process_event(match, GameEvent.BARON_TAKEN, "red", state)
        
        # Check for Ace (detect 5-kill swing in short period)
        if state.blue_kills - last_state.blue_kills >= 4:
            self.log.info(f"⚔️ ACE: {match.team_blue} (Blue) potential ace!")
            self.events_detected += 1
            await self._process_event(match, GameEvent.ACE, "blue", state)
        
        if state.red_kills - last_state.red_kills >= 4:
            self.log.info(f"⚔️ ACE: {match.team_red} (Red) potential ace!")
            self.events_detected += 1
            await self._process_event(match, GameEvent.ACE, "red", state)
        
        # Check for game end (would require separate detection)
        if state.game_over:
            self.log.info(f"🏆 GAME END: Winner is {state.winner}!")
            self.events_detected += 1
            await self._process_event(match, GameEvent.GAME_END, state.winner or "unknown", state)
    
    async def _process_event(
        self, 
        match: LiveMatch, 
        event: GameEvent, 
        team_side: str,
        state: GameState
    ):
        """Process a detected game event and generate signal if market exists"""
        
        # Find matching Polymarket market
        poly_match = await self._find_polymarket_match(match)
        
        if not poly_match:
            self.log.info(f"  No Polymarket market found for {match.team_blue} vs {match.team_red}")
            return
        
        self.markets_matched += 1
        
        # Calculate expected price shift based on event
        if event == GameEvent.GAME_END:
            # Game ended - price should move to 1.0 for winner
            if team_side == "blue":
                expected_price = 0.98  # Near certainty
                current_price = poly_match.team1_price
            else:
                expected_price = 0.98
                current_price = poly_match.team2_price
        
        elif event == GameEvent.BARON_TAKEN:
            # Baron - expect ~15% price swing
            if team_side == "blue":
                expected_price = min(poly_match.team1_price + 0.15, 0.95)
                current_price = poly_match.team1_price
            else:
                expected_price = min(poly_match.team2_price + 0.15, 0.95)
                current_price = poly_match.team2_price
        
        elif event == GameEvent.ACE:
            # Ace - expect ~10% price swing
            if team_side == "blue":
                expected_price = min(poly_match.team1_price + 0.10, 0.95)
                current_price = poly_match.team1_price
            else:
                expected_price = min(poly_match.team2_price + 0.10, 0.95)
                current_price = poly_match.team2_price
        
        else:
            return  # Unknown event type
        
        # Calculate edge
        edge = expected_price - current_price
        
        if edge < MIN_EDGE_THRESHOLD:
            self.log.info(f"  Edge too low: {edge:.2%} < {MIN_EDGE_THRESHOLD:.2%}")
            return
        
        # Generate signal
        signal = OracleSignal(
            signal_id=f"ORACLE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{match.match_id[:8]}",
            match_id=match.match_id,
            event_type=event,
            match_description=f"{match.team_blue} vs {match.team_red}",
            team_blue=match.team_blue,
            team_red=match.team_red,
            detected_winner=match.team_blue if team_side == "blue" else match.team_red,
            market_question=poly_match.question,
            market_condition_id=poly_match.condition_id,
            recommended_side="YES",
            token_id=poly_match.team1_token_id if team_side == "blue" else poly_match.team2_token_id,
            current_price=current_price,
            expected_price=expected_price,
            edge=edge,
            stake_usdc=min(MAX_STAKE_USDC, poly_match.liquidity * 0.1),  # Max 10% of liquidity
            confidence=0.85 if event == GameEvent.GAME_END else 0.70,
            estimated_stream_time=datetime.utcnow() + timedelta(seconds=45),
        )
        
        self.signals_generated += 1
        
        self.log.info("=" * 50)
        self.log.info(f"🎯 ORACLE SIGNAL GENERATED!")
        self.log.info(f"   Event: {event.value}")
        self.log.info(f"   Match: {signal.match_description}")
        self.log.info(f"   Winner: {signal.detected_winner}")
        self.log.info(f"   Edge: {signal.edge:.2%}")
        self.log.info(f"   Stake: ${signal.stake_usdc:.2f}")
        self.log.info(f"   Window: ~35 seconds")
        self.log.info("=" * 50)
        
        # Save to database
        if self.db_callback:
            try:
                await self.db_callback(signal)
            except Exception as e:
                self.log.error(f"Error saving signal to DB: {e}")
        
        # Execute trade
        if self.order_callback:
            try:
                await self.order_callback(signal)
            except Exception as e:
                self.log.error(f"Error executing trade: {e}")
    
    # ==========================================================================
    # POLYMARKET INTEGRATION
    # ==========================================================================
    
    async def _refresh_polymarket_cache(self):
        """Refresh Polymarket esports markets cache"""
        if (
            self.polymarket_cache_time 
            and datetime.utcnow() - self.polymarket_cache_time < timedelta(minutes=5)
        ):
            return  # Cache is fresh
        
        self.polymarket_cache = []
        
        esports_keywords = [
            "esports", "league of legends", "lol", "worlds", "msi",
            "lcs", "lec", "lck", "lpl",
            "t1", "gen.g", "fnatic", "g2", "cloud9",
        ]
        
        try:
            for keyword in esports_keywords[:5]:  # Limit searches
                url = f"{POLYMARKET_API}/markets"
                params = {
                    "closed": "false",
                    "active": "true", 
                    "limit": 50,
                    "_q": keyword,
                }
                
                async with self.http_session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        for market in data:
                            # Check if already cached
                            condition_id = market.get("conditionId", "")
                            if any(m.condition_id == condition_id for m in self.polymarket_cache):
                                continue
                            
                            question = market.get("question", "").lower()
                            
                            # Filter for actual esports
                            if any(kw in question for kw in ["esport", "league", "lol", "worlds"]):
                                tokens = market.get("tokens", [])
                                
                                pm = PolymarketMatch(
                                    condition_id=condition_id,
                                    question=market.get("question", ""),
                                    volume=float(market.get("volume", 0) or 0),
                                    liquidity=float(market.get("liquidity", 0) or 0),
                                )
                                
                                if len(tokens) >= 2:
                                    pm.team1_outcome = tokens[0].get("outcome", "")
                                    pm.team2_outcome = tokens[1].get("outcome", "")
                                    pm.team1_token_id = tokens[0].get("token_id", "")
                                    pm.team2_token_id = tokens[1].get("token_id", "")
                                    pm.team1_price = float(tokens[0].get("price", 0) or 0)
                                    pm.team2_price = float(tokens[1].get("price", 0) or 0)
                                
                                self.polymarket_cache.append(pm)
                
                await asyncio.sleep(0.1)
            
            self.polymarket_cache_time = datetime.utcnow()
            self.log.debug(f"Refreshed Polymarket cache: {len(self.polymarket_cache)} markets")
            
        except Exception as e:
            self.log.error(f"Error refreshing Polymarket cache: {e}")
    
    async def _find_polymarket_match(self, match: LiveMatch) -> Optional[PolymarketMatch]:
        """Find Polymarket market for a given esports match"""
        await self._refresh_polymarket_cache()
        
        if not self.polymarket_cache:
            return None
        
        best_match = None
        best_score = 0.0
        
        team1_normalized = self._normalize_team(match.team_blue)
        team2_normalized = self._normalize_team(match.team_red)
        
        for market in self.polymarket_cache:
            if market.liquidity < MIN_LIQUIDITY:
                continue
            
            question = market.question.lower()
            
            # Check for both teams in question
            score1 = self._fuzzy_team_match(team1_normalized, question)
            score2 = self._fuzzy_team_match(team2_normalized, question)
            
            combined = (score1 + score2) / 2
            
            if combined > best_score and combined >= FUZZY_MATCH_THRESHOLD:
                best_score = combined
                best_match = market
        
        if best_match:
            self.log.debug(f"Matched market: {best_match.question[:50]}... (score: {best_score:.2f})")
        
        return best_match
    
    def _normalize_team(self, team_name: str) -> str:
        """Normalize team name for matching"""
        normalized = team_name.lower().strip()
        
        for canonical, aliases in TEAM_ALIASES.items():
            if normalized in aliases or normalized == canonical:
                return canonical
        
        return normalized
    
    def _fuzzy_team_match(self, team: str, text: str) -> float:
        """Calculate fuzzy match score"""
        if team in text:
            return 1.0
        
        aliases = TEAM_ALIASES.get(team, [team])
        for alias in aliases:
            if alias in text:
                return 0.95
        
        words = text.split()
        best = 0.0
        for word in words:
            ratio = SequenceMatcher(None, team, word).ratio()
            best = max(best, ratio)
        
        return best
    
    # ==========================================================================
    # STATUS & STATS
    # ==========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get current strategy status"""
        return {
            "strategy": "ORACLE",
            "state": self.state.value,
            "riot_api_available": self.riot_client.is_available if self.riot_client else False,
            "riot_api_key": self.riot_client.api_key if self.riot_client else "<not initialized>",
            "active_matches": len(self.active_matches),
            "matches": [
                {
                    "id": m.match_id,
                    "match": f"{m.team_blue} vs {m.team_red}",
                    "league": m.league,
                    "score": f"{m.score_blue}-{m.score_red}",
                }
                for m in self.active_matches.values()
            ],
            "polymarket_cache_size": len(self.polymarket_cache),
            "stats": {
                "signals_generated": self.signals_generated,
                "events_detected": self.events_detected,
                "markets_matched": self.markets_matched,
            }
        }


# ==============================================================================
# INTEGRATION WITH DAEMON
# ==============================================================================

class OracleStrategyRunner:
    """
    Wrapper to integrate Oracle strategy with multi_strategy_daemon.
    
    Provides the same interface as other strategies:
    - async run_cycle() method
    - Graceful error handling
    - Status reporting
    """
    
    def __init__(self, db_session=None, order_executor=None):
        self.strategy = EsportsOracleStrategy(
            db_callback=self._save_signal,
            order_callback=self._execute_order,
        )
        self.db_session = db_session
        self.order_executor = order_executor
        self.log = logging.getLogger("ORACLE.Runner")
        self._initialized = False
    
    async def initialize(self):
        """Initialize the strategy"""
        if self._initialized:
            return
        
        await self.strategy.start()
        self._initialized = True
    
    async def run_cycle(self) -> List[OracleSignal]:
        """
        Run one monitoring cycle.
        
        Note: The actual monitoring runs in a background task.
        This method just returns current status/recent signals.
        """
        if not self._initialized:
            await self.initialize()
        
        # Return status (actual monitoring is continuous)
        return []
    
    async def shutdown(self):
        """Shutdown the strategy"""
        await self.strategy.stop()
        self._initialized = False
    
    async def _save_signal(self, signal: OracleSignal):
        """Save signal to database"""
        if self.db_session:
            # TODO: Implement DB save
            self.log.info(f"Saving signal {signal.signal_id} to database")
    
    async def _execute_order(self, signal: OracleSignal):
        """Execute trade order"""
        if self.order_executor:
            # TODO: Implement order execution
            self.log.info(f"Executing order for signal {signal.signal_id}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get strategy status"""
        return self.strategy.get_status()


# ==============================================================================
# CLI FOR TESTING
# ==============================================================================

async def main():
    """Test the Oracle strategy"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)7s | %(name)s | %(message)s"
    )
    
    print("=" * 60)
    print("      ESPORTS ORACLE STRATEGY - TEST")
    print("=" * 60)
    
    strategy = EsportsOracleStrategy()
    
    try:
        success = await strategy.start()
        
        if not success:
            print("\n⚠️  Strategy started in PAUSED state (API key issue)")
            print("   Update RIOT_API_KEY in .env and call hot_reload_api_key()")
        
        # Run for a bit to see matches
        print("\nMonitoring for 60 seconds...")
        await asyncio.sleep(60)
        
        # Print status
        status = strategy.get_status()
        print(f"\nStatus: {status['state']}")
        print(f"Active matches: {status['active_matches']}")
        for match in status['matches']:
            print(f"  - {match['match']} ({match['league']}) {match['score']}")
        
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        await strategy.stop()
        print("\n✓ Strategy stopped")


if __name__ == "__main__":
    asyncio.run(main())
