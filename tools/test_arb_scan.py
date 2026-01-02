#!/usr/bin/env python3
"""Test the full ARB scanner with targeted sports fetch."""

import asyncio
import sys
sys.path.insert(0, r'c:\Users\amalio\Desktop\PROGRAMACION\01-VS_CODE\32-POLYMARKET-BOT')

from src.scanner.arb_scanner import ARBScanner

async def main():
    print("=" * 70)
    print("TESTING FULL ARB SCANNER WITH TARGETED SPORTS FETCH")
    print("=" * 70)
    
    # Initialize scanner with context manager
    async with ARBScanner(
        min_roi_pct=2.0,  # Lower threshold for testing
        fuzzy_threshold=55,  # Lower threshold for different question formats
    ) as scanner:
        
        # Run scan with targeted fetch (sports only)
        signals = await scanner.scan(use_targeted=True)
        
        print(f"\n📊 RESULTS:")
        print(f"   Total signals found: {len(signals)}")
        
        if signals:
            print(f"\n🎯 ARB SIGNALS:")
            for s in signals[:10]:
                print(f"   • {s.poly_question[:50]}...")
                print(f"     Poly: YES=${s.poly_yes_price:.3f} NO=${s.poly_no_price:.3f}")
                print(f"     PB:   YES=${s.pb_yes_price:.3f} NO=${s.pb_no_price:.3f}")
                print(f"     Spread: {s.spread_pct:.1f}%")
                print()
        else:
            print("\n   No ARB signals found (markets may be too similar in price)")
        
        # Show stats
        print("\n📈 SCANNER STATS:")
        print(f"   Total scans: {scanner._total_scans}")
        print(f"   Total signals: {scanner._total_signals}")
    
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
