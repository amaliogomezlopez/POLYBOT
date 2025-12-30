"""Position manager for delta-neutral arbitrage positions."""

import uuid
from datetime import datetime
from typing import Any

import structlog

from src.config.constants import OrderType, PositionState, Side
from src.models import ArbitrageOpportunity, Market, Position, Trade
from src.trading.order_executor import OrderExecutor, OrderResult

logger = structlog.get_logger(__name__)


class PositionManager:
    """
    Manages delta-neutral positions across UP and DOWN tokens.
    
    Ensures positions are balanced and tracks P&L.
    """

    def __init__(self, order_executor: OrderExecutor) -> None:
        """
        Initialize position manager.

        Args:
            order_executor: OrderExecutor instance for trade execution
        """
        self.order_executor = order_executor
        self._positions: dict[str, Position] = {}
        self._trades: list[Trade] = []

    @property
    def open_positions(self) -> list[Position]:
        """Get all open positions."""
        return [
            p for p in self._positions.values()
            if p.state not in (PositionState.SETTLED,)
        ]

    @property
    def total_exposure(self) -> float:
        """Get total USDC exposure across all positions."""
        return sum(p.total_cost for p in self.open_positions)

    async def open_position(
        self,
        opportunity: ArbitrageOpportunity,
        size_usdc: float,
    ) -> Position | None:
        """
        Open a new delta-neutral position.

        Buys both UP and DOWN tokens to create the arbitrage position.

        Args:
            opportunity: The arbitrage opportunity to execute
            size_usdc: Total size in USDC (split between both sides)

        Returns:
            Position if successful, None otherwise
        """
        market = opportunity.market
        if not market.tokens:
            logger.error("Market has no tokens", market_id=market.id)
            return None

        position_id = str(uuid.uuid4())
        
        # Calculate order sizes (equal split for delta-neutral)
        up_amount = size_usdc / 2
        down_amount = size_usdc / 2

        position = Position(
            id=position_id,
            market_id=market.id,
            market=market,
            state=PositionState.PENDING_ENTRY,
            up_token_id=market.tokens.up_token_id,
            down_token_id=market.tokens.down_token_id,
        )

        logger.info(
            "Opening position",
            position_id=position_id,
            market_id=market.id,
            asset=market.asset,
            size_usdc=size_usdc,
        )

        # Execute UP order
        up_result = await self.order_executor.place_market_order(
            token_id=market.tokens.up_token_id,
            side=Side.BUY,
            amount=up_amount,
            order_type=OrderType.FOK,
        )

        if not up_result.success:
            logger.error(
                "UP order failed",
                position_id=position_id,
                error=up_result.error,
            )
            position.state = PositionState.PENDING_ENTRY
            return None

        position.up_order_id = up_result.order_id
        position.up_contracts = up_result.filled_size
        position.up_avg_price = opportunity.up_price
        position.state = PositionState.PARTIAL

        # Record UP trade
        if up_result.order_id:
            up_trade = Trade(
                id=str(uuid.uuid4()),
                position_id=position_id,
                order_id=up_result.order_id,
                market_id=market.id,
                token_id=market.tokens.up_token_id,
                outcome_type="UP",  # type: ignore
                side="BUY",
                price=opportunity.up_price,
                size=up_result.filled_size,
                fee=0.0,  # Would need to get from response
            )
            self._trades.append(up_trade)

        # Execute DOWN order
        down_result = await self.order_executor.place_market_order(
            token_id=market.tokens.down_token_id,
            side=Side.BUY,
            amount=down_amount,
            order_type=OrderType.FOK,
        )

        if not down_result.success:
            logger.warning(
                "DOWN order failed, position is partial",
                position_id=position_id,
                error=down_result.error,
            )
            # Position remains partial - may need manual intervention
            self._positions[position_id] = position
            return position

        position.down_order_id = down_result.order_id
        position.down_contracts = down_result.filled_size
        position.down_avg_price = opportunity.down_price
        position.state = PositionState.COMPLETE

        # Record DOWN trade
        if down_result.order_id:
            down_trade = Trade(
                id=str(uuid.uuid4()),
                position_id=position_id,
                order_id=down_result.order_id,
                market_id=market.id,
                token_id=market.tokens.down_token_id,
                outcome_type="DOWN",  # type: ignore
                side="BUY",
                price=opportunity.down_price,
                size=down_result.filled_size,
                fee=0.0,
            )
            self._trades.append(down_trade)

        # Calculate total cost
        position.total_cost = (
            position.up_contracts * position.up_avg_price +
            position.down_contracts * position.down_avg_price
        )

        self._positions[position_id] = position

        logger.info(
            "Position opened successfully",
            position_id=position_id,
            up_contracts=position.up_contracts,
            down_contracts=position.down_contracts,
            total_cost=position.total_cost,
            expected_profit=position.expected_profit_per_contract * min(
                position.up_contracts, position.down_contracts
            ),
        )

        return position

    async def close_position(self, position_id: str) -> bool:
        """
        Close a position by selling both sides.

        This is typically not needed since positions settle automatically
        when the market resolves.

        Args:
            position_id: Position ID to close

        Returns:
            True if closed successfully
        """
        position = self._positions.get(position_id)
        if not position:
            logger.warning("Position not found", position_id=position_id)
            return False

        if position.state == PositionState.SETTLED:
            logger.info("Position already settled", position_id=position_id)
            return True

        # Sell UP tokens if we have any
        if position.up_contracts > 0:
            up_result = await self.order_executor.place_market_order(
                token_id=position.up_token_id,
                side=Side.SELL,
                amount=position.up_contracts * position.up_avg_price,
                order_type=OrderType.FOK,
            )
            if not up_result.success:
                logger.error("Failed to sell UP tokens", error=up_result.error)
                return False

        # Sell DOWN tokens if we have any
        if position.down_contracts > 0:
            down_result = await self.order_executor.place_market_order(
                token_id=position.down_token_id,
                side=Side.SELL,
                amount=position.down_contracts * position.down_avg_price,
                order_type=OrderType.FOK,
            )
            if not down_result.success:
                logger.error("Failed to sell DOWN tokens", error=down_result.error)
                return False

        position.state = PositionState.SETTLED
        position.settled_at = datetime.now()

        logger.info("Position closed", position_id=position_id)
        return True

    def get_position(self, position_id: str) -> Position | None:
        """Get a position by ID."""
        return self._positions.get(position_id)

    def get_positions_for_market(self, market_id: str) -> list[Position]:
        """Get all positions for a specific market."""
        return [p for p in self._positions.values() if p.market_id == market_id]

    def get_partial_positions(self) -> list[Position]:
        """Get positions that only have one leg filled."""
        return [p for p in self._positions.values() if p.state == PositionState.PARTIAL]

    def calculate_total_unrealized_pnl(self) -> float:
        """Calculate total unrealized P&L across all open positions."""
        return sum(p.unrealized_pnl for p in self.open_positions)

    def calculate_total_realized_pnl(self) -> float:
        """Calculate total realized P&L from settled positions."""
        return sum(
            p.realized_pnl or 0
            for p in self._positions.values()
            if p.state == PositionState.SETTLED
        )

    def mark_position_settled(
        self,
        position_id: str,
        winning_side: str,
    ) -> None:
        """
        Mark a position as settled after market resolution.

        Args:
            position_id: Position ID
            winning_side: "UP" or "DOWN"
        """
        position = self._positions.get(position_id)
        if not position:
            return

        # Calculate realized P&L
        # Winner pays $1.00 per contract
        if winning_side.upper() == "UP":
            settlement_value = position.up_contracts * 1.0
        else:
            settlement_value = position.down_contracts * 1.0

        position.settlement_value = settlement_value
        position.realized_pnl = settlement_value - position.total_cost
        position.state = PositionState.SETTLED
        position.settled_at = datetime.now()

        logger.info(
            "Position settled",
            position_id=position_id,
            winning_side=winning_side,
            settlement_value=settlement_value,
            realized_pnl=position.realized_pnl,
        )

    def get_trades(self, position_id: str | None = None) -> list[Trade]:
        """Get trades, optionally filtered by position."""
        if position_id:
            return [t for t in self._trades if t.position_id == position_id]
        return self._trades.copy()

    def get_position_summary(self) -> dict[str, Any]:
        """Get summary of all positions."""
        open_pos = self.open_positions
        partial = self.get_partial_positions()

        return {
            "total_positions": len(self._positions),
            "open_positions": len(open_pos),
            "partial_positions": len(partial),
            "settled_positions": len([
                p for p in self._positions.values()
                if p.state == PositionState.SETTLED
            ]),
            "total_exposure": self.total_exposure,
            "unrealized_pnl": self.calculate_total_unrealized_pnl(),
            "realized_pnl": self.calculate_total_realized_pnl(),
            "total_trades": len(self._trades),
        }
