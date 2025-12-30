"""Enhanced paper trading simulation with realistic slippage and liquidity."""

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class OrderbookLevel:
    """Single level in the orderbook."""
    price: float
    size: float


@dataclass
class SimulatedOrderbook:
    """Simulated orderbook for paper trading."""
    token_id: str
    bids: list[OrderbookLevel] = field(default_factory=list)
    asks: list[OrderbookLevel] = field(default_factory=list)
    mid_price: float = 0.5
    spread: float = 0.02
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def best_bid(self) -> float:
        """Best bid price."""
        return self.bids[0].price if self.bids else self.mid_price - self.spread / 2
    
    @property
    def best_ask(self) -> float:
        """Best ask price."""
        return self.asks[0].price if self.asks else self.mid_price + self.spread / 2
    
    @property
    def total_bid_liquidity(self) -> float:
        """Total bid-side liquidity."""
        return sum(level.size for level in self.bids)
    
    @property
    def total_ask_liquidity(self) -> float:
        """Total ask-side liquidity."""
        return sum(level.size for level in self.asks)


@dataclass
class SimulationResult:
    """Result of a simulated order execution."""
    
    success: bool
    order_id: str
    filled_size: float
    avg_price: float
    slippage: float
    slippage_pct: float
    fee: float
    latency_ms: float
    error: str | None = None
    fills: list[dict[str, Any]] = field(default_factory=list)
    
    @property
    def total_cost(self) -> float:
        """Total cost including fees."""
        return self.filled_size * self.avg_price + self.fee


