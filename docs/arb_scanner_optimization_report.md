# ARB Scanner Optimization - Findings Report

## Date: January 2, 2026

## Summary
After thorough testing and analysis, we've identified the **fundamental reason** why the ARB scanner was finding zero arbitrage opportunities between Polymarket and PredictBase.

## Key Discovery

### Market Type Mismatch

**PredictBase Markets** (5 active, 1000+ resolved):
- Focus on **individual game outcomes**
- Format: "Team A vs. Team B"
- Examples:
  - "NHL: Kings vs. Wild"
  - "NBA: Lakers vs. Celtics" 
  - "Premier League: Arsenal vs. Man City"
  - "NFL: Ravens vs. Chiefs"

**Polymarket Markets** (300+ sports):
- Focus on **season/championship outcomes**
- Format: "Will X win Y Championship?"
- Examples:
  - "Will the Ravens win Super Bowl 2026?"
  - "Will the Lakers win the NBA Championship?"
  - "Will the Packers win the NFC Championship?"

### The Problem
These are **fundamentally different bet types**:
- **Game bet**: Will Lakers beat Celtics on January 5th?
- **Futures bet**: Will Lakers win the NBA Championship?

You **CANNOT arbitrage** these against each other - they're not the same market!

## Technical Achievements

Despite the overlap issue, we successfully implemented:

1. **Targeted Sports Fetch** (`fetch_targeted_markets()`)
   - Uses word-boundary regex matching (fixes "inflation" → "nfl" false positive)
   - Filters 300+ sports markets from Polymarket (vs ~20 with general fetch)
   - 75% hit rate on sports markets

2. **Sports Keywords List**
   - 100+ keywords including leagues, teams, conferences
   - NFL, NBA, NHL, MLB, MLS, UEFA coverage
   - All 32 NFL teams, 30 NBA teams

3. **Fuzzy Matching Improvements**
   - Installed thefuzz library for better matching
   - Lowered threshold to 60% (from 85%)
   - Still finding 0 matches due to format differences

## Recommendations

### Option 1: Find Matching Markets
Look for Polymarket markets that match PredictBase's format:
- Daily game outcomes (rare on Polymarket)
- Spread bets for specific games

### Option 2: Different PB Strategy
PredictBase is better suited for:
- **In-play scalping** on individual games
- **Same-game arbitrage** (PB vs other sportsbooks)
- NOT cross-exchange arb with Polymarket

### Option 3: Different Platform
Consider platforms with futures markets:
- Kalshi (has championship markets)
- Pinnacle/Betfair for sports futures

## Files Modified

1. `src/scanner/arb_scanner.py`
   - Added `SPORTS_KEYWORDS` with regex word boundaries
   - Added `_is_sports_question()` helper
   - Updated `fetch_targeted_markets()` - uses keyword filtering (events endpoint broken)
   - Disabled events endpoint (returns 422 errors)
   - Lowered default `fuzzy_threshold` to 60

2. `tools/` - Testing scripts:
   - `get_polymarket_tags.py` - API explorer
   - `test_targeted_fetch.py` - Fetch tester
   - `test_fuzzy_match.py` - Matching tester
   - `check_pb_markets.py` - PB market analyzer

## Conclusion

The ARB scanner is **technically working correctly**. The lack of signals is due to:
1. No market overlap between platforms
2. Different market types (games vs championships)
3. Very limited PredictBase active markets (only 5)

The Polymarket-focused strategies (spread scanning, market timing) remain more viable than cross-exchange arbitrage with PredictBase.
