"""
Real-time Polymarket data feed for training and evaluation.
NO TRADING - Read only for ML training.
"""
import asyncio
import aiohttp
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import json


@dataclass
class MarketTick:
    """Single market tick data"""
    timestamp: float
    market_id: str
    token_id: str
    question: str
    outcome: str  # YES or NO
    best_bid: float
    best_ask: float
    mid_price: float
    spread: float
    bid_size: float
    ask_size: float
    volume_24h: float
    liquidity: float
    last_trade_price: Optional[float] = None
    price_change_1m: float = 0.0
    price_change_5m: float = 0.0


@dataclass 
class OrderBookSnapshot:
    """Order book snapshot"""
    timestamp: float
    token_id: str
    bids: List[Dict[str, float]]  # [{price, size}]
    asks: List[Dict[str, float]]
    spread: float
    mid_price: float


@dataclass
class TradeEvent:
    """Trade event from the market"""
    timestamp: float
    token_id: str
    price: float
    size: float
    side: str  # BUY or SELL
    maker: str
    taker: str


class PolymarketFeed:
    """
    Real-time data feed from Polymarket CLOB API.
    Read-only - no trading functionality.
    """
    
    CLOB_BASE = "https://clob.polymarket.com"
    GAMMA_BASE = "https://gamma-api.polymarket.com"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.price_history: Dict[str, List[Dict]] = {}  # token_id -> [{ts, price}]
        self.callbacks: List[Callable[[MarketTick], None]] = []
        self.running = False
        self._rate_limit_delay = 0.5  # 500ms between requests
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
            
    async def _request(self, url: str, params: Dict = None) -> Optional[Dict]:
        """Make rate-limited request"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            await asyncio.sleep(self._rate_limit_delay)
            async with self.session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    print(f"⚠️ Rate limited, waiting 5s...")
                    await asyncio.sleep(5)
                    return None
                else:
                    return None
        except Exception as e:
            print(f"Request error: {e}")
            return None
            
    # ============== Market Discovery ==============
    
    async def get_active_markets(self, limit: int = 50) -> List[Dict]:
        """Get active markets from Gamma API"""
        url = f"{self.GAMMA_BASE}/markets"
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false"
        }
        
        data = await self._request(url, params)
        if not data:
            return []
            
        markets = []
        for m in data:
            try:
                markets.append({
                    "condition_id": m.get("conditionId", ""),
                    "question": m.get("question", ""),
                    "slug": m.get("slug", ""),
                    "volume_24h": float(m.get("volume24hr", 0) or 0),
                    "liquidity": float(m.get("liquidityClob", 0) or 0),
                    "outcomes": m.get("outcomes", []),
                    "tokens": m.get("clobTokenIds", [])
                })
            except:
                continue
                
        return markets
    
    async def get_flash_markets(self) -> List[Dict]:
        """Get flash/minute markets (high frequency)"""
        url = f"{self.GAMMA_BASE}/markets"
        params = {
            "active": "true",
            "tag": "flash",
            "limit": 20
        }
        
        data = await self._request(url, params)
        if not data:
            # Fallback: search for minute-based markets
            params = {
                "active": "true",
                "closed": "false",
                "limit": 100
            }
            data = await self._request(url, params) or []
            
        # Filter for flash-like markets
        flash_markets = []
        flash_keywords = ["minute", "1-min", "5-min", "flash", "btc", "eth", "sol", "price"]
        
        for m in data:
            question = m.get("question", "").lower()
            if any(kw in question for kw in flash_keywords):
                flash_markets.append({
                    "condition_id": m.get("conditionId", ""),
                    "question": m.get("question", ""),
                    "slug": m.get("slug", ""),
                    "tokens": m.get("clobTokenIds", []),
                    "end_date": m.get("endDate", "")
                })
                
        return flash_markets
    
    # ============== Price Data ==============
    
    async def get_orderbook(self, token_id: str) -> Optional[OrderBookSnapshot]:
        """Get current order book for a token"""
        url = f"{self.CLOB_BASE}/book"
        params = {"token_id": token_id}
        
        data = await self._request(url, params)
        if not data:
            return None
            
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            # Parse order book
            bid_list = [{"price": float(b.get("price", 0)), "size": float(b.get("size", 0))} for b in bids[:10]]
            ask_list = [{"price": float(a.get("price", 0)), "size": float(a.get("size", 0))} for a in asks[:10]]
            
            best_bid = bid_list[0]["price"] if bid_list else 0
            best_ask = ask_list[0]["price"] if ask_list else 1
            
            return OrderBookSnapshot(
                timestamp=time.time(),
                token_id=token_id,
                bids=bid_list,
                asks=ask_list,
                spread=best_ask - best_bid,
                mid_price=(best_bid + best_ask) / 2
            )
        except Exception as e:
            print(f"Orderbook parse error: {e}")
            return None
            
    async def get_midpoint(self, token_id: str) -> Optional[Dict]:
        """Get midpoint price for a token"""
        url = f"{self.CLOB_BASE}/midpoint"
        params = {"token_id": token_id}
        
        data = await self._request(url, params)
        if data and "mid" in data:
            return {
                "mid": float(data["mid"]),
                "timestamp": time.time()
            }
        return None
        
    async def get_price(self, token_id: str) -> Optional[Dict]:
        """Get current price info for a token"""
        url = f"{self.CLOB_BASE}/price"
        params = {"token_id": token_id, "side": "buy"}
        
        data = await self._request(url, params)
        if data and "price" in data:
            return {
                "price": float(data["price"]),
                "side": "buy",
                "timestamp": time.time()
            }
        return None
    
    # ============== Market Tick Assembly ==============
    
    async def get_market_tick(self, token_id: str, question: str = "", outcome: str = "YES") -> Optional[MarketTick]:
        """Get complete market tick with all data"""
        orderbook = await self.get_orderbook(token_id)
        if not orderbook:
            return None
            
        # Calculate price changes from history
        price_change_1m = 0.0
        price_change_5m = 0.0
        
        history = self.price_history.get(token_id, [])
        now = time.time()
        
        if history:
            # 1 minute ago
            prices_1m = [h["price"] for h in history if now - h["ts"] <= 60]
            if prices_1m:
                price_change_1m = orderbook.mid_price - prices_1m[0]
                
            # 5 minutes ago
            prices_5m = [h["price"] for h in history if now - h["ts"] <= 300]
            if prices_5m:
                price_change_5m = orderbook.mid_price - prices_5m[0]
        
        # Update history
        if token_id not in self.price_history:
            self.price_history[token_id] = []
        self.price_history[token_id].append({"ts": now, "price": orderbook.mid_price})
        
        # Keep only last 10 minutes
        self.price_history[token_id] = [
            h for h in self.price_history[token_id] 
            if now - h["ts"] <= 600
        ]
        
        return MarketTick(
            timestamp=now,
            market_id="",
            token_id=token_id,
            question=question,
            outcome=outcome,
            best_bid=orderbook.bids[0]["price"] if orderbook.bids else 0,
            best_ask=orderbook.asks[0]["price"] if orderbook.asks else 1,
            mid_price=orderbook.mid_price,
            spread=orderbook.spread,
            bid_size=sum(b["size"] for b in orderbook.bids),
            ask_size=sum(a["size"] for a in orderbook.asks),
            volume_24h=0,  # Would need separate call
            liquidity=sum(b["size"] for b in orderbook.bids) + sum(a["size"] for a in orderbook.asks),
            price_change_1m=price_change_1m,
            price_change_5m=price_change_5m
        )
    
    # ============== Live Feed ==============
    
    def on_tick(self, callback: Callable[[MarketTick], None]):
        """Register callback for new ticks"""
        self.callbacks.append(callback)
        
    async def start_feed(self, token_ids: List[str], interval: float = 2.0):
        """Start polling feed for given tokens"""
        self.running = True
        print(f"📡 Starting feed for {len(token_ids)} tokens...")
        
        while self.running:
            for token_id in token_ids:
                if not self.running:
                    break
                    
                tick = await self.get_market_tick(token_id)
                if tick:
                    for callback in self.callbacks:
                        try:
                            callback(tick)
                        except Exception as e:
                            print(f"Callback error: {e}")
                            
            await asyncio.sleep(interval)
            
    def stop_feed(self):
        """Stop the feed"""
        self.running = False
        print("📡 Feed stopped")


class DataCollector:
    """
    Collects and stores market data for ML training.
    """
    
    def __init__(self, output_dir: str = "data/market_data"):
        self.output_dir = output_dir
        self.ticks: List[Dict] = []
        self.trades: List[Dict] = []
        
    def record_tick(self, tick: MarketTick):
        """Record a market tick"""
        self.ticks.append({
            "timestamp": tick.timestamp,
            "token_id": tick.token_id,
            "mid_price": tick.mid_price,
            "spread": tick.spread,
            "bid_size": tick.bid_size,
            "ask_size": tick.ask_size,
            "price_change_1m": tick.price_change_1m,
            "price_change_5m": tick.price_change_5m
        })
        
    def save(self, filename: str = None):
        """Save collected data"""
        import os
        os.makedirs(self.output_dir, exist_ok=True)
        
        if not filename:
            filename = f"ticks_{int(time.time())}.json"
            
        path = os.path.join(self.output_dir, filename)
        with open(path, 'w') as f:
            json.dump({
                "ticks": self.ticks,
                "collected_at": datetime.now().isoformat(),
                "count": len(self.ticks)
            }, f, indent=2)
            
        print(f"💾 Saved {len(self.ticks)} ticks to {path}")
        return path


# ============== Test Functions ==============

async def test_feed():
    """Test the data feed"""
    print("🔍 Testing Polymarket Feed...")
    
    async with PolymarketFeed() as feed:
        # Get active markets
        print("\n📊 Active Markets:")
        markets = await feed.get_active_markets(limit=5)
        for m in markets[:3]:
            print(f"  - {m['question'][:60]}...")
            print(f"    Volume: ${m['volume_24h']:,.0f} | Liquidity: ${m['liquidity']:,.0f}")
            
        # Get flash markets
        print("\n⚡ Flash/Minute Markets:")
        flash = await feed.get_flash_markets()
        for m in flash[:5]:
            print(f"  - {m['question'][:60]}...")
            if m['tokens']:
                print(f"    Token: {m['tokens'][0][:20]}...")
                
        # Get orderbook for first token
        if markets and markets[0]['tokens']:
            token_id = markets[0]['tokens'][0]
            print(f"\n📖 Order Book for: {token_id[:20]}...")
            
            book = await feed.get_orderbook(token_id)
            if book:
                print(f"  Mid: {book.mid_price:.4f} | Spread: {book.spread:.4f}")
                print(f"  Bids: {len(book.bids)} | Asks: {len(book.asks)}")
                
            tick = await feed.get_market_tick(token_id, markets[0]['question'])
            if tick:
                print(f"\n📈 Market Tick:")
                print(f"  Mid: {tick.mid_price:.4f}")
                print(f"  Spread: {tick.spread:.4f}")
                print(f"  Liquidity: ${tick.liquidity:,.2f}")


if __name__ == "__main__":
    asyncio.run(test_feed())