class SlippageSimulator:
    """
    Simulates realistic order execution with slippage and liquidity constraints.
    
    Models:
    - Order book depth and price impact
    - Network latency variation
    - Fee structure (maker/taker)
    - Partial fills
    - Failed orders
    """
    
    def __init__(
        self,
        base_fee_rate: float = 0.0,  # Polymarket has 0% trading fees currently
        taker_fee_rate: float = 0.02,  # But we simulate 2% taker fee for safety margin
        maker_fee_rate: float = 0.0,
        avg_latency_ms: float = 100.0,
        latency_std_ms: float = 50.0,
        failure_rate: float = 0.02,  # 2% order failure rate
        partial_fill_rate: float = 0.05,  # 5% partial fill rate
    ) -> None:
        """
        Initialize slippage simulator.
        
        Args:
            base_fee_rate: Base fee rate for all orders
            taker_fee_rate: Additional fee for market orders
            maker_fee_rate: Additional fee for limit orders
            avg_latency_ms: Average network latency
            latency_std_ms: Standard deviation of latency
            failure_rate: Probability of order failure
            partial_fill_rate: Probability of partial fill
        """
        self.base_fee_rate = base_fee_rate
        self.taker_fee_rate = taker_fee_rate
        self.maker_fee_rate = maker_fee_rate
        self.avg_latency_ms = avg_latency_ms
        self.latency_std_ms = latency_std_ms
        self.failure_rate = failure_rate
        self.partial_fill_rate = partial_fill_rate
        
        # Simulated orderbooks
        self._orderbooks: dict[str, SimulatedOrderbook] = {}
        
        # Execution statistics
        self._total_orders = 0
        self._failed_orders = 0
        self._partial_fills = 0
        self._total_slippage = 0.0
    
    def generate_orderbook(
        self,
        token_id: str,
        mid_price: float = 0.5,
        spread: float = 0.02,
        depth_levels: int = 10,
        avg_level_size: float = 500.0,
    ) -> SimulatedOrderbook:
        """
        Generate a simulated orderbook.
        
        Args:
            token_id: Token identifier
            mid_price: Mid price (0-1 for binary outcomes)
            spread: Bid-ask spread
            depth_levels: Number of price levels
            avg_level_size: Average size per level
            
        Returns:
            SimulatedOrderbook
        """
        bids = []
        asks = []
        
        # Generate bid levels (decreasing prices)
        bid_price = mid_price - spread / 2
        for i in range(depth_levels):
            # Liquidity decreases away from mid
            size = avg_level_size * (1 - i * 0.1) * random.uniform(0.5, 1.5)
            bids.append(OrderbookLevel(
                price=round(bid_price - i * 0.01, 4),
                size=round(size, 2),
            ))
        
        # Generate ask levels (increasing prices)
        ask_price = mid_price + spread / 2
        for i in range(depth_levels):
            size = avg_level_size * (1 - i * 0.1) * random.uniform(0.5, 1.5)
            asks.append(OrderbookLevel(
                price=round(ask_price + i * 0.01, 4),
                size=round(size, 2),
            ))
        
        orderbook = SimulatedOrderbook(
            token_id=token_id,
            bids=bids,
            asks=asks,
            mid_price=mid_price,
            spread=spread,
        )
        
        self._orderbooks[token_id] = orderbook
        return orderbook
    
    def update_orderbook(
        self,
        token_id: str,
        mid_price: float | None = None,
        volatility: float = 0.01,
    ) -> SimulatedOrderbook:
        """
        Update an existing orderbook with price movement.
        
        Args:
            token_id: Token identifier
            mid_price: New mid price (or None for random walk)
            volatility: Price volatility for random walk
            
        Returns:
            Updated orderbook
        """
        if token_id not in self._orderbooks:
            return self.generate_orderbook(token_id, mid_price or 0.5)
        
        ob = self._orderbooks[token_id]
        
        if mid_price is None:
            # Random walk
            change = random.gauss(0, volatility)
            mid_price = max(0.01, min(0.99, ob.mid_price + change))
        
        # Regenerate with new mid
        return self.generate_orderbook(
            token_id,
            mid_price=mid_price,
            spread=ob.spread,
        )
    
    def simulate_market_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        amount_usdc: float,
        orderbook: SimulatedOrderbook | None = None,
    ) -> SimulationResult:
        """
        Simulate a market order with realistic slippage.
        
        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            amount_usdc: Amount in USDC
            orderbook: Optional orderbook (uses stored if not provided)
            
        Returns:
            SimulationResult with execution details
        """
        import uuid
        
        self._total_orders += 1
        
        # Simulate latency
        latency = max(10, random.gauss(self.avg_latency_ms, self.latency_std_ms))
        
        # Check for failure
        if random.random() < self.failure_rate:
            self._failed_orders += 1
            logger.debug("Simulated order failure", token_id=token_id[:20])
            return SimulationResult(
                success=False,
                order_id="",
                filled_size=0,
                avg_price=0,
                slippage=0,
                slippage_pct=0,
                fee=0,
                latency_ms=latency,
                error="Simulated order failure (market conditions)",
            )
        
        # Get or generate orderbook
        if orderbook is None:
            if token_id in self._orderbooks:
                orderbook = self._orderbooks[token_id]
            else:
                orderbook = self.generate_orderbook(token_id)
        
        # Determine which side of the book to consume
        levels = orderbook.asks if side == "BUY" else orderbook.bids
        
        if not levels:
            return SimulationResult(
                success=False,
                order_id="",
                filled_size=0,
                avg_price=0,
                slippage=0,
                slippage_pct=0,
                fee=0,
                latency_ms=latency,
                error="No liquidity available",
            )
        
        # Calculate fills across levels
        remaining = amount_usdc
        fills = []
        total_contracts = 0
        total_cost = 0
        
        for level in levels:
            if remaining <= 0:
                break
            
            # How much can we fill at this level?
            level_value = level.size * level.price
            fill_value = min(remaining, level_value)
            fill_contracts = fill_value / level.price
            
            fills.append({
                "price": level.price,
                "size": fill_contracts,
                "value": fill_value,
            })
            
            total_contracts += fill_contracts
            total_cost += fill_value
            remaining -= fill_value
        
        # Check for partial fill
        fill_pct = (amount_usdc - remaining) / amount_usdc
        is_partial = fill_pct < 0.99
        
        if is_partial or random.random() < self.partial_fill_rate:
            # Force partial fill
            self._partial_fills += 1
            fill_pct = random.uniform(0.7, 0.95)
            total_contracts *= fill_pct
            total_cost *= fill_pct
        
        if total_contracts == 0:
            return SimulationResult(
                success=False,
                order_id="",
                filled_size=0,
                avg_price=0,
                slippage=0,
                slippage_pct=0,
                fee=0,
                latency_ms=latency,
                error="Insufficient liquidity",
            )
        
        # Calculate average price and slippage
        avg_price = total_cost / total_contracts
        best_price = levels[0].price
        slippage = avg_price - best_price if side == "BUY" else best_price - avg_price
        slippage_pct = (slippage / best_price) * 100 if best_price > 0 else 0
        
        # Calculate fees
        fee = total_cost * (self.base_fee_rate + self.taker_fee_rate)
        
        self._total_slippage += abs(slippage_pct)
        
        logger.debug(
            "Simulated market order",
            token_id=token_id[:20] if len(token_id) > 20 else token_id,
            side=side,
            amount=amount_usdc,
            filled=total_contracts,
            avg_price=round(avg_price, 4),
            slippage_pct=round(slippage_pct, 4),
            fee=round(fee, 4),
        )
        
        return SimulationResult(
            success=True,
            order_id=f"paper-{uuid.uuid4()}",
            filled_size=round(total_contracts, 4),
            avg_price=round(avg_price, 4),
            slippage=round(slippage, 6),
            slippage_pct=round(slippage_pct, 4),
            fee=round(fee, 4),
            latency_ms=round(latency, 2),
            fills=fills,
        )
    
    def simulate_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        orderbook: SimulatedOrderbook | None = None,
    ) -> SimulationResult:
        """
        Simulate a limit order.
        
        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            price: Limit price
            size: Number of contracts
            orderbook: Optional orderbook
            
        Returns:
            SimulationResult
        """
        import uuid
        
        self._total_orders += 1
        latency = max(10, random.gauss(self.avg_latency_ms, self.latency_std_ms))
        
        if orderbook is None:
            orderbook = self._orderbooks.get(token_id) or self.generate_orderbook(token_id)
        
        # Check if limit order would be filled immediately
        if side == "BUY":
            best_ask = orderbook.best_ask
            if price >= best_ask:
                # Crosses the spread - behaves like market order
                return self.simulate_market_order(token_id, side, size * price, orderbook)
            # Otherwise, order sits on book (simulated as filled for paper trading)
            fill_probability = 0.8  # 80% chance of fill for paper trading
        else:
            best_bid = orderbook.best_bid
            if price <= best_bid:
                return self.simulate_market_order(token_id, side, size * price, orderbook)
            fill_probability = 0.8
        
        if random.random() > fill_probability:
            return SimulationResult(
                success=False,
                order_id=f"paper-{uuid.uuid4()}",
                filled_size=0,
                avg_price=0,
                slippage=0,
                slippage_pct=0,
                fee=0,
                latency_ms=latency,
                error="Limit order not filled (simulated)",
            )
        
        # Limit order filled at limit price (no slippage by definition)
        fee = size * price * (self.base_fee_rate + self.maker_fee_rate)
        
        return SimulationResult(
            success=True,
            order_id=f"paper-{uuid.uuid4()}",
            filled_size=size,
            avg_price=price,
            slippage=0,
            slippage_pct=0,
            fee=round(fee, 4),
            latency_ms=round(latency, 2),
        )
    
    def get_statistics(self) -> dict[str, Any]:
        """Get simulation statistics."""
        return {
            "total_orders": self._total_orders,
            "failed_orders": self._failed_orders,
            "failure_rate": round(self._failed_orders / self._total_orders * 100, 2) if self._total_orders > 0 else 0,
            "partial_fills": self._partial_fills,
            "partial_fill_rate": round(self._partial_fills / self._total_orders * 100, 2) if self._total_orders > 0 else 0,
            "avg_slippage_pct": round(self._total_slippage / self._total_orders, 4) if self._total_orders > 0 else 0,
        }
    
    def reset_statistics(self) -> None:
        """Reset simulation statistics."""
        self._total_orders = 0
        self._failed_orders = 0
        self._partial_fills = 0
        self._total_slippage = 0.0


# Global simulator instance
_simulator: SlippageSimulator | None = None


def get_simulator() -> SlippageSimulator:
    """Get global simulator instance."""
    global _simulator
    if _simulator is None:
        _simulator = SlippageSimulator()
    return _simulator
