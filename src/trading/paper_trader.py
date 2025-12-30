"""
Paper Trading System
Simulates trades without executing real orders.
Tracks virtual P&L with real market prices.
"""

import os
import json
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Trade lifecycle status"""
    PENDING = "pending"         # Trade placed, market not resolved
    WON = "won"                 # Trade won (received $1 per token)
    LOST = "lost"               # Trade lost (received $0)
    CANCELLED = "cancelled"     # Trade cancelled


@dataclass
class PaperTrade:
    """Record of a simulated trade"""
    id: str
    timestamp: float
    asset: str                  # BTC, ETH
    market_id: str
    market_question: str
    
    # Position details
    side: str                   # "UP" or "DOWN"
    entry_price: float          # Price paid per token
    size_usdc: float            # Total USDC spent
    tokens_bought: float        # Number of tokens
    
    # AI decision
    ai_bias: str                # AI prediction
    ai_confidence: float        # AI confidence level
    
    # Resolution
    status: TradeStatus = TradeStatus.PENDING
    exit_price: Optional[float] = None
    pnl: float = 0.0
    resolved_at: Optional[float] = None
    
    # Metadata
    notes: str = ""
    
    def resolve(self, won: bool) -> None:
        """Resolve the trade"""
        self.status = TradeStatus.WON if won else TradeStatus.LOST
        self.exit_price = 1.0 if won else 0.0
        self.pnl = (self.exit_price - self.entry_price) * self.tokens_bought
        self.resolved_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PaperTrade':
        """Create from dictionary"""
        data['status'] = TradeStatus(data['status'])
        return cls(**data)


@dataclass
class PaperPortfolio:
    """Virtual portfolio state"""
    initial_balance: float
    current_balance: float
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    peak_balance: float = 0.0
    max_drawdown: float = 0.0
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate"""
        resolved = self.winning_trades + self.losing_trades
        return self.winning_trades / resolved if resolved > 0 else 0.0
    
    @property
    def roi(self) -> float:
        """Return on investment"""
        return (self.current_balance - self.initial_balance) / self.initial_balance
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PaperTrader:
    """
    Paper trading system for strategy validation.
    
    Features:
    - Simulates trades without real execution
    - Tracks virtual P&L with real prices
    - Persists state to JSON file
    - Provides detailed statistics
    """
    
    DEFAULT_INITIAL_BALANCE = 100.0  # $100 virtual starting balance
    DATA_DIR = "data/paper_trading"
    
    def __init__(
        self,
        initial_balance: Optional[float] = None,
        data_dir: Optional[str] = None
    ):
        """
        Initialize paper trader.
        
        Args:
            initial_balance: Starting virtual balance
            data_dir: Directory for persisting trades
        """
        self._data_dir = Path(data_dir or self.DATA_DIR)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        
        self._trades_file = self._data_dir / "trades.json"
        self._portfolio_file = self._data_dir / "portfolio.json"
        
        # Load or create portfolio
        self._portfolio = self._load_portfolio(
            initial_balance or self.DEFAULT_INITIAL_BALANCE
        )
        self._trades: List[PaperTrade] = self._load_trades()
        
        logger.info(
            f"PaperTrader initialized: balance=${self._portfolio.current_balance:.2f}, "
            f"trades={len(self._trades)}"
        )
    
    def place_trade(
        self,
        asset: str,
        market_id: str,
        market_question: str,
        side: str,
        entry_price: float,
        size_usdc: float,
        ai_bias: str,
        ai_confidence: float,
        notes: str = ""
    ) -> Optional[PaperTrade]:
        """
        Place a simulated trade.
        
        Args:
            asset: BTC, ETH
            market_id: Polymarket market ID
            market_question: Market question text
            side: "UP" or "DOWN"
            entry_price: Price per token
            size_usdc: Amount to spend
            ai_bias: AI prediction
            ai_confidence: AI confidence
            notes: Optional notes
            
        Returns:
            PaperTrade if successful, None if insufficient balance
        """
        # Check balance
        if size_usdc > self._portfolio.current_balance:
            logger.warning(
                f"Insufficient balance: ${size_usdc:.2f} > ${self._portfolio.current_balance:.2f}"
            )
            return None
        
        # Calculate tokens
        tokens_bought = size_usdc / entry_price
        
        # Create trade
        trade = PaperTrade(
            id=f"paper_{int(time.time()*1000)}",
            timestamp=time.time(),
            asset=asset,
            market_id=market_id,
            market_question=market_question,
            side=side,
            entry_price=entry_price,
            size_usdc=size_usdc,
            tokens_bought=tokens_bought,
            ai_bias=ai_bias,
            ai_confidence=ai_confidence,
            notes=notes
        )
        
        # Deduct from balance
        self._portfolio.current_balance -= size_usdc
        self._portfolio.total_trades += 1
        
        # Store trade
        self._trades.append(trade)
        self._save()
        
        logger.info(
            f"📝 PAPER TRADE: {side} {asset} @ ${entry_price:.2f} "
            f"(${size_usdc:.2f}, {tokens_bought:.2f} tokens)"
        )
        
        return trade
    
    def resolve_trade(self, trade_id: str, won: bool) -> Optional[PaperTrade]:
        """
        Resolve a pending trade.
        
        Args:
            trade_id: Trade ID to resolve
            won: Whether the trade won
            
        Returns:
            Updated trade or None if not found
        """
        trade = self._find_trade(trade_id)
        if not trade:
            logger.warning(f"Trade not found: {trade_id}")
            return None
        
        if trade.status != TradeStatus.PENDING:
            logger.warning(f"Trade already resolved: {trade_id}")
            return trade
        
        # Resolve trade
        trade.resolve(won)
        
        # Update portfolio
        if won:
            # Return original stake + profit
            self._portfolio.current_balance += trade.tokens_bought  # $1 per token
            self._portfolio.winning_trades += 1
        else:
            self._portfolio.losing_trades += 1
        
        self._portfolio.total_pnl += trade.pnl
        
        # Update peak and drawdown
        if self._portfolio.current_balance > self._portfolio.peak_balance:
            self._portfolio.peak_balance = self._portfolio.current_balance
        
        drawdown = (self._portfolio.peak_balance - self._portfolio.current_balance) / self._portfolio.peak_balance
        if drawdown > self._portfolio.max_drawdown:
            self._portfolio.max_drawdown = drawdown
        
        self._save()
        
        status_emoji = "✅" if won else "❌"
        logger.info(
            f"{status_emoji} PAPER RESOLVED: {trade.side} {trade.asset} "
            f"P&L: ${trade.pnl:+.2f}"
        )
        
        return trade
    
    def resolve_all_pending(self, results: Dict[str, bool]) -> List[PaperTrade]:
        """
        Resolve multiple pending trades.
        
        Args:
            results: Dict of {trade_id: won}
            
        Returns:
            List of resolved trades
        """
        resolved = []
        for trade_id, won in results.items():
            trade = self.resolve_trade(trade_id, won)
            if trade:
                resolved.append(trade)
        return resolved
    
    def get_pending_trades(self) -> List[PaperTrade]:
        """Get all pending trades"""
        return [t for t in self._trades if t.status == TradeStatus.PENDING]
    
    def get_recent_trades(self, limit: int = 10) -> List[PaperTrade]:
        """Get most recent trades"""
        return sorted(self._trades, key=lambda t: t.timestamp, reverse=True)[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        pending = len(self.get_pending_trades())
        resolved = self._portfolio.winning_trades + self._portfolio.losing_trades
        
        # Calculate average metrics
        if resolved > 0:
            resolved_trades = [t for t in self._trades if t.status != TradeStatus.PENDING]
            avg_win = sum(t.pnl for t in resolved_trades if t.pnl > 0) / max(self._portfolio.winning_trades, 1)
            avg_loss = sum(t.pnl for t in resolved_trades if t.pnl < 0) / max(self._portfolio.losing_trades, 1)
        else:
            avg_win = avg_loss = 0
        
        return {
            "portfolio": {
                "initial_balance": self._portfolio.initial_balance,
                "current_balance": self._portfolio.current_balance,
                "total_pnl": self._portfolio.total_pnl,
                "roi": f"{self._portfolio.roi * 100:.2f}%",
                "peak_balance": self._portfolio.peak_balance,
                "max_drawdown": f"{self._portfolio.max_drawdown * 100:.2f}%"
            },
            "trades": {
                "total": self._portfolio.total_trades,
                "pending": pending,
                "resolved": resolved,
                "winning": self._portfolio.winning_trades,
                "losing": self._portfolio.losing_trades,
                "win_rate": f"{self._portfolio.win_rate * 100:.1f}%"
            },
            "metrics": {
                "avg_win": f"${avg_win:.2f}",
                "avg_loss": f"${avg_loss:.2f}",
                "profit_factor": abs(avg_win / avg_loss) if avg_loss != 0 else 0
            }
        }
    
    def reset(self, initial_balance: Optional[float] = None) -> None:
        """Reset paper trading (clear all trades)"""
        balance = initial_balance or self.DEFAULT_INITIAL_BALANCE
        self._portfolio = PaperPortfolio(
            initial_balance=balance,
            current_balance=balance,
            peak_balance=balance
        )
        self._trades = []
        self._save()
        logger.info(f"Paper trading reset with ${balance:.2f}")
    
    def _find_trade(self, trade_id: str) -> Optional[PaperTrade]:
        """Find trade by ID"""
        for trade in self._trades:
            if trade.id == trade_id:
                return trade
        return None
    
    def _load_portfolio(self, default_balance: float) -> PaperPortfolio:
        """Load portfolio from file or create new"""
        if self._portfolio_file.exists():
            try:
                with open(self._portfolio_file, 'r') as f:
                    data = json.load(f)
                    return PaperPortfolio(**data)
            except Exception as e:
                logger.error(f"Error loading portfolio: {e}")
        
        return PaperPortfolio(
            initial_balance=default_balance,
            current_balance=default_balance,
            peak_balance=default_balance
        )
    
    def _load_trades(self) -> List[PaperTrade]:
        """Load trades from file"""
        if self._trades_file.exists():
            try:
                with open(self._trades_file, 'r') as f:
                    data = json.load(f)
                    return [PaperTrade.from_dict(t) for t in data]
            except Exception as e:
                logger.error(f"Error loading trades: {e}")
        return []
    
    def _save(self) -> None:
        """Persist state to files"""
        try:
            with open(self._portfolio_file, 'w') as f:
                json.dump(self._portfolio.to_dict(), f, indent=2)
            
            with open(self._trades_file, 'w') as f:
                json.dump([t.to_dict() for t in self._trades], f, indent=2)
        except Exception as e:
            logger.error(f"Error saving paper trading state: {e}")
    
    @property
    def balance(self) -> float:
        """Current virtual balance"""
        return self._portfolio.current_balance
    
    @property
    def portfolio(self) -> PaperPortfolio:
        """Portfolio state"""
        return self._portfolio


# Global instance
_paper_trader: Optional[PaperTrader] = None


def get_paper_trader() -> PaperTrader:
    """Get or create global paper trader"""
    global _paper_trader
    if _paper_trader is None:
        _paper_trader = PaperTrader()
    return _paper_trader
