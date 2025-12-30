"""Alert manager for Telegram/Discord notifications."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from src.config.constants import AlertType

logger = structlog.get_logger(__name__)


@dataclass
class Alert:
    """An alert to be sent."""

    type: AlertType
    title: str
    message: str
    data: dict[str, Any] | None = None
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now()


class AlertManager:
    """
    Manages alerts via Telegram.
    
    Sends notifications for trades, errors, and daily summaries.
    """

    def __init__(
        self,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> None:
        """
        Initialize alert manager.

        Args:
            telegram_token: Telegram bot token
            telegram_chat_id: Telegram chat ID to send alerts to
        """
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self._queue: asyncio.Queue[Alert] = asyncio.Queue()
        self._running = False
        self._alert_history: list[Alert] = []

    @property
    def is_enabled(self) -> bool:
        """Check if alerts are enabled."""
        return bool(self.telegram_token and self.telegram_chat_id)

    async def start(self) -> None:
        """Start the alert processing loop."""
        if not self.is_enabled:
            logger.info("Alerts disabled (no Telegram credentials)")
            return

        self._running = True
        asyncio.create_task(self._process_alerts())
        logger.info("Alert manager started")

    async def stop(self) -> None:
        """Stop the alert processing loop."""
        self._running = False
        logger.info("Alert manager stopped")

    async def send_alert(self, alert: Alert) -> bool:
        """
        Queue an alert for sending.

        Args:
            alert: Alert to send

        Returns:
            True if queued successfully
        """
        await self._queue.put(alert)
        return True

    async def send_trade_alert(
        self,
        market_id: str,
        asset: str | None,
        side: str,
        size: float,
        price: float,
        pnl: float | None = None,
    ) -> bool:
        """Send a trade execution alert."""
        emoji = "📈" if side == "BUY" else "📉"
        pnl_text = f" | P&L: ${pnl:.2f}" if pnl is not None else ""

        alert = Alert(
            type=AlertType.TRADE_EXECUTED,
            title=f"{emoji} Trade Executed",
            message=(
                f"**{asset or 'Unknown'}** {side}\n"
                f"Size: ${size:.2f} @ {price:.4f}{pnl_text}"
            ),
            data={"market_id": market_id, "asset": asset, "side": side, "size": size},
        )
        return await self.send_alert(alert)

    async def send_opportunity_alert(
        self,
        asset: str,
        profit: float,
        total_cost: float,
        max_size: float,
    ) -> bool:
        """Send an opportunity found alert."""
        alert = Alert(
            type=AlertType.OPPORTUNITY_FOUND,
            title="💰 Opportunity Found",
            message=(
                f"**{asset}** Flash Market\n"
                f"Profit: {profit*100:.2f}% (${profit:.4f}/contract)\n"
                f"Cost: ${total_cost:.4f} | Max: ${max_size:.2f}"
            ),
            data={"asset": asset, "profit": profit, "total_cost": total_cost},
        )
        return await self.send_alert(alert)

    async def send_position_settled_alert(
        self,
        asset: str,
        winning_side: str,
        realized_pnl: float,
    ) -> bool:
        """Send a position settled alert."""
        emoji = "✅" if realized_pnl >= 0 else "❌"
        alert = Alert(
            type=AlertType.POSITION_SETTLED,
            title=f"{emoji} Position Settled",
            message=(
                f"**{asset}** | Winner: {winning_side}\n"
                f"Realized P&L: ${realized_pnl:.2f}"
            ),
            data={"asset": asset, "winning_side": winning_side, "pnl": realized_pnl},
        )
        return await self.send_alert(alert)

    async def send_error_alert(self, error: str, context: str | None = None) -> bool:
        """Send an error alert."""
        alert = Alert(
            type=AlertType.ERROR,
            title="🚨 Error",
            message=f"{error}\n\nContext: {context}" if context else error,
        )
        return await self.send_alert(alert)

    async def send_daily_summary(
        self,
        trades: int,
        realized_pnl: float,
        win_rate: float,
        exposure: float,
    ) -> bool:
        """Send daily summary alert."""
        emoji = "🟢" if realized_pnl >= 0 else "🔴"
        alert = Alert(
            type=AlertType.DAILY_SUMMARY,
            title=f"{emoji} Daily Summary",
            message=(
                f"**Trades:** {trades}\n"
                f"**P&L:** ${realized_pnl:.2f}\n"
                f"**Win Rate:** {win_rate*100:.1f}%\n"
                f"**Exposure:** ${exposure:.2f}"
            ),
        )
        return await self.send_alert(alert)

    async def _process_alerts(self) -> None:
        """Process queued alerts."""
        while self._running:
            try:
                # Get alert with timeout
                try:
                    alert = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                # Send via Telegram
                success = await self._send_telegram(alert)
                if success:
                    self._alert_history.append(alert)
                    # Keep only last 100 alerts
                    self._alert_history = self._alert_history[-100:]

            except Exception as e:
                logger.error("Alert processing error", error=str(e))

    async def _send_telegram(self, alert: Alert) -> bool:
        """Send alert via Telegram."""
        if not self.is_enabled:
            # Log instead of sending
            logger.info(
                "Alert (Telegram disabled)",
                type=alert.type.value,
                title=alert.title,
                message=alert.message[:100],
            )
            return True

        try:
            import httpx

            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": f"*{alert.title}*\n\n{alert.message}",
                "parse_mode": "Markdown",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                response.raise_for_status()

            logger.debug("Telegram alert sent", type=alert.type.value)
            return True

        except Exception as e:
            logger.error("Telegram send failed", error=str(e))
            return False

    def get_recent_alerts(self, count: int = 10) -> list[Alert]:
        """Get recent alerts."""
        return self._alert_history[-count:]
