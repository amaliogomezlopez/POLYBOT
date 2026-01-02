# V2 Production Deployment Guide

## Overview
This document describes the deployment of Hydra V2 with two new strategies derived from the Whale Hunting research project.

## New Strategies

### 1. Flash Sniper (`src/trading/strategies/flash_sniper.py`)
**Based on Account88888** - Ultra-HFT for 15-minute crypto flash markets.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `stake_size` | $100 | Per leg (so $200 total per arb) |
| `min_spread` | 0.2% | Lower than legacy (was 1%) |
| `max_combined_cost` | $0.998 | Guaranteed profit threshold |
| `max_daily_trades` | 500 | High frequency like Account88888 |

**Logic**: Buy both UP and DOWN tokens when `YES_price + NO_price < 0.998`.

### 2. Contrarian NO (`src/trading/strategies/contrarian_no.py`)
**Based on tsybka** - "Nothing Ever Happens" mean reversion.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `stake_size` | $200 | Higher conviction bets |
| `min_yes_price` | 8% | Don't bet if NO is already winning |
| `max_yes_price` | 40% | Avoid events that might happen |
| `max_daily_trades` | 10 | Low frequency (tsybka style) |

**Logic**: Buy NO on sensational markets where retail overbuys YES on fear/hope.

## Deployment

### Local Testing
```bash
# Run daemon locally in paper mode
python scripts/multi_strategy_daemon.py --daemon --interval 60

# Single cycle (debug)
python scripts/multi_strategy_daemon.py
```

### VPS Deployment
```bash
# Make deploy script executable
chmod +x scripts/deploy_v2.sh

# Run deployment
./scripts/deploy_v2.sh
```

## Strategy Registration
The daemon registers 5 strategies:
1. **InternalArbStrategy** (Legacy) - $50/trade - Orderbook inefficiencies
2. **SniperStrategy** (Legacy) - $5/trade - Panic drop rebounds
3. **TailStrategy** (Legacy) - $2/trade - Low price multipliers
4. **FlashSniperStrategy** (V2) - $100/trade - Crypto flash arb
5. **ContrarianNoStrategy** (V2) - $200/trade - Sensationalism fade

## Capital Allocation
| Strategy | Base Stake | Max Daily | Risk Level |
|----------|------------|-----------|------------|
| Flash Sniper | $100 | 500 | Low (arb) |
| Contrarian NO | $200 | 10 | Medium |
| Internal Arb | $50 | 50 | Low (arb) |
| Sniper | $5 | 50 | Medium |
| Tail | $2 | 50 | High |

**Total Daily Exposure** (max):
- Flash: $100 × 500 = $50,000
- Contrarian: $200 × 10 = $2,000
- Others: ~$5,000

## Monitoring
```bash
# View live logs
tail -f logs/multi_strategy.log

# Check signals
cat data/multi_strategy/signals.json | jq '.[-10:]'

# Strategy stats
sqlite3 data/polybot.db "SELECT strategy_id, COUNT(*) FROM trades GROUP BY strategy_id"
```

## Rollback
If issues occur:
```bash
# Revert to previous version
git checkout HEAD~1 -- src/trading/strategies/
git checkout HEAD~1 -- scripts/multi_strategy_daemon.py
./scripts/deploy_v2.sh
```
