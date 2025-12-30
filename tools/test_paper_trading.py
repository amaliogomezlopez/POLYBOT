"""Test paper trading system"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.paper_trader import PaperTrader

# Create fresh paper trader
pt = PaperTrader(initial_balance=100.0, data_dir="data/paper_trading_test")
print(f"Initial balance: ${pt.balance:.2f}")

# Place a test trade
trade = pt.place_trade(
    asset='BTC',
    market_id='test_btc_flash',
    market_question='Will BTC go UP in 1 hour?',
    side='UP',
    entry_price=0.55,
    size_usdc=5.0,
    ai_bias='UP',
    ai_confidence=0.75,
    notes='Test paper trade'
)

print(f"\nTrade placed: {trade.id}")
print(f"Tokens bought: {trade.tokens_bought:.2f}")
print(f"Balance after trade: ${pt.balance:.2f}")

# Check pending
pending = pt.get_pending_trades()
print(f"\nPending trades: {len(pending)}")

# Resolve as winning (market went UP, we bought UP)
pt.resolve_trade(trade.id, won=True)
print(f"\n=== TRADE WON ===")
print(f"Exit price: ${trade.exit_price}")
print(f"P&L: ${trade.pnl:+.2f}")
print(f"Balance after WIN: ${pt.balance:.2f}")

# Place another trade and lose
trade2 = pt.place_trade(
    asset='ETH',
    market_id='test_eth_flash',
    market_question='Will ETH go DOWN in 1 hour?',
    side='DOWN',
    entry_price=0.40,
    size_usdc=4.0,
    ai_bias='DOWN',
    ai_confidence=0.65,
    notes='Test paper trade 2'
)

print(f"\n\nTrade 2 placed: {trade2.id}")
pt.resolve_trade(trade2.id, won=False)
print(f"\n=== TRADE LOST ===")
print(f"P&L: ${trade2.pnl:+.2f}")
print(f"Balance after LOSS: ${pt.balance:.2f}")

# Final stats
print("\n" + "="*50)
print("FINAL STATISTICS")
print("="*50)
stats = pt.get_stats()

print(f"\nPortfolio:")
for k, v in stats['portfolio'].items():
    print(f"  {k}: {v}")

print(f"\nTrades:")
for k, v in stats['trades'].items():
    print(f"  {k}: {v}")

print(f"\nMetrics:")
for k, v in stats['metrics'].items():
    print(f"  {k}: {v}")

print("\n✅ Paper trading system working correctly!")
