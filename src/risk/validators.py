"""Trade validators for pre-trade checks."""

from dataclasses import dataclass

import structlog

from src.config.constants import MARKET_CLOSE_BUFFER_SECONDS
from src.models import ArbitrageOpportunity, Market

logger = structlog.get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    reason: str = ""
    warnings: list[str] | None = None


class TradeValidator:
    """
    Validates trades before execution.
    
    Performs various checks to ensure trades are safe to execute.
    """

    def __init__(
        self,
        min_profit_threshold: float = 0.04,
        min_liquidity: float = 100.0,
        min_time_to_close: float = MARKET_CLOSE_BUFFER_SECONDS,
    ) -> None:
        """
        Initialize validator.

        Args:
            min_profit_threshold: Minimum profit per contract
            min_liquidity: Minimum liquidity required
            min_time_to_close: Minimum seconds before market close
        """
        self.min_profit_threshold = min_profit_threshold
        self.min_liquidity = min_liquidity
        self.min_time_to_close = min_time_to_close

    def validate_market(self, market: Market) -> ValidationResult:
        """
        Validate a market is suitable for trading.

        Args:
            market: Market to validate

        Returns:
            ValidationResult
        """
        warnings = []

        # Check if market is active
        if not market.is_active:
            return ValidationResult(False, "Market is not active")

        # Check if market is closed
        if market.is_closed:
            return ValidationResult(False, "Market is closed")

        # Check time to close
        time_to_close = market.time_to_close_seconds
        if time_to_close is not None:
            if time_to_close < self.min_time_to_close:
                return ValidationResult(
                    False,
                    f"Market closes in {time_to_close:.0f}s (min: {self.min_time_to_close}s)",
                )
            if time_to_close < 60:
                warnings.append(f"Market closes soon: {time_to_close:.0f}s")

        # Check tokens exist
        if not market.tokens:
            return ValidationResult(False, "Market has no tradeable tokens")

        return ValidationResult(True, "Market is valid", warnings)

    def validate_opportunity(
        self,
        opportunity: ArbitrageOpportunity,
    ) -> ValidationResult:
        """
        Validate an arbitrage opportunity.

        Args:
            opportunity: Opportunity to validate

        Returns:
            ValidationResult
        """
        warnings = []

        # Validate underlying market first
        market_result = self.validate_market(opportunity.market)
        if not market_result.is_valid:
            return market_result

        if market_result.warnings:
            warnings.extend(market_result.warnings)

        # Check profitability
        if opportunity.profit_per_contract < self.min_profit_threshold:
            return ValidationResult(
                False,
                f"Profit {opportunity.profit_per_contract:.4f} below threshold "
                f"{self.min_profit_threshold:.4f}",
            )

        # Check total cost is valid
        if opportunity.total_cost >= 1.0:
            return ValidationResult(
                False,
                f"Total cost {opportunity.total_cost:.4f} >= $1.00 (no arbitrage)",
            )

        if opportunity.total_cost <= 0:
            return ValidationResult(False, "Invalid total cost")

        # Check liquidity
        min_liquidity = min(opportunity.up_liquidity, opportunity.down_liquidity)
        if min_liquidity < self.min_liquidity:
            return ValidationResult(
                False,
                f"Insufficient liquidity: {min_liquidity:.2f} < {self.min_liquidity:.2f}",
            )

        # Check max contracts
        if opportunity.max_contracts <= 0:
            return ValidationResult(False, "No contracts available")

        # Add warnings for marginal conditions
        if opportunity.profit_per_contract < 0.05:
            warnings.append(f"Low profit margin: {opportunity.profit_per_contract:.4f}")

        if min_liquidity < 500:
            warnings.append(f"Limited liquidity: {min_liquidity:.2f}")

        return ValidationResult(True, "Opportunity is valid", warnings)

    def validate_position_size(
        self,
        opportunity: ArbitrageOpportunity,
        proposed_size: float,
        current_balance: float,
    ) -> ValidationResult:
        """
        Validate a proposed position size.

        Args:
            opportunity: The opportunity being traded
            proposed_size: Proposed size in USDC
            current_balance: Current USDC balance

        Returns:
            ValidationResult
        """
        warnings = []

        # Check minimum size
        if proposed_size < 1.0:
            return ValidationResult(False, "Position size too small (min: $1.00)")

        # Check balance
        if proposed_size > current_balance:
            return ValidationResult(
                False,
                f"Insufficient balance: {current_balance:.2f} < {proposed_size:.2f}",
            )

        # Check against liquidity
        max_by_liquidity = opportunity.max_contracts * opportunity.total_cost
        if proposed_size > max_by_liquidity:
            return ValidationResult(
                False,
                f"Size exceeds liquidity: {proposed_size:.2f} > {max_by_liquidity:.2f}",
            )

        # Warnings for large positions relative to liquidity
        if proposed_size > max_by_liquidity * 0.5:
            warnings.append("Position uses >50% of available liquidity")

        return ValidationResult(True, "Position size is valid", warnings)

    def validate_all(
        self,
        opportunity: ArbitrageOpportunity,
        proposed_size: float,
        current_balance: float,
    ) -> ValidationResult:
        """
        Run all validations.

        Args:
            opportunity: Opportunity to validate
            proposed_size: Proposed position size
            current_balance: Current balance

        Returns:
            Combined ValidationResult
        """
        all_warnings = []

        # Validate opportunity (includes market)
        opp_result = self.validate_opportunity(opportunity)
        if not opp_result.is_valid:
            return opp_result
        if opp_result.warnings:
            all_warnings.extend(opp_result.warnings)

        # Validate size
        size_result = self.validate_position_size(
            opportunity, proposed_size, current_balance
        )
        if not size_result.is_valid:
            return size_result
        if size_result.warnings:
            all_warnings.extend(size_result.warnings)

        return ValidationResult(True, "All validations passed", all_warnings)
