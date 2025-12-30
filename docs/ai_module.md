# AI Trading Module

## Overview

This module integrates AI-powered market analysis into the Polymarket trading bot. It uses Google's Gemini AI to predict market direction (UP/DOWN) for flash markets.

## Architecture

```
src/ai/
├── __init__.py           # Module exports
├── gemini_client.py      # Optimized Gemini API client
├── bias_analyzer.py      # Market direction predictor
└── cache.py              # TTL-based decision caching

src/trading/
└── ai_strategy.py        # AI-powered trading strategy
```

## Components

### 1. GeminiClient (`gemini_client.py`)

Low-level client for Gemini API with:
- **Automatic retry** with exponential backoff
- **Rate limit handling** (429 errors)
- **Connection pooling** (reuses model instance)
- **Latency tracking**

```python
from src.ai.gemini_client import GeminiClient, GeminiModel

client = GeminiClient(model=GeminiModel.FLASH_25)
response = client.generate("Will BTC go UP or DOWN?")
print(response.content)  # "UP" or "DOWN"
print(response.latency_ms)  # ~400-500ms
```

### 2. BiasAnalyzer (`bias_analyzer.py`)

High-level market direction analyzer:
- **Cached decisions** (5-minute TTL)
- **Multiple prompt strategies** (simple, detailed, contrarian, momentum)
- **Confidence scoring**
- **BTC/ETH specific analysis**

```python
from src.ai.bias_analyzer import BiasAnalyzer, get_market_bias

# Full analyzer
analyzer = BiasAnalyzer()
decision = analyzer.analyze({
    "price_change": "+2.5%",
    "volume": "high",
    "trend": "bullish"
})
print(decision.bias)       # MarketBias.UP
print(decision.confidence) # 0.8

# Quick helper
bias = get_market_bias(price_change_pct=2.5, volume="high", trend="bullish")
print(bias)  # "UP"
```

### 3. AICache (`cache.py`)

Thread-safe TTL cache:
- **Configurable TTL** per entry type
- **Automatic cleanup** of expired entries
- **Statistics tracking**
- **Sliding window** support

```python
from src.ai.cache import AICache

cache = AICache(default_ttl=300)  # 5 minutes
cache.set("bias_btc", "UP", category="bias")
value = cache.get("bias_btc")  # Returns "UP" or None if expired
```

### 4. AIFlashStrategy (`ai_strategy.py`)

Complete trading strategy:
- **Trade signal generation**
- **Position sizing** based on confidence
- **Expected value calculation**
- **Risk/reward analysis**

```python
from src.trading.ai_strategy import AIFlashStrategy

strategy = AIFlashStrategy(max_position_usdc=5.0)

signal = await strategy.get_trade_signal(
    market_data={"price_change": "+2%", "volume": "high", "trend": "bullish"},
    market_info={"up_price": 0.45, "down_price": 0.55}
)

if signal.is_actionable:
    print(f"Action: {signal.action}")  # BUY_UP or BUY_DOWN
    print(f"Size: ${signal.recommended_size_usdc}")
    print(f"EV: ${signal.expected_value}")
```

## Configuration

### Environment Variables

```env
# Required
GEMINI_API_KEY=your_gemini_api_key

# Optional (for GitHub Models fallback)
GITHUB_PAT=your_github_token
```

### Strategy Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MIN_CONFIDENCE` | 0.6 | Minimum confidence to trade |
| `MAX_POSITION_USDC` | 5.0 | Maximum position size |
| `BIAS_UPDATE_INTERVAL` | 300s | Time between AI calls |
| `CACHE_TTL` | 300s | Cache duration for decisions |

## Performance

### Latency Benchmarks (gemini-2.5-flash)

| Metric | Value |
|--------|-------|
| Average | ~400-500ms |
| P50 | ~400ms |
| P95 | ~600ms |
| P99 | ~800ms |

### Rate Limits

Gemini free tier has rate limits:
- ~15 requests/minute
- ~1500 requests/day

