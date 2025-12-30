"""Database repository for CRUD operations."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import structlog

from src.db.models import (
    Base,
    MarketRecord,
    PnLSnapshotRecord,
    PositionRecord,
    TradeRecord,
)
from src.models import Market, Position, Trade

logger = structlog.get_logger(__name__)


class Repository:
    """
    Async database repository for persistence operations.
    """

    def __init__(self, database_url: str) -> None:
        """
        Initialize repository.

        Args:
            database_url: SQLAlchemy async database URL
        """
        self.database_url = database_url
        self._engine = create_async_engine(database_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def initialize(self) -> None:
        """Create database tables."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized", url=self.database_url[:30] + "...")

    async def close(self) -> None:
        """Close database connection."""
        await self._engine.dispose()

    # Position operations
    async def save_position(self, position: Position) -> None:
        """Save or update a position."""
        async with self._session_factory() as session:
            record = PositionRecord(
                id=position.id,
                market_id=position.market_id,
                state=position.state.value,
                up_token_id=position.up_token_id,
                up_contracts=position.up_contracts,
                up_avg_price=position.up_avg_price,
                up_order_id=position.up_order_id,
                down_token_id=position.down_token_id,
                down_contracts=position.down_contracts,
                down_avg_price=position.down_avg_price,
                down_order_id=position.down_order_id,
                total_cost=position.total_cost,
                settlement_value=position.settlement_value,
                realized_pnl=position.realized_pnl,
                created_at=position.created_at,
                updated_at=datetime.now(),
                settled_at=position.settled_at,
            )
            await session.merge(record)
            await session.commit()

    async def get_position(self, position_id: str) -> PositionRecord | None:
        """Get a position by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(PositionRecord).where(PositionRecord.id == position_id)
            )
            return result.scalar_one_or_none()

    async def get_open_positions(self) -> list[PositionRecord]:
        """Get all open positions."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(PositionRecord).where(PositionRecord.state != "settled")
            )
            return list(result.scalars().all())

    async def get_positions_by_market(self, market_id: str) -> list[PositionRecord]:
        """Get positions for a specific market."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(PositionRecord).where(PositionRecord.market_id == market_id)
            )
            return list(result.scalars().all())

    # Trade operations
    async def save_trade(self, trade: Trade) -> None:
        """Save a trade record."""
        async with self._session_factory() as session:
            record = TradeRecord(
                id=trade.id,
                position_id=trade.position_id,
                order_id=trade.order_id,
                market_id=trade.market_id,
                token_id=trade.token_id,
                outcome_type=str(trade.outcome_type),
                side=trade.side,
                price=trade.price,
                size=trade.size,
                fee=trade.fee,
                executed_at=trade.executed_at,
            )
            session.add(record)
            await session.commit()

    async def get_trades(
        self,
        limit: int = 100,
        position_id: str | None = None,
    ) -> list[TradeRecord]:
        """Get recent trades."""
        async with self._session_factory() as session:
            query = select(TradeRecord).order_by(TradeRecord.executed_at.desc())

            if position_id:
                query = query.where(TradeRecord.position_id == position_id)

            query = query.limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())

    # Market operations
    async def save_market(self, market: Market) -> None:
        """Save or update market metadata."""
        if not market.tokens:
            return

        async with self._session_factory() as session:
            record = MarketRecord(
                id=market.id,
                condition_id=market.condition_id,
                question=market.question,
                slug=market.slug,
                asset=market.asset,
                up_token_id=market.tokens.up_token_id,
                down_token_id=market.tokens.down_token_id,
                end_time=market.end_time,
                updated_at=datetime.now(),
            )
            await session.merge(record)
            await session.commit()

    async def get_market(self, market_id: str) -> MarketRecord | None:
        """Get market by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MarketRecord).where(MarketRecord.id == market_id)
            )
            return result.scalar_one_or_none()

    # P&L operations
    async def save_pnl_snapshot(
        self,
        unrealized: float,
        realized: float,
        open_positions: int,
        exposure: float,
        trades: int,
    ) -> None:
        """Save a P&L snapshot."""
        async with self._session_factory() as session:
            record = PnLSnapshotRecord(
                unrealized_pnl=unrealized,
                realized_pnl=realized,
                total_pnl=unrealized + realized,
                open_positions=open_positions,
                total_exposure=exposure,
                daily_trades=trades,
            )
            session.add(record)
            await session.commit()

    async def get_pnl_history(
        self,
        hours: int = 24,
    ) -> list[PnLSnapshotRecord]:
        """Get P&L snapshots for the last N hours."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=hours)

        async with self._session_factory() as session:
            result = await session.execute(
                select(PnLSnapshotRecord)
                .where(PnLSnapshotRecord.timestamp >= cutoff)
                .order_by(PnLSnapshotRecord.timestamp.asc())
            )
            return list(result.scalars().all())

    # Statistics
    async def get_daily_stats(self, date: str | None = None) -> dict[str, Any]:
        """Get statistics for a specific day."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        from datetime import timedelta
        start = datetime.strptime(date, "%Y-%m-%d")
        end = start + timedelta(days=1)

        async with self._session_factory() as session:
            # Count trades
            trades_result = await session.execute(
                select(TradeRecord).where(
                    TradeRecord.executed_at >= start,
                    TradeRecord.executed_at < end,
                )
            )
            trades = list(trades_result.scalars().all())

            # Get settled positions
            positions_result = await session.execute(
                select(PositionRecord).where(
                    PositionRecord.settled_at >= start,
                    PositionRecord.settled_at < end,
                )
            )
            settled = list(positions_result.scalars().all())

            realized_pnl = sum(p.realized_pnl or 0 for p in settled)
            wins = sum(1 for p in settled if (p.realized_pnl or 0) > 0)

            return {
                "date": date,
                "trades": len(trades),
                "settled_positions": len(settled),
                "realized_pnl": realized_pnl,
                "wins": wins,
                "losses": len(settled) - wins,
                "win_rate": wins / len(settled) if settled else 0,
            }
