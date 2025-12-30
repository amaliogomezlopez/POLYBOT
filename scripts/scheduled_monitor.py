"""
🔄 SCHEDULED TAIL BETTING MONITOR
==================================
Runs continuously on server to:
1. Monitor tail bets for resolutions
2. Scan for new opportunities
3. Log results and send alerts
4. Collect data for XGBoost training

Usage:
    python scripts/scheduled_monitor.py              # Run once
    python scripts/scheduled_monitor.py --daemon     # Run as daemon
    python scripts/scheduled_monitor.py --interval 30  # Custom interval (minutes)
"""

import asyncio
import json
import httpx
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import argparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/scheduled_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

# Ensure logs directory exists
Path('logs').mkdir(exist_ok=True)

# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    BETS_FILE = Path('data/tail_bot/bets.json')
    RESOLVED_FILE = Path('data/tail_bot/resolved.json')
    TRAINING_FILE = Path('data/tail_bot/training_data.json')
    
    # Scanning
    MAX_PRICE = 0.04
    MIN_PRICE = 0.001
    STAKE = 2.0
    
    # Monitoring
    DEFAULT_INTERVAL_MINUTES = 30
    MAX_NEW_BETS_PER_CYCLE = 10

# =============================================================================
# MONITOR CLASS
# =============================================================================

