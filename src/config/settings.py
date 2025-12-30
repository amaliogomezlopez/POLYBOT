"""Application settings with Pydantic validation."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Polymarket credentials
    polymarket_private_key: SecretStr = Field(
        ...,
        description="Private key for signing transactions",
    )
    polymarket_funder_address: str = Field(
        ...,
        description="Address that holds funds on Polymarket",
    )
    signature_type: int = Field(
        default=1,
        ge=0,
        le=2,
        description="Signature type: 0=EOA, 1=Magic/Email, 2=Browser proxy",
    )

    # Trading parameters
    max_position_size_usdc: float = Field(
        default=1000.0,
        gt=0,
        description="Maximum position size per market in USDC",
    )
    min_profit_threshold: float = Field(
        default=0.04,
        gt=0,
        lt=1,
        description="Minimum profit per contract to consider (e.g., 0.04 = 4 cents)",
    )
    max_daily_loss_usdc: float = Field(
        default=500.0,
        gt=0,
        description="Maximum daily loss before stopping bot",
    )
    max_total_exposure_usdc: float = Field(
        default=5000.0,
        gt=0,
        description="Maximum total exposure across all markets",
    )

    # Telegram alerts (optional)
    telegram_bot_token: str | None = Field(
        default=None,
        description="Telegram bot token for alerts",
    )
    telegram_chat_id: str | None = Field(
        default=None,
        description="Telegram chat ID for alerts",
    )

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./polymarket_bot.db",
        description="Database connection URL",
    )

    # Environment
    environment: Literal["development", "production"] = Field(
        default="development",
        description="Environment mode",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Paper trading
    paper_trading: bool = Field(
        default=False,
        description="Enable paper trading mode (no real orders)",
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    @property
    def telegram_enabled(self) -> bool:
        """Check if Telegram alerts are configured."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
