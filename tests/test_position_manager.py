"""Tests for the position manager."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.trading.position_manager import PositionManager
from src.trading.order_executor import OrderExecutor, OrderResult
from src.models import ArbitrageOpportunity, Market, TokenPair, Position
from src.config.constants import MarketType, PositionState


@pytest.fixture
def mock_order_executor() -> MagicMock:
    """Create a mock order executor."""
    executor = MagicMock(spec=OrderExecutor)
    executor.place_market_order = AsyncMock(return_value=OrderResult(
        success=True,
        order_id="order-123",
        filled_size=100.0,
        avg_price=0.50,
    ))
    return executor


@pytest.fixture
def position_manager(mock_order_executor: MagicMock) -> PositionManager:
    """Create a position manager with mock executor."""
    return PositionManager(order_executor=mock_order_executor)


@pytest.fixture
def sample_opportunity() -> ArbitrageOpportunity:
    """Create a sample arbitrage opportunity."""
    market = Market(
        id="test-market-123",
        condition_id="cond-123",
        question="Will BTC go up?",
        slug="btc-up",
        market_type=MarketType.FLASH_15MIN,
        asset="BTC",
        tokens=TokenPair(
            up_token_id="up-token-123",
            down_token_id="down-token-456",
        ),
        is_active=True,
    )

    return ArbitrageOpportunity(
        market=market,
        up_price=0.52,
        down_price=0.44,
        total_cost=0.96,
        profit_per_contract=0.04,
        up_liquidity=1000,
        down_liquidity=1000,
        max_contracts=500,
    )


class TestPositionManager:
    """Tests for PositionManager class."""

    @pytest.mark.asyncio
    async def test_open_position_success(
        self,
        position_manager: PositionManager,
        sample_opportunity: ArbitrageOpportunity,
    ) -> None:
        """Test successfully opening a position."""
        position = await position_manager.open_position(
            opportunity=sample_opportunity,
            size_usdc=100.0,
        )

        assert position is not None
        assert position.state == PositionState.COMPLETE
        assert position.market_id == "test-market-123"
        assert position.up_contracts > 0
        assert position.down_contracts > 0

    @pytest.mark.asyncio
    async def test_open_position_records_trades(
        self,
        position_manager: PositionManager,
        sample_opportunity: ArbitrageOpportunity,
    ) -> None:
        """Test that opening a position records trades."""
        await position_manager.open_position(
            opportunity=sample_opportunity,
            size_usdc=100.0,
        )

        trades = position_manager.get_trades()
        assert len(trades) == 2  # UP and DOWN trades

    @pytest.mark.asyncio
    async def test_open_position_partial_when_down_fails(
        self,
        position_manager: PositionManager,
        mock_order_executor: MagicMock,
        sample_opportunity: ArbitrageOpportunity,
    ) -> None:
        """Test partial position when DOWN order fails."""
        # Make DOWN order fail
        call_count = 0
        async def mock_place_order(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # UP order succeeds
                return OrderResult(success=True, order_id="up-order", filled_size=50.0)
            else:  # DOWN order fails
                return OrderResult(success=False, error="Insufficient liquidity")

        mock_order_executor.place_market_order = mock_place_order

        position = await position_manager.open_position(
            opportunity=sample_opportunity,
            size_usdc=100.0,
        )

        assert position is not None
        assert position.state == PositionState.PARTIAL
        assert position.up_contracts > 0
        assert position.down_contracts == 0

    @pytest.mark.asyncio
    async def test_get_partial_positions(
        self,
        position_manager: PositionManager,
        mock_order_executor: MagicMock,
        sample_opportunity: ArbitrageOpportunity,
    ) -> None:
        """Test getting partial positions."""
        # Create a partial position
        call_count = 0
        async def mock_place_order(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OrderResult(success=True, order_id="up-order", filled_size=50.0)
            else:
                return OrderResult(success=False, error="Failed")

        mock_order_executor.place_market_order = mock_place_order

        await position_manager.open_position(
            opportunity=sample_opportunity,
            size_usdc=100.0,
        )

        partial = position_manager.get_partial_positions()
        assert len(partial) == 1

    def test_position_delta_calculation(self) -> None:
        """Test delta calculation for positions."""
        position = Position(
            id="test-pos",
            market_id="test-market",
            up_contracts=100.0,
            down_contracts=95.0,
        )

        assert position.delta == pytest.approx(5.0)
        assert not position.is_delta_neutral

    def test_position_delta_neutral(self) -> None:
        """Test delta neutral check."""
        position = Position(
            id="test-pos",
            market_id="test-market",
            up_contracts=100.0,
            down_contracts=100.0,
        )

        assert position.delta == pytest.approx(0.0)
        assert position.is_delta_neutral

    def test_expected_profit_calculation(self) -> None:
        """Test expected profit per contract calculation."""
        position = Position(
            id="test-pos",
            market_id="test-market",
            up_contracts=100.0,
            down_contracts=100.0,
            up_avg_price=0.52,
            down_avg_price=0.44,
        )

        # Combined cost: 0.96, expected profit: 0.04
        assert position.combined_avg_price == pytest.approx(0.96, rel=0.01)
        assert position.expected_profit_per_contract == pytest.approx(0.04, rel=0.01)

    def test_unrealized_pnl_calculation(self) -> None:
        """Test unrealized P&L calculation."""
        position = Position(
            id="test-pos",
            market_id="test-market",
            up_contracts=100.0,
            down_contracts=100.0,
            up_avg_price=0.52,
            down_avg_price=0.44,
            total_cost=96.0,
        )

        # Expected: 100 contracts * $0.04 = $4.00
        assert position.unrealized_pnl == pytest.approx(4.0, rel=0.1)

    @pytest.mark.asyncio
    async def test_position_summary(
        self,
        position_manager: PositionManager,
        sample_opportunity: ArbitrageOpportunity,
    ) -> None:
        """Test getting position summary."""
        await position_manager.open_position(
            opportunity=sample_opportunity,
            size_usdc=100.0,
        )

        summary = position_manager.get_position_summary()

        assert summary["total_positions"] == 1
        assert summary["open_positions"] == 1
        assert summary["total_trades"] == 2

    def test_mark_position_settled(self, position_manager: PositionManager) -> None:
        """Test marking a position as settled."""
        # Manually add a position
        position = Position(
            id="test-pos",
            market_id="test-market",
            state=PositionState.COMPLETE,
            up_contracts=100.0,
            down_contracts=100.0,
            up_avg_price=0.52,
            down_avg_price=0.44,
            total_cost=96.0,
        )
        position_manager._positions["test-pos"] = position

        # Settle with UP winning
        position_manager.mark_position_settled("test-pos", "UP")

        assert position.state == PositionState.SETTLED
        assert position.settlement_value == 100.0  # 100 UP contracts * $1
        assert position.realized_pnl == pytest.approx(4.0, rel=0.1)  # $4 profit

    def test_total_exposure(
        self, position_manager: PositionManager
    ) -> None:
        """Test total exposure calculation."""
        # Add two positions
        pos1 = Position(
            id="pos-1",
            market_id="market-1",
            state=PositionState.COMPLETE,
            total_cost=100.0,
        )
        pos2 = Position(
            id="pos-2",
            market_id="market-2",
            state=PositionState.COMPLETE,
            total_cost=150.0,
        )
        position_manager._positions["pos-1"] = pos1
        position_manager._positions["pos-2"] = pos2

        assert position_manager.total_exposure == pytest.approx(250.0)
