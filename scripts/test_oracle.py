#!/usr/bin/env python3
"""
Quick test for ORACLE strategy integration
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)

async def main():
    print("=" * 60)
    print("    ORACLE STRATEGY INTEGRATION TEST")
    print("=" * 60)
    
    # Import
    print("\n1. Testing imports...")
    try:
        from src.trading.strategies import EsportsOracleStrategy
        from src.exchanges.riot_client import RiotGuard, create_riot_client
        print("   ✓ All imports successful")
    except Exception as e:
        print(f"   ✗ Import error: {e}")
        return
    
    # Create strategy
    print("\n2. Creating ORACLE strategy...")
    strategy = EsportsOracleStrategy()
    
    # Start
    print("\n3. Starting strategy...")
    success = await strategy.start()
    
    if success:
        print("   ✓ Strategy started successfully")
    else:
        print("   ⚠ Strategy started in PAUSED state (normal for dev API key)")
    
    # Get status
    print("\n4. Strategy status:")
    status = strategy.get_status()
    print(f"   State: {status['state']}")
    print(f"   Riot API Available: {status['riot_api_available']}")
    print(f"   Riot API Key: {status['riot_api_key']}")
    print(f"   Active Matches: {status['active_matches']}")
    
    # Let it run briefly
    print("\n5. Running for 10 seconds...")
    await asyncio.sleep(10)
    
    # Final status
    print("\n6. Final status:")
    status = strategy.get_status()
    print(f"   Active Matches: {status['active_matches']}")
    print(f"   Signals Generated: {status['stats']['signals_generated']}")
    print(f"   Events Detected: {status['stats']['events_detected']}")
    
    # Stop
    print("\n7. Stopping strategy...")
    await strategy.stop()
    print("   ✓ Strategy stopped")
    
    print("\n" + "=" * 60)
    print("    TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
