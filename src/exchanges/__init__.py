"""
📦 Exchanges Module
===================
Clients for external APIs and exchanges.

Available:
- RiotGuard: Riot Games API client for esports data

DEPRECATED (Jan 2026):
- PredictBaseClient: Removed - platform has 0 liquidity
"""

# Only import what exists and is actively used
try:
    from .riot_client import RiotGuard, create_riot_client, KeyExpiredError
    RIOT_AVAILABLE = True
except ImportError:
    RIOT_AVAILABLE = False

# PredictBase REMOVED - file archived to archive/deprecated_20260102/
# from .predictbase_client import PredictBaseClient, PredictBaseMarket

__all__ = ['RiotGuard', 'create_riot_client', 'KeyExpiredError', 'RIOT_AVAILABLE']
