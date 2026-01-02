# Esports Latency Oracle - Technical Implementation Plan

## Executive Summary

**Strategy Name:** Esports Latency Oracle (ORACLE)  
**Thesis:** Exploit 30-60s Twitch stream delay using real-time game APIs  
**Target Games:** League of Legends (primary), Dota 2 (secondary), CS2 (low priority)  
**Expected Edge:** 15-50 seconds information advantage  
**Verdict:** ✅ VIABLE - Implement for LoL first

---

## 1. Research Findings

### 1.1 API Latency Measurements (Actual)

| Data Source | Latency | Availability | Reliability |
|-------------|---------|--------------|-------------|
| Riot LoL Esports API | ~491ms | FREE | High |
| OpenDota API | ~150ms | FREE | Medium |
| Polymarket Gamma API | ~60ms | FREE | High |
| HLTV (CS2) | N/A | Scrapers | Low |

### 1.2 Arbitrage Window Calculation

```
Stream Delay (Twitch):     45s (conservative estimate)
API Latency:               0.5s
Market Reaction Time:      10s (time for viewers to bet)
─────────────────────────────────────────────────────────
NET ARBITRAGE WINDOW:      34.5 seconds
```

**Conclusion:** We have a ~35 second window to place bets before stream viewers react.

### 1.3 Event Impact Analysis

| Event | API Delay | Stream Delay | Market Impact |
|-------|-----------|--------------|---------------|
| Kill | 100-500ms | 30-60s | Low |
| Tower Destroyed | 100-500ms | 30-60s | Medium |
| Dragon/Baron | 500-1000ms | 30-60s | **High** |
| Ace (5 kills) | 100-500ms | 30-60s | **High** |
| Game End | 1-3s | 30-60s | **Critical** |

**Priority Events:** Baron, Dragon, Ace, Game End

---

## 2. Data Sources

### 2.1 Riot Games LoL Esports API (PRIMARY)

**Endpoint:** `https://esports-api.lolesports.com/persisted/gw`  
**Live Stats:** `https://feed.lolesports.com/livestats/v1`  
**Authentication:** Public API key (no registration required for basic data)  
**Rate Limit:** No documented limit (reasonable use)  
**Coverage:** LCS, LEC, LCK, LPL, Worlds, MSI, regional leagues

```python
# Sample API Call
headers = {"x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"}
response = requests.get(
    "https://esports-api.lolesports.com/persisted/gw/getLive",
    headers=headers,
    params={"hl": "en-US"}
)
```

### 2.2 OpenDota API (SECONDARY)

**Endpoint:** `https://api.opendota.com/api`  
**Live Matches:** `https://api.opendota.com/api/live`  
**Authentication:** None required  
**Rate Limit:** 60 requests/minute  
**Coverage:** All pro Dota 2 matches

### 2.3 Valve CS2 (LOW PRIORITY)

**Status:** No official live API  
**Alternative:** HLTV scrapers (unreliable)  
**Recommendation:** Skip until market liquidity improves

---

## 3. Polymarket Integration

### 3.1 Esports Market Availability

**Current Status (Jan 2026):** Low  
- Esports markets appear primarily during major tournaments
- Typical volume: $5,000-$50,000 per match
- Liquidity often thin: $1,000-$10,000

**Target Tournaments:**
| Tournament | Game | Timing | Expected Volume |
|------------|------|--------|-----------------|
| Worlds | LoL | October | $50k-500k |
| MSI | LoL | May | $20k-100k |
| LCK/LEC/LCS Finals | LoL | Quarterly | $10k-50k |
| The International | Dota 2 | August | $100k+ |
| CS2 Major | CS2 | Feb/Jul | $50k-200k |

### 3.2 Market Matching Algorithm

```python
# Fuzzy matching between live game and Polymarket market
TEAM_ALIASES = {
    "t1": ["t1", "skt", "sk telecom"],
    "gen.g": ["gen", "geng", "gen.g"],
    "fnatic": ["fnc", "fnatic"],
    # ... 50+ teams mapped
}

def match_market_to_game(live_match, poly_markets):
    for market in poly_markets:
        score = fuzzy_match(live_match.teams, market.question)
        if score > 0.6:  # 60% confidence threshold
            return market
    return None
```

