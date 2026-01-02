# ORACLE Esports Strategy - Operations Guide

## 🔑 API Key Management

### Development Keys (Current Setup)

Riot Development API keys expire **every 24 hours** and must be manually renewed.

**Your Current Key:** `RGAPI-dbbb09fd-e591-4b53-bf91-cce9970e37dc`  
**Expires:** Sat, Jan 3rd, 2026 @ 9:06am (PT) = ~17:06 UTC

### Renewing the API Key

1. Go to: https://developer.riotgames.com/
2. Log in with your Riot account
3. Click **"Regenerate API Key"**
4. Copy the new key

### Updating the Key on VPS

**Method 1: Hot Reload (No Restart Required)**

```bash
# SSH to VPS
ssh root@94.143.138.8

# Edit .env
nano /opt/polymarket-bot/.env

# Find and replace RIOT_API_KEY=...
# Save and exit (Ctrl+X, Y, Enter)

# Send SIGHUP to daemon for hot reload
kill -HUP $(pgrep -f "multi_strategy_daemon")
```

**Method 2: Full Restart**

```bash
# SSH to VPS
ssh root@94.143.138.8

# Stop daemon
systemctl stop polymarket-bot
# Or: pkill -f "multi_strategy_daemon"

# Edit .env
nano /opt/polymarket-bot/.env
# Update RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Start daemon
systemctl start polymarket-bot
# Or: cd /opt/polymarket-bot && source venv/bin/activate && python scripts/multi_strategy_daemon.py --daemon
```

**Method 3: Remote Update (From Windows)**

```powershell
# Update .env locally with new key
# Then upload:
scp .env root@94.143.138.8:/opt/polymarket-bot/

# Hot reload (Unix)
ssh root@94.143.138.8 "kill -HUP \$(pgrep -f multi_strategy_daemon)"
```

---

## 🎮 How ORACLE Works

### Data Flow

```
┌──────────────────────┐     ┌─────────────────────┐     ┌──────────────┐
│  LoL Esports API     │────▶│  ORACLE Strategy    │────▶│  Polymarket  │
│  (lolesports.com)    │     │  Event Detection    │     │  Market Match│
│  FREE, no rate limit │     │  Baron/Dragon/Ace   │     │  Fuzzy Search│
└──────────────────────┘     └─────────────────────┘     └──────────────┘
```

### Event Detection

| Event | API Delay | Stream Delay | Arbitrage Window |
|-------|-----------|--------------|------------------|
| Baron Taken | ~500ms | 30-60s | **~35 seconds** |
| Dragon Taken | ~500ms | 30-60s | **~35 seconds** |
| Ace (5 kills) | ~200ms | 30-60s | **~35 seconds** |
| Game End | ~2s | 30-60s | **~33 seconds** |

### Strategy Parameters

```python
POLLING_INTERVAL = 2.0      # Check every 2 seconds
MIN_EDGE_THRESHOLD = 0.05   # Minimum 5% edge to trade
MAX_STAKE_USDC = 25.0       # Maximum $25 per trade
MIN_LIQUIDITY = 500.0       # Need at least $500 liquidity
```

---

## 📊 Monitoring ORACLE

### Check Strategy Status

```bash
# View live logs
journalctl -u polymarket-bot -f | grep ORACLE

# Or if running manually:
tail -f /opt/polymarket-bot/logs/multi_strategy.log | grep ORACLE
```

### Dashboard

The ORACLE signals appear in the main dashboard at http://94.143.138.8

---

## ⚠️ Troubleshooting

### "Riot API key expired" Error

**Symptoms:**
```
ERROR | RIOT API KEY EXPIRED!
ERROR | Strategy ORACLE will be paused until key is updated.
```

**Solution:**
1. Get new key from https://developer.riotgames.com/
2. Update `.env` on VPS
3. Hot reload or restart daemon

### No Live Matches Detected

This is **normal** when there are no professional matches happening. The LoL Esports API only shows scheduled/live events.

**Check upcoming matches:**
```bash
curl -s "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US" \
  -H "x-api-key: 0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z" | python -m json.tool
```

### Strategy Stuck in PAUSED State

```bash
# Force hot-reload
cd /opt/polymarket-bot && source venv/bin/activate
python -c "
import asyncio
from src.trading.strategies import EsportsOracleStrategy
async def reload():
    s = EsportsOracleStrategy()
    await s.start()
    await s.hot_reload_api_key()
    print(s.get_status())
    await s.stop()
asyncio.run(reload())
"
```

---

## 🗓️ Tournament Calendar 2026

**Best times for ORACLE:**

| Month | Tournament | Expected Volume |
|-------|------------|-----------------|
| Jan | LCK/LPL Spring | Medium |
| Feb | IEM Katowice (CS2) | High |
| May | **MSI** | **Very High** |
| Aug | The International (Dota2) | High |
| Oct-Nov | **Worlds** | **Very High** |

---

## 🔧 Production API Key

For a permanent solution (no 24h expiry), register a Production application:

1. Go to: https://developer.riotgames.com/app
2. Create new application
3. Fill in details:
   - Application Name: "Polymarket Esports Oracle"
   - Application Type: "Personal"
   - Description: "Esports betting analytics tool"
4. Wait for approval (usually 2-3 days)
5. Once approved, your key won't expire

---

## 📁 Files Reference

| File | Description |
|------|-------------|
| `src/exchanges/riot_client.py` | Fault-tolerant Riot API client |
| `src/trading/strategies/esports_oracle.py` | ORACLE strategy implementation |
| `scripts/multi_strategy_daemon.py` | Main daemon (integrates ORACLE) |
| `scripts/test_oracle.py` | Standalone ORACLE test |
| `research/esports_delay_check.py` | Research/PoC script |
| `.env` | Contains `RIOT_API_KEY` |

---

**Last Updated:** 2026-01-02  
**VPS:** 94.143.138.8  
**Key Expiry Check:** https://developer.riotgames.com/