The cache reduces API calls significantly by caching decisions for 5 minutes.

## Trading Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI TRADING FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. MARKET DATA INPUT                                            │
│     └─► price_change, volume, trend                             │
│                                                                  │
│  2. CHECK CACHE                                                  │
│     └─► If cached bias exists and not expired → use it          │
│                                                                  │
│  3. AI ANALYSIS (if cache miss)                                  │
│     └─► Gemini analyzes data                                    │
│     └─► Returns UP/DOWN with confidence                         │
│     └─► Cache result for 5 minutes                              │
│                                                                  │
│  4. GENERATE TRADE SIGNAL                                        │
│     └─► Calculate position size from confidence                 │
│     └─► Calculate expected value                                │
│     └─► Determine if actionable                                 │
│                                                                  │
│  5. EXECUTE (if actionable)                                      │
│     └─► Send order to Polymarket                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Position Sizing

Position size is determined by AI confidence:

| Confidence | Size (% of max) |
|------------|-----------------|
| 90%+ | 100% |
| 80-90% | 75% |
| 70-80% | 50% |
| 60-70% | 25% |
| <60% | No trade |

## Expected Value Calculation

```
EV = confidence × (1 - entry_price) - (1 - confidence) × entry_price
```

Example:
- Confidence: 70%
- Entry price: $0.45 (for UP token)
- Position: $5

```
EV = 0.70 × (1 - 0.45) - 0.30 × 0.45
EV = 0.70 × 0.55 - 0.30 × 0.45
EV = 0.385 - 0.135
EV = +$0.25 per $1 risked
```

## Usage Examples

### Basic Usage

```python
import asyncio
from src.trading.ai_strategy import AIFlashStrategy

async def main():
    strategy = AIFlashStrategy()
    
    signal = await strategy.get_trade_signal({
        "asset": "BTC",
        "price_change": "+1.5%",
        "volume": "high",
        "trend": "bullish"
    })
    
    print(f"Action: {signal.action.value}")
    print(f"Confidence: {signal.confidence}")
    print(f"Size: ${signal.recommended_size_usdc}")

asyncio.run(main())
```

### With Real Market Data

```python
async def trade_flash_market():
    strategy = AIFlashStrategy()
    
    # Get real BTC price data
    btc_data = await fetch_btc_price_data()  # Your implementation
    
    # Get flash market info from Polymarket
    market_info = await get_flash_market_info()  # Your implementation
    
    signal = await strategy.get_trade_signal(
        market_data=btc_data,
        market_info=market_info
    )
    
    if signal.is_actionable:
        await execute_trade(signal)  # Your implementation
```

## Testing

Run the test suite:

```bash
python tools/test_ai_strategy.py
```

This tests:
1. Gemini client connectivity
2. Cache functionality
3. Bias analyzer accuracy
4. Strategy signal generation
5. Latency benchmarks

## Troubleshooting

### Rate Limit Errors (429)

The module automatically handles rate limits with exponential backoff. If you see frequent rate limit errors:
- Increase `BIAS_UPDATE_INTERVAL` 
- Use the cache more aggressively
- Consider upgrading Gemini plan

### IP Restriction Errors (403)

If you see IP restriction errors:
1. Go to Google Cloud Console
2. Edit your API key
3. Remove IP restrictions or add your IP

### Empty Responses

Gemini sometimes returns empty responses for certain prompts. The module handles this with retry logic. If persistent:
- Simplify your prompts
- Try a different model (gemini-2.0-flash)

## Model Comparison

| Model | Latency | Accuracy | Stability |
|-------|---------|----------|-----------|
| gemini-2.5-flash | ~430ms | 80% | ✅ Stable |
| gemini-2.0-flash | ~360ms | 100%* | ⚠️ Rate limits |
| gemini-2.0-flash-lite | ~440ms | 80% | ✅ Stable |
| gemini-3-flash-preview | ~740ms | 60% | ⚠️ Preview |

*Based on limited test set

**Recommendation**: Use `gemini-2.5-flash` for production.