---

## 4. Architecture

### 4.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      HYDRA BOT (VPS)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐                   │
│  │  ARB Strategy   │     │ SNIPER Strategy │                   │
│  └─────────────────┘     └─────────────────┘                   │
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────────────────────┐   │
│  │  TAIL Strategy  │     │  ORACLE Strategy (NEW)          │   │
│  └─────────────────┘     │  ┌─────────────────────────┐    │   │
│                          │  │ Riot LoL Esports Client │    │   │
│                          │  └─────────────────────────┘    │   │
│                          │  ┌─────────────────────────┐    │   │
│                          │  │ OpenDota Client         │    │   │
│                          │  └─────────────────────────┘    │   │
│                          │  ┌─────────────────────────┐    │   │
│                          │  │ Event Detector          │    │   │
│                          │  └─────────────────────────┘    │   │
│                          │  ┌─────────────────────────┐    │   │
│                          │  │ Polymarket Matcher      │    │   │
│                          │  └─────────────────────────┘    │   │
│                          └─────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Order Executor (Shared)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Data Flow

```
1. Riot API → Live Match Data (every 10s)
2. Event Detector → Identify Baron/Dragon/Ace/Game End
3. Polymarket Matcher → Find corresponding market
4. Edge Calculator → Calculate expected odds shift
5. IF edge > 5%:
   → Signal Generator → Create ORACLE signal
   → Order Executor → Place bet
   → Dashboard → Display trade
```

---

## 5. Implementation Phases

### Phase 1: LoL Oracle Core (2-3 days)

**Files to create:**
```
src/strategies/
├── __init__.py
├── esports_oracle.py      # Main Oracle strategy
├── riot_client.py         # Riot API client
├── event_detector.py      # Detects significant events
└── market_matcher.py      # Matches games to Polymarket
```

**Key Components:**

1. **RiotLiveMonitor** - Polls lolesports API every 10s
2. **EventDetector** - Identifies tradeable events
3. **OracleStrategy** - Decision engine
4. **OracleSignal** - Signal format for dashboard

**Sample Signal:**
```python
{
    "strategy": "ORACLE",
    "game": "lol",
    "match": "T1 vs Gen.G",
    "event": "Baron Taken (T1)",
    "event_time": "23:45",
    "api_time": "2026-01-02T16:52:36Z",
    "stream_time_estimate": "2026-01-02T16:53:21Z",  # +45s
    "market": "Will T1 win vs Gen.G?",
    "recommended_side": "YES",
    "pre_event_odds": 0.58,
    "expected_post_event_odds": 0.72,
    "edge": 0.14,  # 14%
    "action": "BUY",
    "stake": 10.00,
}
```

### Phase 2: Integration (1 day)

1. Add ORACLE to `multi_strategy_daemon.py`
2. Add ORACLE signals to PostgreSQL schema
3. Add ORACLE tab to dashboard
4. Test with live LCK/LPL matches

### Phase 3: Dota 2 Support (1 day)

1. Add OpenDota client
2. Map Dota events (Roshan, Aegis)
3. Test during DPC events

### Phase 4: Alerts & Automation (1 day)

1. Telegram alerts for ORACLE opportunities
2. Auto-execution for high-confidence signals
3. Post-match analysis

---

## 6. Risk Analysis

### 6.1 Primary Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| No Polymarket market for match | High | Critical | Only trade during major tournaments |
| Thin liquidity | High | High | Limit stake to $10-50 |
| Market makers have API access | Medium | Medium | Focus on sub-$50k markets |
| API rate limited | Low | Medium | Implement backoff strategy |
| Stream delay shorter than expected | Low | High | Conservative 45s estimate |

### 6.2 Financial Risk

```
Max stake per trade: $50
Max daily ORACLE exposure: $200
Expected win rate: 60-70%
Expected profit per trade: $3-7
Max drawdown: $100 (stop trading if hit)
```

---

## 7. VPS Resource Impact

| Metric | Current (3 strategies) | With ORACLE | Change |
|--------|----------------------|-------------|--------|
| CPU | ~5% | ~8% | +3% |
| Memory | ~200MB | ~250MB | +50MB |
| Network | ~5MB/hour | ~6MB/hour | +1MB/hour |
| DB Storage | ~10MB/day | ~12MB/day | +2MB/day |

