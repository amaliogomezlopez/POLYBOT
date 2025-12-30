"""Tests for the risk manager."""

import pytest
from datetime import datetime, timedelta

from src.config.settings import Settings
from src.risk.risk_manager import RiskManager, RiskLimits
from src.models import ArbitrageOpportunity, Market, Position, TokenPair
from src.config.constants import MarketType, PositionState


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings."""
    # Create settings without loading from env
    class MockSettings:
        max_position_size_usdc = 1000.0
        max_total_exposure_usdc = 5000.0
        max_daily_loss_usdc = 500.0
        min_profit_threshold = 0.04

    return MockSettings()  # type: ignore


@pytest.fixture
def risk_manager(mock_settings) -> RiskManager:
    """Create a risk manager with mock settings."""
    return RiskManager(mock_settings)


@pytest.fixture
def sample_opportunity() -> ArbitrageOpportunity:
    """Create a sample arbitrage opportunity."""
    market = Market(
        id="test-market",
        condition_id="cond-123",
        question="Test market",
        slug="test",
        market_type=MarketType.FLASH_15MIN,
        asset="BTC",
        tokens=TokenPair(up_token_id="up", down_token_id="down"),
    )
    return ArbitrageOpportunity(
        market=market,
        up_price=0.50,
        down_price=0.45,
        total_cost=0.95,
        profit_per_contract=0.05,
        up_liquidity=1000,
        down_liquidity=1000,
        max_contracts=500,
    )


class TestRiskManager:
    """Tests for RiskManager class."""

    def test_can_open_position_success(
        self, risk_manager: RiskManager, sample_opportunity: ArbitrageOpportunity
    ) -> None:
        """Test allowing a position that meets all criteria."""
        allowed, reason = risk_manager.can_open_position(
            opportunity=sample_opportunity,
            proposed_size=500.0,
        )

        assert allowed is True
        assert reason == "OK"

    def test_reject_when_trading_halted(
        self, risk_manager: RiskManager, sample_opportunity: ArbitrageOpportunity
    ) -> None:
        """Test rejection when trading is halted."""
        risk_manager.halt_trading("daily_loss_limit")

        allowed, reason = risk_manager.can_open_position(
            opportunity=sample_opportunity,
            proposed_size=500.0,
        )

        assert allowed is False
        assert "halted" in reason.lower()

    def test_reject_exceeds_exposure_limit(
        self, risk_manager: RiskManager, sample_opportunity: ArbitrageOpportunity
    ) -> None:
        """Test rejection when exposure limit would be exceeded."""
        # Set current exposure close to limit
        risk_manager._metrics.total_exposure = 4800.0

        allowed, reason = risk_manager.can_open_position(
            opportunity=sample_opportunity,
            proposed_size=500.0,  # Would exceed 5000 limit
        )

        assert allowed is False
        assert "exposure limit" in reason.lower()

    def test_reject_exceeds_position_limit(
        self, risk_manager: RiskManager, sample_opportunity: ArbitrageOpportunity
    ) -> None:
        """Test rejection when position size exceeds limit."""
        allowed, reason = risk_manager.can_open_position(
            opportunity=sample_opportunity,
            proposed_size=1500.0,  # Exceeds 1000 limit
        )

        assert allowed is False
        assert "position size" in reason.lower()

    def test_reject_profit_below_threshold(
        self, risk_manager: RiskManager
    ) -> None:
        """Test rejection when profit is below threshold."""
        low_profit_market = Market(
            id="low-profit",
            condition_id="cond",
            question="Test",
            slug="test",
            market_type=MarketType.FLASH_15MIN,
            asset="ETH",
            tokens=TokenPair(up_token_id="up", down_token_id="down"),
        )
        low_profit_opp = ArbitrageOpportunity(
            market=low_profit_market,
            up_price=0.50,
            down_price=0.48,
            total_cost=0.98,
            profit_per_contract=0.02,  # Below 0.04 threshold
            up_liquidity=1000,
            down_liquidity=1000,
            max_contracts=500,
        )

        allowed, reason = risk_manager.can_open_position(
            opportunity=low_profit_opp,
            proposed_size=500.0,
        )

        assert allowed is False
        assert "profit" in reason.lower()

    def test_reject_max_positions_per_market(
        self, risk_manager: RiskManager, sample_opportunity: ArbitrageOpportunity
    ) -> None:
        """Test rejection when max positions per market reached."""
        risk_manager._metrics.positions_per_market["test-market"] = 1

        allowed, reason = risk_manager.can_open_position(
            opportunity=sample_opportunity,
            proposed_size=500.0,
        )

        assert allowed is False
        assert "max positions" in reason.lower()

    def test_calculate_position_size(
        self, risk_manager: RiskManager, sample_opportunity: ArbitrageOpportunity
    ) -> None:
        """Test position size calculation."""
        size = risk_manager.calculate_position_size(sample_opportunity)

        # Should be limited by max_position_size_usdc (1000)
        # multiplied by profit factor (0.05 / 0.10 = 0.5)
        assert size > 0
        assert size <= 1000.0

    def test_calculate_position_size_respects_remaining_exposure(
        self, risk_manager: RiskManager, sample_opportunity: ArbitrageOpportunity
    ) -> None:
        """Test that position size respects remaining exposure."""
        risk_manager._metrics.total_exposure = 4500.0  # 500 remaining

        size = risk_manager.calculate_position_size(sample_opportunity)

        assert size <= 500.0

    def test_update_exposure(self, risk_manager: RiskManager) -> None:
        """Test exposure update from positions."""
        positions = [
            Position(id="1", market_id="m1", total_cost=100.0),
            Position(id="2", market_id="m1", total_cost=200.0),
            Position(id="3", market_id="m2", total_cost=150.0),
        ]

        risk_manager.update_exposure(positions)

        assert risk_manager._metrics.total_exposure == 450.0
        assert risk_manager._metrics.open_positions == 3
        assert risk_manager._metrics.positions_per_market["m1"] == 2
        assert risk_manager._metrics.positions_per_market["m2"] == 1

    def test_daily_loss_limit_halts_trading(self, risk_manager: RiskManager) -> None:
        """Test that exceeding daily loss limit halts trading."""
        risk_manager.update_daily_pnl(-600.0)  # Exceeds 500 limit

        assert risk_manager._metrics.is_trading_halted is True
        assert risk_manager._metrics.halt_reason == "daily_loss_limit"

    def test_resume_trading(self, risk_manager: RiskManager) -> None:
        """Test resuming trading after halt."""
        risk_manager.halt_trading("test_reason")
        assert risk_manager.is_trading_allowed is False

        risk_manager.resume_trading()
        assert risk_manager.is_trading_allowed is True

    def test_check_position_timeout(self, risk_manager: RiskManager) -> None:
        """Test position timeout detection."""
        old_position = Position(
            id="old",
            market_id="m1",
            created_at=datetime.now() - timedelta(minutes=20),
        )
        new_position = Position(
            id="new",
            market_id="m2",
            created_at=datetime.now() - timedelta(minutes=5),
        )

        timed_out = risk_manager.check_position_timeout([old_position, new_position])

        assert len(timed_out) == 1
        assert timed_out[0].id == "old"

    def test_risk_summary(self, risk_manager: RiskManager) -> None:
        """Test getting risk summary."""
        risk_manager._metrics.total_exposure = 2500.0
        risk_manager._metrics.daily_pnl = 150.0
        risk_manager._metrics.open_positions = 3

        summary = risk_manager.get_risk_summary()

        assert summary["total_exposure"] == 2500.0
        assert summary["exposure_utilization"] == 50.0
        assert summary["daily_pnl"] == 150.0
        assert summary["open_positions"] == 3
        assert summary["is_trading_allowed"] is True
