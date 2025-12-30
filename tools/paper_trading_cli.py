"""
Paper Trading CLI Tool
Interactive tool for testing strategies with virtual money.
"""

import os
import sys
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.paper_trader import PaperTrader, get_paper_trader
from src.ai.gemini_client import GeminiClient, GeminiModel
from src.ai.bias_analyzer import BiasAnalyzer


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class PaperTradingCLI:
    """Interactive paper trading interface"""
    
    def __init__(self):
        self.paper_trader = get_paper_trader()
        self.gemini = GeminiClient()
        self.bias_analyzer = BiasAnalyzer(self.gemini)
    
    async def run(self):
        """Main CLI loop"""
        print("\n" + "="*60)
        print("📊 POLYMARKET PAPER TRADING SYSTEM")
        print("="*60)
        print("Trade with virtual money to test your strategy!")
        print(f"Starting balance: ${self.paper_trader.portfolio.initial_balance:.2f}")
        print(f"Current balance: ${self.paper_trader.balance:.2f}")
        print("="*60 + "\n")
        
        while True:
            self._show_menu()
            choice = input("\n> ").strip().lower()
            
            if choice == '1':
                await self._place_trade()
            elif choice == '2':
                self._show_pending()
            elif choice == '3':
                self._resolve_trade()
            elif choice == '4':
                self._show_stats()
            elif choice == '5':
                self._show_history()
            elif choice == '6':
                await self._ai_analysis()
            elif choice == '7':
                self._reset_portfolio()
            elif choice in ('q', 'quit', 'exit'):
                print("\n👋 Goodbye!")
                break
            else:
                print("❌ Invalid option")
    
    def _show_menu(self):
        """Display main menu"""
        print("\n" + "-"*40)
        print(f"💰 Balance: ${self.paper_trader.balance:.2f}")
        print("-"*40)
        print("1. Place new trade")
        print("2. View pending trades")
        print("3. Resolve trade")
        print("4. View statistics")
        print("5. Trade history")
        print("6. AI market analysis")
        print("7. Reset portfolio")
        print("q. Quit")
    
    async def _place_trade(self):
        """Interactive trade placement"""
        print("\n📝 NEW PAPER TRADE")
        print("-"*30)
        
        # Asset
        asset = input("Asset (BTC/ETH) [BTC]: ").strip().upper() or "BTC"
        if asset not in ["BTC", "ETH"]:
            print("❌ Invalid asset")
            return
        
        # Side
        side = input("Direction (UP/DOWN) [UP]: ").strip().upper() or "UP"
        if side not in ["UP", "DOWN"]:
            print("❌ Invalid direction")
            return
        
        # Price
        try:
            price_str = input(f"Entry price (e.g., 0.55) [0.50]: ").strip() or "0.50"
            entry_price = float(price_str)
            if not 0 < entry_price < 1:
                raise ValueError("Price must be between 0 and 1")
        except ValueError as e:
            print(f"❌ Invalid price: {e}")
            return
        
        # Size
        try:
            max_size = min(10, self.paper_trader.balance)
            size_str = input(f"Size USDC (max ${max_size:.2f}) [$2]: ").strip() or "2"
            size_usdc = float(size_str)
            if size_usdc <= 0 or size_usdc > self.paper_trader.balance:
                raise ValueError(f"Size must be between $0.01 and ${self.paper_trader.balance:.2f}")
        except ValueError as e:
            print(f"❌ Invalid size: {e}")
            return
        
        # AI analysis
        print("\n🤖 Getting AI analysis...")
        try:
            bias = await self.bias_analyzer.get_bias(asset=asset)
            ai_bias = bias.direction
            ai_confidence = bias.confidence
            print(f"AI says: {ai_bias} ({ai_confidence*100:.0f}% confidence)")
            
            if ai_bias != side:
                confirm = input("⚠️ Trade goes AGAINST AI. Continue? (y/n): ").lower()
                if confirm != 'y':
                    print("Trade cancelled")
                    return
        except Exception as e:
            logger.warning(f"AI analysis failed: {e}")
            ai_bias = "UNKNOWN"
            ai_confidence = 0.0
        
        # Confirm
        print(f"\n📋 Trade Summary:")
        print(f"   Asset: {asset}")
        print(f"   Side: {side}")
        print(f"   Price: ${entry_price:.2f}")
        print(f"   Size: ${size_usdc:.2f}")
        print(f"   Tokens: {size_usdc/entry_price:.2f}")
        
        confirm = input("\nConfirm trade? (y/n): ").lower()
        if confirm != 'y':
            print("Trade cancelled")
            return
        
        # Place trade
        trade = self.paper_trader.place_trade(
            asset=asset,
            market_id=f"paper_{asset.lower()}_flash",
            market_question=f"{asset} Flash Market (Paper)",
            side=side,
            entry_price=entry_price,
            size_usdc=size_usdc,
            ai_bias=ai_bias,
            ai_confidence=ai_confidence,
            notes=f"Manual paper trade"
        )
        
        if trade:
            print(f"\n✅ Trade placed! ID: {trade.id}")
            print(f"💰 New balance: ${self.paper_trader.balance:.2f}")
        else:
            print("❌ Failed to place trade")
    
    def _show_pending(self):
        """Show pending trades"""
        pending = self.paper_trader.get_pending_trades()
        
        print(f"\n⏳ PENDING TRADES ({len(pending)})")
        print("-"*60)
        
        if not pending:
            print("No pending trades")
            return
        
        for trade in pending:
            age = (datetime.now().timestamp() - trade.timestamp) / 60
            print(f"\n  ID: {trade.id}")
            print(f"  {trade.side} {trade.asset} @ ${trade.entry_price:.2f}")
            print(f"  Size: ${trade.size_usdc:.2f} ({trade.tokens_bought:.2f} tokens)")
            print(f"  AI: {trade.ai_bias} ({trade.ai_confidence*100:.0f}%)")
            print(f"  Age: {age:.1f} minutes")
    
    def _resolve_trade(self):
        """Manually resolve a trade"""
        pending = self.paper_trader.get_pending_trades()
        
        if not pending:
            print("\n❌ No pending trades to resolve")
            return
        
        print("\n🎲 RESOLVE TRADE")
        print("-"*30)
        
        for i, trade in enumerate(pending):
            print(f"{i+1}. {trade.id[:20]}... - {trade.side} {trade.asset}")
        
        try:
            idx = int(input("\nSelect trade number: ")) - 1
            if idx < 0 or idx >= len(pending):
                raise ValueError("Invalid selection")
        except ValueError:
            print("❌ Invalid selection")
            return
        
        trade = pending[idx]
        print(f"\nTrade: {trade.side} {trade.asset} @ ${trade.entry_price:.2f}")
        print(f"To win, {trade.asset} needed to go {trade.side}")
        
        result = input("Did trade WIN? (y/n): ").lower()
        if result not in ['y', 'n']:
            print("❌ Invalid response")
            return
        
        won = result == 'y'
        resolved = self.paper_trader.resolve_trade(trade.id, won)
        
        if resolved:
            emoji = "🎉" if won else "😞"
            print(f"\n{emoji} Trade resolved!")
            print(f"P&L: ${resolved.pnl:+.2f}")
            print(f"💰 New balance: ${self.paper_trader.balance:.2f}")
    
    def _show_stats(self):
        """Display portfolio statistics"""
        stats = self.paper_trader.get_stats()
        
        print("\n📊 PORTFOLIO STATISTICS")
        print("="*40)
        
        p = stats['portfolio']
        print(f"\n💰 Portfolio:")
        print(f"   Initial: ${p['initial_balance']:.2f}")
        print(f"   Current: ${p['current_balance']:.2f}")
        print(f"   P&L: ${p['total_pnl']:+.2f} ({p['roi']})")
        print(f"   Peak: ${p['peak_balance']:.2f}")
        print(f"   Max Drawdown: {p['max_drawdown']}")
        
        t = stats['trades']
        print(f"\n📈 Trades:")
        print(f"   Total: {t['total']}")
        print(f"   Pending: {t['pending']}")
        print(f"   Won: {t['winning']}")
        print(f"   Lost: {t['losing']}")
        print(f"   Win Rate: {t['win_rate']}")
        
        m = stats['metrics']
        print(f"\n📉 Metrics:")
        print(f"   Avg Win: {m['avg_win']}")
        print(f"   Avg Loss: {m['avg_loss']}")
        print(f"   Profit Factor: {m['profit_factor']:.2f}")
    
    def _show_history(self):
        """Show trade history"""
        trades = self.paper_trader.get_recent_trades(20)
        
        print(f"\n📜 RECENT TRADES")
        print("-"*60)
        
        if not trades:
            print("No trades yet")
            return
        
        for trade in trades:
            dt = datetime.fromtimestamp(trade.timestamp)
            status_emoji = {
                'pending': '⏳',
                'won': '✅',
                'lost': '❌',
                'cancelled': '🚫'
            }.get(trade.status.value, '?')
            
            pnl_str = f"${trade.pnl:+.2f}" if trade.status.value != 'pending' else "..."
            
            print(f"{status_emoji} {dt.strftime('%m/%d %H:%M')} | "
                  f"{trade.side:4} {trade.asset} @ ${trade.entry_price:.2f} | "
                  f"${trade.size_usdc:.2f} | P&L: {pnl_str}")
    
    async def _ai_analysis(self):
        """Get AI market analysis"""
        print("\n🤖 AI MARKET ANALYSIS")
        print("-"*30)
        
        asset = input("Asset (BTC/ETH) [BTC]: ").strip().upper() or "BTC"
        
        print(f"\nAnalyzing {asset}...")
        
        try:
            bias = await self.bias_analyzer.get_bias(asset=asset)
            
            print(f"\n📊 {asset} Analysis:")
            print(f"   Direction: {bias.direction}")
            print(f"   Confidence: {bias.confidence*100:.0f}%")
            print(f"   Reasoning: {bias.reasoning}")
            print(f"   Timestamp: {datetime.fromtimestamp(bias.timestamp)}")
            print(f"   Source: {bias.model_used}")
            
            if bias.confidence >= 0.7:
                print(f"\n💡 Recommendation: Consider {bias.direction} position")
            else:
                print(f"\n⚠️ Low confidence - consider waiting")
                
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
    
    def _reset_portfolio(self):
        """Reset paper trading portfolio"""
        print("\n⚠️ RESET PORTFOLIO")
        print("-"*30)
        print("This will delete all trades and reset balance!")
        
        confirm = input("Are you sure? (type 'RESET' to confirm): ")
        if confirm != 'RESET':
            print("Cancelled")
            return
        
        try:
            balance = input("New starting balance [$100]: ").strip() or "100"
            balance = float(balance)
        except ValueError:
            balance = 100.0
        
        self.paper_trader.reset(balance)
        print(f"✅ Portfolio reset with ${balance:.2f}")


async def main():
    """Entry point"""
    cli = PaperTradingCLI()
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())
