"""Dry-run and validation configuration settings."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class DryRunConfig:
    """Configuration for dry-run validation sessions."""
    
    # Duration settings
    duration_minutes: int = 60
    
    # Position settings
    position_size_usdc: float = 10.0
    max_positions: int = 5
    
    # Thresholds
    min_profit_threshold: float = 0.04
    max_slippage_threshold: float = 1.0  # %
    latency_threshold_ms: float = 500.0
    
    # Simulation settings
    simulate_failures: bool = True
    failure_rate: float = 0.02
    simulate_partial_fills: bool = True
    partial_fill_rate: float = 0.05
    simulate_slippage: bool = True
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"
    save_all_trades: bool = True
    
    # Report settings
    generate_report: bool = True
    report_output_dir: str = "./reports"
    report_format: Literal["json", "md", "both"] = "both"


@dataclass
class ValidationThresholds:
    """Thresholds for validation pass/fail criteria."""
    
    # Success criteria
    min_success_rate: float = 90.0  # %
    min_win_rate: float = 50.0  # %
    max_avg_slippage: float = 0.5  # %
    max_p95_latency_ms: float = 500.0
    min_profit_factor: float = 1.5
    
    # Alert thresholds
    alert_on_failure_rate: float = 10.0  # %
    alert_on_slippage: float = 1.0  # %
    alert_on_latency_ms: float = 1000.0
    
    def check_passed(
        self,
        success_rate: float,
        win_rate: float,
        avg_slippage: float,
        p95_latency: float,
        profit_factor: float,
    ) -> tuple[bool, list[str]]:
        """
        Check if validation thresholds are met.
        
        Returns:
            Tuple of (passed, list of failure reasons)
        """
        failures = []
        
        if success_rate < self.min_success_rate:
            failures.append(f"Success rate {success_rate:.1f}% below threshold {self.min_success_rate}%")
        
        if win_rate < self.min_win_rate:
            failures.append(f"Win rate {win_rate:.1f}% below threshold {self.min_win_rate}%")
        
        if avg_slippage > self.max_avg_slippage:
            failures.append(f"Avg slippage {avg_slippage:.2f}% exceeds threshold {self.max_avg_slippage}%")
        
        if p95_latency > self.max_p95_latency_ms:
            failures.append(f"P95 latency {p95_latency:.0f}ms exceeds threshold {self.max_p95_latency_ms}ms")
        
        if profit_factor < self.min_profit_factor:
            failures.append(f"Profit factor {profit_factor:.2f} below threshold {self.min_profit_factor}")
        
        return len(failures) == 0, failures


# Default configurations
DEFAULT_DRY_RUN_CONFIG = DryRunConfig()
DEFAULT_VALIDATION_THRESHOLDS = ValidationThresholds()


# Production-ready configuration (stricter)
PRODUCTION_VALIDATION_THRESHOLDS = ValidationThresholds(
    min_success_rate=95.0,
    min_win_rate=60.0,
    max_avg_slippage=0.3,
    max_p95_latency_ms=300.0,
    min_profit_factor=2.0,
)
