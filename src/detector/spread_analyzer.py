"""Spread analyzer for detecting arbitrage opportunities."""

from dataclasses import dataclass
from datetime import datetime

import structlog

from src.config.constants import MARKET_CLOSE_BUFFER_SECONDS
from src.models import ArbitrageOpportunity, Market

logger = structlog.get_logger(__name__)


@dataclass
class SpreadAnalysisResult:
    """Result of spread analysis."""

    is_profitable: bool
    total_cost: float
    profit_per_contract: float
    up_price: float
    down_price: float
    up_liquidity: float
    down_liquidity: float
    max_contracts: float
    reason: str = ""


class SpreadAnalyzer:
    """
    Analyzes spreads between UP and DOWN tokens to find arbitrage opportunities.
    
    The core strategy: if UP + DOWN prices < $1.00, we can buy both and guarantee profit
    regardless of the outcome, since the winning side always pays $1.00.
    """

    def __init__(
        self,
        min_profit_threshold: float = 0.04,
        min_liquidity: float = 100.0,
        max_position_size: float = 1000.0,
    ) -> None:
        """
        Initialize spread analyzer.

        Args:
            min_profit_threshold: Minimum profit per contract (e.g., 0.04 = 4 cents)
            min_liquidity: Minimum liquidity required on each side
            max_position_size: Maximum position size in USDC
        """
        self.min_profit_threshold = min_profit_threshold
        self.min_liquidity = min_liquidity
        self.max_position_size = max_position_size

    def analyze(
        self,
        market: Market,
        up_price: float,
        down_price: float,
        up_liquidity: float,
        down_liquidity: float,
    ) -> SpreadAnalysisResult:
        """
        Analyze a market's spread for arbitrage opportunity.

        Args:
            market: Market to analyze
            up_price: Current best ask price for UP token
            down_price: Current best ask price for DOWN token
            up_liquidity: Available liquidity at UP price
            down_liquidity: Available liquidity at DOWN price

        Returns:
            SpreadAnalysisResult with profitability assessment
        """
        # Calculate total cost and profit
        total_cost = up_price + down_price
        profit_per_contract = 1.0 - total_cost

        # Calculate max contracts based on liquidity and position limits
        available_liquidity = min(up_liquidity, down_liquidity)
        max_contracts_by_liquidity = available_liquidity / max(total_cost, 0.01)
        max_contracts_by_limit = self.max_position_size / max(total_cost, 0.01)
        max_contracts = min(max_contracts_by_liquidity, max_contracts_by_limit)

        # Check profitability conditions
        if total_cost >= 1.0:
            return SpreadAnalysisResult(
                is_profitable=False,
                total_cost=total_cost,
                profit_per_contract=profit_per_contract,
                up_price=up_price,
                down_price=down_price,
                up_liquidity=up_liquidity,
                down_liquidity=down_liquidity,
                max_contracts=0,
                reason="Total cost >= $1.00 (no arbitrage available)",
            )

        if profit_per_contract < self.min_profit_threshold:
            return SpreadAnalysisResult(
                is_profitable=False,
                total_cost=total_cost,
                profit_per_contract=profit_per_contract,
                up_price=up_price,
                down_price=down_price,
                up_liquidity=up_liquidity,
                down_liquidity=down_liquidity,
                max_contracts=0,
                reason=f"Profit {profit_per_contract:.4f} below threshold {self.min_profit_threshold}",
            )

        if min(up_liquidity, down_liquidity) < self.min_liquidity:
            return SpreadAnalysisResult(
                is_profitable=False,
                total_cost=total_cost,
                profit_per_contract=profit_per_contract,
                up_price=up_price,
                down_price=down_price,
                up_liquidity=up_liquidity,
                down_liquidity=down_liquidity,
                max_contracts=0,
                reason=f"Insufficient liquidity (min: {min(up_liquidity, down_liquidity):.2f} < {self.min_liquidity})",
            )

        # Check time to close
        time_to_close = market.time_to_close_seconds
        if time_to_close is not None and time_to_close < MARKET_CLOSE_BUFFER_SECONDS:
            return SpreadAnalysisResult(
                is_profitable=False,
                total_cost=total_cost,
                profit_per_contract=profit_per_contract,
                up_price=up_price,
                down_price=down_price,
                up_liquidity=up_liquidity,
                down_liquidity=down_liquidity,
                max_contracts=0,
                reason=f"Market closes in {time_to_close:.0f}s (buffer: {MARKET_CLOSE_BUFFER_SECONDS}s)",
            )

        return SpreadAnalysisResult(
            is_profitable=True,
            total_cost=total_cost,
            profit_per_contract=profit_per_contract,
            up_price=up_price,
            down_price=down_price,
            up_liquidity=up_liquidity,
            down_liquidity=down_liquidity,
            max_contracts=max_contracts,
            reason="Profitable arbitrage opportunity",
        )

    def create_opportunity(
        self,
        market: Market,
        result: SpreadAnalysisResult,
    ) -> ArbitrageOpportunity | None:
        """
        Create an ArbitrageOpportunity from analysis result.

        Args:
            market: The market being analyzed
            result: Spread analysis result

        Returns:
            ArbitrageOpportunity if profitable, None otherwise
        """
        if not result.is_profitable:
            return None

        opportunity = ArbitrageOpportunity(
            market=market,
            up_price=result.up_price,
            down_price=result.down_price,
            total_cost=result.total_cost,
            profit_per_contract=result.profit_per_contract,
            up_liquidity=result.up_liquidity,
            down_liquidity=result.down_liquidity,
            max_contracts=result.max_contracts,
            timestamp=datetime.now(),
        )
        opportunity.calculate_score()

        logger.info(
            "Arbitrage opportunity found",
            market_id=market.id,
            asset=market.asset,
            up_price=result.up_price,
            down_price=result.down_price,
            total_cost=result.total_cost,
            profit=result.profit_per_contract,
            max_contracts=result.max_contracts,
            score=opportunity.score,
        )

        return opportunity

    def analyze_orderbook(
        self,
        market: Market,
        up_bids: list[tuple[float, float]],
        up_asks: list[tuple[float, float]],
        down_bids: list[tuple[float, float]],
        down_asks: list[tuple[float, float]],
    ) -> SpreadAnalysisResult:
        """
        Analyze spread using full orderbook data.

        Uses best ask prices for buying both sides.

        Args:
            market: Market to analyze
            up_bids: UP token bids [(price, size), ...]
            up_asks: UP token asks [(price, size), ...]
            down_bids: DOWN token bids [(price, size), ...]
            down_asks: DOWN token asks [(price, size), ...]

        Returns:
            SpreadAnalysisResult
        """
        # Get best asks (we're buying)
        if not up_asks or not down_asks:
            return SpreadAnalysisResult(
                is_profitable=False,
                total_cost=0,
                profit_per_contract=0,
                up_price=0,
                down_price=0,
                up_liquidity=0,
                down_liquidity=0,
                max_contracts=0,
                reason="No asks available on one or both sides",
            )

        up_best_ask_price = up_asks[0][0]
        up_best_ask_size = up_asks[0][1]
        down_best_ask_price = down_asks[0][0]
        down_best_ask_size = down_asks[0][1]

        # Calculate total liquidity at best ask (could aggregate multiple levels)
        up_liquidity = sum(size for price, size in up_asks if price <= up_best_ask_price * 1.01)
        down_liquidity = sum(size for price, size in down_asks if price <= down_best_ask_price * 1.01)

        return self.analyze(
            market=market,
            up_price=up_best_ask_price,
            down_price=down_best_ask_price,
            up_liquidity=up_liquidity,
            down_liquidity=down_liquidity,
        )
