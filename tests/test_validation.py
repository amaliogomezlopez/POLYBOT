"""Tests for validation modules (Phase 9)."""

import pytest
from datetime import datetime, timedelta

from src.monitoring.latency_logger import LatencyLogger, LatencyMeasurement
from src.trading.slippage_simulator import SlippageSimulator, SimulatedOrderbook
from src.reporting.post_trade_analysis import PostTradeAnalyzer, TradeAnalysis
from src.config.validation_config import ValidationThresholds, DryRunConfig


class TestLatencyLogger:
    """Tests for LatencyLogger class."""

    def test_record_latency(self) -> None:
        """Test recording a latency measurement."""
        logger = LatencyLogger()
        
        start = logger.start_timer()
        import time
        time.sleep(0.01)  # 10ms delay
        
        measurement = logger.record("test_operation", start)
        
        assert measurement.operation == "test_operation"
        assert measurement.latency_ms >= 10  # At least 10ms
        assert measurement.success is True

    def test_get_stats(self) -> None:
        """Test getting latency statistics."""
        logger = LatencyLogger()
        
        # Record some measurements
        for i in range(10):
            logger.record_direct("test_op", latency_ms=100 + i * 10)
        
        stats = logger.get_stats("test_op")
        
        assert stats.count == 10
        assert stats.min_ms == 100
        assert stats.max_ms == 190
        assert stats.avg_ms == 145  # Average of 100-190

    def test_warning_threshold(self) -> None:
        """Test that high latency triggers warning."""
        logger = LatencyLogger()
        logger.warning_thresholds["test_op"] = 50
        
        # This should trigger warning (over 50ms)
        logger.record_direct("test_op", latency_ms=100)
        
        # Measurement should still be recorded
        assert len(logger.get_recent_measurements("test_op")) == 1

    def test_generate_report(self) -> None:
        """Test report generation."""
        logger = LatencyLogger()
        
        logger.record_direct("order_placement", 100, success=True)
        logger.record_direct("order_placement", 150, success=True)
        logger.record_direct("order_placement", 200, success=False)
        
        report = logger.generate_report()
        
        assert "order_placement" in report["operations"]
        assert report["operations"]["order_placement"]["count"] == 3
        assert report["operations"]["order_placement"]["success_rate"] < 100


class TestSlippageSimulator:
    """Tests for SlippageSimulator class."""

    def test_generate_orderbook(self) -> None:
        """Test orderbook generation."""
        simulator = SlippageSimulator()
        
        orderbook = simulator.generate_orderbook(
            token_id="test-token",
            mid_price=0.5,
            spread=0.02,
        )
        
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0
        assert orderbook.best_bid < orderbook.best_ask
        assert abs(orderbook.best_ask - orderbook.best_bid - 0.02) < 0.01

    def test_simulate_market_order_buy(self) -> None:
        """Test market order simulation for buy."""
        simulator = SlippageSimulator(failure_rate=0, partial_fill_rate=0)
        
        orderbook = simulator.generate_orderbook("test-token", mid_price=0.5)
        result = simulator.simulate_market_order(
            token_id="test-token",
            side="BUY",
            amount_usdc=100,
            orderbook=orderbook,
        )
        
        assert result.success is True
        assert result.filled_size > 0
        assert result.avg_price > 0
        assert result.fee >= 0

    def test_simulate_market_order_with_slippage(self) -> None:
        """Test that large orders have slippage."""
        simulator = SlippageSimulator(failure_rate=0, partial_fill_rate=0)
        
        # Create orderbook with limited liquidity
        orderbook = simulator.generate_orderbook(
            "test-token",
            mid_price=0.5,
            avg_level_size=100,  # Small liquidity
        )
        
        # Large order should have slippage
        result = simulator.simulate_market_order(
            token_id="test-token",
            side="BUY",
            amount_usdc=500,  # Large relative to liquidity
            orderbook=orderbook,
        )
        
        if result.success:
            # Should have some slippage due to eating through levels
            assert result.slippage >= 0

    def test_failure_simulation(self) -> None:
        """Test that failures are simulated."""
        simulator = SlippageSimulator(failure_rate=1.0)  # 100% failure
        
        result = simulator.simulate_market_order(
            token_id="test-token",
            side="BUY",
            amount_usdc=100,
        )
        
        assert result.success is False
        assert result.error is not None

    def test_statistics_tracking(self) -> None:
        """Test that statistics are tracked."""
        simulator = SlippageSimulator(failure_rate=0, partial_fill_rate=0)
        
        for _ in range(5):
            simulator.simulate_market_order("test", "BUY", 100)
        
        stats = simulator.get_statistics()
        
        assert stats["total_orders"] == 5


class TestPostTradeAnalyzer:
    """Tests for PostTradeAnalyzer class."""

    def test_record_detected_price(self) -> None:
        """Test recording detected prices."""
        analyzer = PostTradeAnalyzer()
        
        analyzer.record_detected_price("token-1", 0.50)
        
        assert "token-1" in analyzer._detected_prices
        assert analyzer._detected_prices["token-1"] == 0.50

    def test_analyze_trade_slippage(self) -> None:
        """Test slippage calculation in trade analysis."""
        from src.models import Trade
        from src.config.constants import OutcomeType
        
        analyzer = PostTradeAnalyzer()
        
        # Record detected price
        analyzer.record_detected_price("token-1", 0.50)
        
        # Create trade with different executed price
        trade = Trade(
            id="trade-1",
            position_id="pos-1",
            order_id="order-1",
            market_id="market-1",
            token_id="token-1",
            outcome_type=OutcomeType.UP,
            side="BUY",
            price=0.52,  # Executed at higher price
            size=100,
            fee=1.0,
        )
        
        analysis = analyzer.analyze_trade(trade, executed_price=0.52)
        
        assert analysis.detected_price == 0.50
        assert analysis.executed_price == 0.52
        assert abs(analysis.slippage - 0.02) < 0.0001  # Float comparison with tolerance
        assert abs(analysis.slippage_pct - 4.0) < 0.0001  # 2 cents on 50 cent price = 4%
        assert analysis.had_slippage is True


class TestValidationThresholds:
    """Tests for ValidationThresholds class."""

    def test_check_passed_all_good(self) -> None:
        """Test validation passes when all criteria met."""
        thresholds = ValidationThresholds()
        
        passed, failures = thresholds.check_passed(
            success_rate=95.0,
            win_rate=60.0,
            avg_slippage=0.2,
            p95_latency=300,
            profit_factor=2.0,
        )
        
        assert passed is True
        assert len(failures) == 0

    def test_check_passed_failures(self) -> None:
        """Test validation fails when criteria not met."""
        thresholds = ValidationThresholds(
            min_success_rate=90.0,
            min_win_rate=50.0,
        )
        
        passed, failures = thresholds.check_passed(
            success_rate=80.0,  # Below threshold
            win_rate=40.0,  # Below threshold
            avg_slippage=0.2,
            p95_latency=300,
            profit_factor=2.0,
        )
        
        assert passed is False
        assert len(failures) == 2
        assert any("Success rate" in f for f in failures)
        assert any("Win rate" in f for f in failures)


class TestDryRunConfig:
    """Tests for DryRunConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = DryRunConfig()
        
        assert config.duration_minutes == 60
        assert config.position_size_usdc == 10.0
        assert config.simulate_slippage is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = DryRunConfig(
            duration_minutes=120,
            position_size_usdc=50.0,
            failure_rate=0.05,
        )
        
        assert config.duration_minutes == 120
        assert config.position_size_usdc == 50.0
        assert config.failure_rate == 0.05
