"""Tests for the spread analyzer."""

import pytest
from datetime import datetime, timedelta

from src.detector.spread_analyzer import SpreadAnalyzer, SpreadAnalysisResult
from src.models import Market, TokenPair
from src.config.constants import MarketType


@pytest.fixture
def analyzer() -> SpreadAnalyzer:
    """Create a spread analyzer with default settings."""
    return SpreadAnalyzer(
        min_profit_threshold=0.04,
        min_liquidity=100.0,
        max_position_size=1000.0,
    )


@pytest.fixture
def sample_market() -> Market:
    """Create a sample market for testing."""
    return Market(
        id="test-market-123",
        condition_id="cond-123",
        question="Will BTC go up in the next 15 minutes?",
        slug="btc-15min-up",
        market_type=MarketType.FLASH_15MIN,
        asset="BTC",
        tokens=TokenPair(
            up_token_id="up-token-123",
            down_token_id="down-token-456",
        ),
        end_time=datetime.now() + timedelta(minutes=10),
        is_active=True,
    )


class TestSpreadAnalyzer:
    """Tests for SpreadAnalyzer class."""

    def test_profitable_opportunity(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test detection of a profitable arbitrage opportunity."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.52,
            down_price=0.44,
            up_liquidity=1000,
            down_liquidity=1000,
        )

        assert result.is_profitable is True
        assert result.total_cost == pytest.approx(0.96, rel=0.01)
        assert result.profit_per_contract == pytest.approx(0.04, rel=0.01)
        assert result.max_contracts > 0

    def test_unprofitable_total_above_one(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test rejection when total cost >= $1.00."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.55,
            down_price=0.50,
            up_liquidity=1000,
            down_liquidity=1000,
        )

        assert result.is_profitable is False
        assert result.total_cost == pytest.approx(1.05, rel=0.01)
        assert "no arbitrage" in result.reason.lower()

    def test_profit_below_threshold(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test rejection when profit is below threshold."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.50,
            down_price=0.48,  # Total: 0.98, profit: 0.02
            up_liquidity=1000,
            down_liquidity=1000,
        )

        assert result.is_profitable is False
        assert result.profit_per_contract == pytest.approx(0.02, rel=0.01)
        assert "below threshold" in result.reason.lower()

    def test_insufficient_liquidity(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test rejection when liquidity is too low."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.50,
            down_price=0.45,
            up_liquidity=50,  # Below 100 minimum
            down_liquidity=1000,
        )

        assert result.is_profitable is False
        assert "liquidity" in result.reason.lower()

    def test_market_closing_soon(self, analyzer: SpreadAnalyzer) -> None:
        """Test rejection when market closes too soon."""
        market = Market(
            id="test-market-closing",
            condition_id="cond-closing",
            question="Test closing market",
            slug="test-closing",
            market_type=MarketType.FLASH_15MIN,
            asset="BTC",
            tokens=TokenPair(
                up_token_id="up-token",
                down_token_id="down-token",
            ),
            end_time=datetime.now() + timedelta(seconds=20),  # Only 20 seconds left
            is_active=True,
        )

        result = analyzer.analyze(
            market=market,
            up_price=0.50,
            down_price=0.45,
            up_liquidity=1000,
            down_liquidity=1000,
        )

        assert result.is_profitable is False
        assert "closes" in result.reason.lower()

    def test_high_profit_opportunity(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test detection of a high-profit opportunity."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.45,
            down_price=0.40,  # Total: 0.85, profit: 0.15
            up_liquidity=5000,
            down_liquidity=5000,
        )

        assert result.is_profitable is True
        assert result.total_cost == pytest.approx(0.85, rel=0.01)
        assert result.profit_per_contract == pytest.approx(0.15, rel=0.01)

    def test_max_contracts_by_liquidity(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test that max contracts is limited by liquidity."""
        # Low liquidity on one side
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.50,
            down_price=0.45,
            up_liquidity=200,  # Limited
            down_liquidity=5000,
        )

        # Max contracts should be limited by the lower liquidity
        assert result.is_profitable is True
        # 200 / 0.95 ≈ 210 contracts max
        assert result.max_contracts < 250

    def test_max_contracts_by_position_limit(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test that max contracts is limited by position size limit."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.50,
            down_price=0.45,  # Total: 0.95
            up_liquidity=50000,
            down_liquidity=50000,
        )

        # With max position size of 1000, max contracts = 1000 / 0.95 ≈ 1053
        assert result.is_profitable is True
        assert result.max_contracts <= 1100

    def test_create_opportunity(self, analyzer: SpreadAnalyzer, sample_market: Market) -> None:
        """Test creating an ArbitrageOpportunity from result."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.50,
            down_price=0.44,
            up_liquidity=1000,
            down_liquidity=1000,
        )

        opportunity = analyzer.create_opportunity(sample_market, result)

        assert opportunity is not None
        assert opportunity.market == sample_market
        assert opportunity.profit_per_contract == pytest.approx(0.06, rel=0.01)
        assert opportunity.score > 0

    def test_create_opportunity_returns_none_for_unprofitable(
        self, analyzer: SpreadAnalyzer, sample_market: Market
    ) -> None:
        """Test that create_opportunity returns None for unprofitable result."""
        result = analyzer.analyze(
            market=sample_market,
            up_price=0.55,
            down_price=0.50,
            up_liquidity=1000,
            down_liquidity=1000,
        )

        opportunity = analyzer.create_opportunity(sample_market, result)
        assert opportunity is None