class ScheduledMonitor:
    """
    Automated monitoring system for tail betting.
    """
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.stats = {
            'cycles': 0,
            'resolutions_found': 0,
            'new_bets_placed': 0,
            'errors': 0
        }
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30)
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    # -------------------------------------------------------------------------
    # FILE OPERATIONS
    # -------------------------------------------------------------------------
    
    def load_json(self, path: Path) -> list:
        if path.exists():
            return json.loads(path.read_text())
        return []
    
    def save_json(self, path: Path, data: list):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))
    
    # -------------------------------------------------------------------------
    # RESOLUTION CHECKING
    # -------------------------------------------------------------------------
    
    async def check_resolution(self, condition_id: str) -> Optional[str]:
        """Check if market has resolved via CLOB API."""
        try:
            url = f"https://clob.polymarket.com/markets/{condition_id}"
            resp = await self.client.get(url)
            
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            if data.get("closed"):
                for token in data.get("tokens", []):
                    if float(token.get("price", 0)) >= 0.99:
                        return token.get("outcome")
            
            return None
        except Exception:
            return None
    
    async def check_all_resolutions(self) -> dict:
        """Check all pending bets for resolutions."""
        bets = self.load_json(Config.BETS_FILE)
        resolved = self.load_json(Config.RESOLVED_FILE)
        resolved_ids = {r.get("condition_id") for r in resolved}
        
        pending = [b for b in bets if b.get("status") == "pending" 
                   and b.get("condition_id") not in resolved_ids]
        
        results = {'checked': 0, 'resolved': [], 'won': 0, 'lost': 0}
        
        for bet in pending:
            result = await self.check_resolution(bet.get("condition_id"))
            results['checked'] += 1
            
            if result:
                status = "won" if result == "Yes" else "lost"
                bet["status"] = status
                bet["resolved_at"] = datetime.now().isoformat()
                
                if status == "won":
                    mult = bet.get("potential_multiplier") or (1 / bet.get("entry_price", 0.02))
                    bet["payout"] = bet.get("stake", 2) * mult
                    bet["profit"] = bet["payout"] - bet.get("stake", 2)
                    results['won'] += 1
                else:
                    bet["payout"] = 0
                    bet["profit"] = -bet.get("stake", 2)
                    results['lost'] += 1
                
                resolved.append(bet)
                results['resolved'].append(bet)
                
                logger.info(f"{'🎉 WON' if status == 'won' else '❌ LOST'}: {bet.get('question', '')[:50]}")
            
            await asyncio.sleep(0.1)
        
        if results['resolved']:
            self.save_json(Config.BETS_FILE, bets)
            self.save_json(Config.RESOLVED_FILE, resolved)
            self._append_training_data(results['resolved'])
        
        return results
    
    def _append_training_data(self, resolved_bets: list):
        """Append resolved bets to training data for XGBoost."""
        training = self.load_json(Config.TRAINING_FILE)
        
        for bet in resolved_bets:
            training.append({
                'question': bet.get('question', ''),
                'entry_price': bet.get('entry_price', 0),
                'multiplier': bet.get('potential_multiplier', 50),
                'ml_score': bet.get('ml_score', 0.5),
                'outcome': 1 if bet.get('status') == 'won' else 0,
                'profit': bet.get('profit', 0),
                'resolved_at': bet.get('resolved_at')
            })
        
        self.save_json(Config.TRAINING_FILE, training)
        logger.info(f"Added {len(resolved_bets)} samples to training data (total: {len(training)})")
    
    # -------------------------------------------------------------------------
    # OPPORTUNITY SCANNING
    # -------------------------------------------------------------------------
    
    async def scan_opportunities(self) -> list:
        """Scan for new tail opportunities."""
        existing_ids = {b.get("condition_id") for b in self.load_json(Config.BETS_FILE)}
        
        opportunities = []
        cursors = ['LTE=', 'MA==', 'MjA=', 'NDA=', 'NjA=']
        
        for cursor in cursors:
            try:
                url = f"https://clob.polymarket.com/sampling-markets?next_cursor={cursor}"
                resp = await self.client.get(url)
                
                if resp.status_code != 200:
                    continue
                
                for m in resp.json().get("data", []):
                    cid = m.get("condition_id")
                    if cid in existing_ids:
                        continue
                    
                    for t in m.get("tokens", []):
                        if t.get("outcome") == "Yes":
                            price = float(t.get("price", 1))
                            if Config.MIN_PRICE < price < Config.MAX_PRICE:
                                opportunities.append({
                                    'condition_id': cid,
                                    'question': m.get('question', ''),
                                    'price': price,
                                    'mult': round(1/price, 1),
                                    'token_id': t.get('token_id')
                                })
                            break
            except Exception as e:
                logger.error(f"Error scanning: {e}")
        
        # Deduplicate
        seen = set()
        unique = []
        for o in opportunities:
            if o['condition_id'] not in seen:
                seen.add(o['condition_id'])
                unique.append(o)
        
        return unique
    
    async def auto_place_bets(self, opportunities: list, max_bets: int = None) -> int:
        """Automatically place paper bets on best opportunities."""
        max_bets = max_bets or Config.MAX_NEW_BETS_PER_CYCLE
        
        # Score and sort
        scored = []
        for opp in opportunities:
            score = self._calculate_ml_score(opp)
            if score >= 0.55:
                opp['ml_score'] = score
                scored.append(opp)
        
        scored.sort(key=lambda x: x['ml_score'], reverse=True)
        to_place = scored[:max_bets]
        
        if not to_place:
            return 0
        
        bets = self.load_json(Config.BETS_FILE)
        
        for opp in to_place:
            bet = {
                'id': f"TAIL-{int(datetime.now().timestamp())}-{len(bets)}",
                'timestamp': datetime.now().timestamp(),
                'question': opp['question'],
                'condition_id': opp['condition_id'],
                'token_id': opp.get('token_id'),
                'entry_price': opp['price'],
                'stake': Config.STAKE,
                'size': round(Config.STAKE / opp['price'], 2),
                'potential_return': round(Config.STAKE / opp['price'], 2),
                'potential_multiplier': opp['mult'],
                'ml_score': opp.get('ml_score', 0.5),
                'status': 'pending',
                'exit_price': None,
                'pnl': 0.0,
                'resolved_at': None
            }
            bets.append(bet)
            logger.info(f"📝 New bet: ${opp['price']:.3f} ({opp['mult']:.0f}x) - {opp['question'][:40]}...")
        
        self.save_json(Config.BETS_FILE, bets)
        return len(to_place)
    
    def _calculate_ml_score(self, market: dict) -> float:
        """Simple ML scoring."""
        score = 0.50
        q = market.get('question', '').lower()
        mult = market.get('mult', 50)
        
        # Category weights
        weights = {
            'crypto': 0.12, 'bitcoin': 0.10, 'ethereum': 0.08,
            'nvidia': 0.08, 'tesla': 0.10, 'apple': 0.05,
            'ai': 0.08, 'openai': 0.06, 'trump': 0.04,
            'sports': -0.05, 'weather': -0.03
        }
        
        for kw, w in weights.items():
            if kw in q:
                score += w
        
        if mult >= 500:
            score += 0.05
        elif mult >= 200:
            score += 0.02
        
        return max(0, min(1, score))
    
    # -------------------------------------------------------------------------
    # STATISTICS
    # -------------------------------------------------------------------------
    
    def get_portfolio_stats(self) -> dict:
        """Get current portfolio statistics."""
        bets = self.load_json(Config.BETS_FILE)
        resolved = self.load_json(Config.RESOLVED_FILE)
        
        total_bets = len(bets)
        total_invested = sum(b.get('stake', 2) for b in bets)
        pending = len([b for b in bets if b.get('status') == 'pending'])
        
        won = len([r for r in resolved if r.get('status') == 'won'])
        lost = len([r for r in resolved if r.get('status') == 'lost'])
        
        total_payout = sum(r.get('payout', 0) for r in resolved)
        total_pnl = total_payout - sum(r.get('stake', 2) for r in resolved)
        
        return {
            'total_bets': total_bets,
            'total_invested': total_invested,
            'pending': pending,
            'resolved': len(resolved),
            'won': won,
            'lost': lost,
            'hit_rate': won / len(resolved) * 100 if resolved else 0,
            'total_pnl': total_pnl,
            'roi': total_pnl / total_invested * 100 if total_invested > 0 else 0
        }
    
    # -------------------------------------------------------------------------
    # MAIN CYCLE
    # -------------------------------------------------------------------------
    
    async def run_cycle(self, auto_bet: bool = True):
        """Run a single monitoring cycle."""
        self.stats['cycles'] += 1
        cycle_start = datetime.now()
        
        logger.info("=" * 60)
        logger.info(f"🔄 CYCLE {self.stats['cycles']} - {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        # 1. Check resolutions
        logger.info("📊 Checking resolutions...")
        res_results = await self.check_all_resolutions()
        logger.info(f"   Checked: {res_results['checked']}, Resolved: {len(res_results['resolved'])}")
        
        if res_results['resolved']:
            self.stats['resolutions_found'] += len(res_results['resolved'])
            logger.info(f"   Won: {res_results['won']}, Lost: {res_results['lost']}")
        
        # 2. Scan opportunities
        logger.info("🔍 Scanning opportunities...")
        opportunities = await self.scan_opportunities()
        logger.info(f"   Found: {len(opportunities)} new tail markets")
        
        # 3. Auto-place bets
        if auto_bet and opportunities:
            logger.info("💰 Auto-placing bets...")
            placed = await self.auto_place_bets(opportunities)
            self.stats['new_bets_placed'] += placed
            logger.info(f"   Placed: {placed} new bets")
        
        # 4. Portfolio stats
        stats = self.get_portfolio_stats()
        logger.info("-" * 40)
        logger.info(f"📈 Portfolio: {stats['total_bets']} bets, ${stats['total_invested']:.0f} invested")
        logger.info(f"   Pending: {stats['pending']}, Resolved: {stats['resolved']}")
        if stats['resolved'] > 0:
            logger.info(f"   Hit Rate: {stats['hit_rate']:.1f}%, P&L: ${stats['total_pnl']:+.2f}")
        
        duration = (datetime.now() - cycle_start).total_seconds()
        logger.info(f"⏱️ Cycle completed in {duration:.1f}s")
    
    async def run_daemon(self, interval_minutes: int = 30, auto_bet: bool = True):
        """Run as daemon with periodic cycles."""
        logger.info(f"🚀 Starting daemon mode (interval: {interval_minutes} min)")
        logger.info("   Press Ctrl+C to stop\n")
        
        while True:
            try:
                await self.run_cycle(auto_bet=auto_bet)
                logger.info(f"\n⏰ Next cycle in {interval_minutes} minutes...\n")
                await asyncio.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("\n👋 Daemon stopped by user")
                break
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"❌ Error in cycle: {e}")
                await asyncio.sleep(60)

# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Scheduled Tail Betting Monitor")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run as daemon")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Interval (minutes)")
    parser.add_argument("--no-auto-bet", action="store_true", help="Disable auto-betting")
    
    args = parser.parse_args()
    
    async with ScheduledMonitor() as monitor:
        if args.daemon:
            await monitor.run_daemon(
                interval_minutes=args.interval,
                auto_bet=not args.no_auto_bet
            )
        else:
            await monitor.run_cycle(auto_bet=not args.no_auto_bet)

if __name__ == "__main__":
    asyncio.run(main())