**Verdict:** ✅ Safe to run alongside existing strategies

---

## 8. Success Metrics

### 8.1 Launch Criteria

- [ ] Research script validates API access
- [ ] At least 1 esports market found on Polymarket
- [ ] Latency measurements confirm >30s edge
- [ ] Integration tests pass

### 8.2 Performance Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Opportunities detected | 2-5/day (tournament) | Count signals |
| Match-to-market rate | >50% | Matched / Total |
| Win rate | >60% | Won / Total trades |
| Avg profit per trade | $3-7 | Total P&L / Trades |
| Avg edge captured | >5% | Actual vs pre-bet odds |

---

## 9. Tournament Calendar 2026

| Month | Tournament | Game | Priority |
|-------|------------|------|----------|
| January | LCK/LPL Spring | LoL | Medium |
| February | IEM Katowice | CS2 | High |
| March | LCS/LEC Spring Playoffs | LoL | Medium |
| April | LCK Spring Finals | LoL | High |
| May | MSI | LoL | **Critical** |
| June | VCT Masters | Valorant | Low |
| July | CS2 Major | CS2 | High |
| August | The International | Dota 2 | **Critical** |
| September | LCK/LPL Summer | LoL | Medium |
| October | **Worlds** | LoL | **Critical** |
| November | Worlds Finals | LoL | **Critical** |

**Next Major Opportunity:** LCK Spring 2026 (January - ongoing)

---

## 10. Next Steps

### Immediate (Today)

1. ✅ Run research script on VPS
2. ✅ Validate Riot API access
3. ✅ Check for current esports markets on Polymarket
4. ⏳ Get Riot API key (optional, basic access is free)

### This Week

1. Create `src/strategies/esports_oracle.py`
2. Create `src/strategies/riot_client.py`
3. Add ORACLE to daemon
4. Test during LCK match

### Before MSI (May 2026)

1. Full integration complete
2. Telegram alerts working
3. Auto-execution enabled
4. Backtested on historical tournament data

---

## Appendix A: API Reference

### Riot LoL Esports API

```bash
# Get live matches
curl -H "x-api-key: 0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z" \
  "https://esports-api.lolesports.com/persisted/gw/getLive?hl=en-US"

# Get schedule
curl -H "x-api-key: 0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z" \
  "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US"

# Get live game stats (requires game_id)
curl "https://feed.lolesports.com/livestats/v1/window/{game_id}"
```

### OpenDota API

```bash
# Get live pro matches
curl "https://api.opendota.com/api/live"

# Get match details
curl "https://api.opendota.com/api/matches/{match_id}"
```

---

## Appendix B: Team Alias Database

```python
TEAM_ALIASES = {
    # LCK
    "t1": ["t1", "skt", "sk telecom"],
    "gen.g": ["gen", "geng", "gen.g"],
    "dk": ["dk", "damwon", "damwon kia", "dplus kia"],
    "kt rolster": ["kt", "kt rolster"],
    "hanwha life": ["hle", "hanwha", "hanwha life esports"],
    
    # LEC
    "g2 esports": ["g2", "g2 esports"],
    "fnatic": ["fnc", "fnatic"],
    "mad lions": ["mad", "mad lions"],
    "team vitality": ["vit", "vitality", "team vitality"],
    
    # LCS
    "cloud9": ["c9", "cloud9", "cloud 9"],
    "team liquid": ["tl", "liquid", "team liquid"],
    "100 thieves": ["100t", "100 thieves", "hundred thieves"],
    
    # LPL
    "jdg": ["jdg", "jd gaming"],
    "bilibili gaming": ["blg", "bilibili", "bilibili gaming"],
    "weibo gaming": ["wbg", "weibo", "weibo gaming"],
    "top esports": ["tes", "top", "top esports"],
    
    # CS2
    "navi": ["navi", "natus vincere"],
    "faze": ["faze", "faze clan"],
    "g2": ["g2", "g2 esports"],
    "vitality": ["vit", "vitality", "team vitality"],
}
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-02  
**Author:** Hydra Quant Research
