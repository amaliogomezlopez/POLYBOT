"""
🔄 PRODUCTION SCHEDULED MONITOR
================================
Runs continuously on server with dual storage:
- PostgreSQL (primary): Robust, queryable, persistent
- JSON files (backup): Quick access, easy debugging

Features:
1. Monitor tail bets for resolutions
2. Scan for new opportunities  
3. Auto-place bets with ML scoring
4. Log to database and files
5. Collect XGBoost training data
"""

import asyncio
import json
import httpx
import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
from decimal import Decimal
import argparse

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging
Path('logs').mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/scheduled_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# TRY TO IMPORT DATABASE (GRACEFUL FALLBACK TO JSON-ONLY)
# =============================================================================

try:
    from src.db.production_db import (
        get_session, Market, Position, Order, PriceSnapshot,
        TradingSession, SystemLog, MLTrainingData,
        BetStatus, BetType, OrderSide, OrderStatus,
        get_portfolio_stats
    )
    DB_AVAILABLE = True
    logger.info("✅ Database connection available")
except Exception as e:
    DB_AVAILABLE = False
    logger.warning(f"⚠️ Database not available, using JSON only: {e}")

# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    # File storage (always used as backup)
    BETS_FILE = Path('data/tail_bot/bets.json')
    RESOLVED_FILE = Path('data/tail_bot/resolved.json')
    TRAINING_FILE = Path('data/tail_bot/training_data.json')
    
    # Trading parameters
    MAX_PRICE = 0.04
    MIN_PRICE = 0.001
    STAKE = 2.0
    MIN_ML_SCORE = 0.55
    
    # Monitoring
    DEFAULT_INTERVAL_MINUTES = 30
    MAX_NEW_BETS_PER_CYCLE = 10

# =============================================================================
# ML SCORER
# =============================================================================

class TailScorer:
    """ML-based scoring for tail bets."""
    
    CATEGORY_WEIGHTS = {
        'crypto': 0.12, 'bitcoin': 0.10, 'ethereum': 0.08,
        'nvidia': 0.08, 'tesla': 0.10, 'apple': 0.05,
        'ai': 0.08, 'openai': 0.06, 'trump': 0.04,
        'sports': -0.05, 'weather': -0.03, 'celebrity': -0.02
    }
    
    def score(self, question: str, multiplier: float) -> float:
        """Calculate ML score for a market."""
        score = 0.50
        question_lower = question.lower()
        
        for keyword, weight in self.CATEGORY_WEIGHTS.items():
            if keyword in question_lower:
                score += weight
        
        if multiplier >= 500:
            score += 0.05
        elif multiplier >= 200:
            score += 0.02
        
        return max(0.0, min(1.0, score))
    
    def extract_features(self, market: dict) -> dict:
        """Extract features for ML training."""
        question = market.get('question', '').lower()
        return {
            'has_crypto': any(kw in question for kw in ['crypto', 'bitcoin', 'ethereum']),
            'has_stock': any(kw in question for kw in ['nvidia', 'tesla', 'apple', 'stock']),
            'has_ai': any(kw in question for kw in ['ai', 'openai', 'gpt']),
            'has_politics': any(kw in question for kw in ['trump', 'biden', 'election']),
            'has_sports': 'sports' in question or 'nba' in question or 'nfl' in question,
            'question_length': len(market.get('question', '')),
            'multiplier': market.get('mult', 50),
            'entry_price': market.get('price', 0.02),
        }

# =============================================================================
# PRODUCTION MONITOR
# =============================================================================

class ProductionMonitor:
    """
    Production-ready monitoring system with dual storage.
    """
    
    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.scorer = TailScorer()
        self.session_id = f"SESSION-{int(datetime.now().timestamp())}"
        self.stats = {
            'cycles': 0,
            'resolutions_found': 0,
            'new_bets_placed': 0,
            'errors': 0
        }
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30)
        self._init_session()
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    def _init_session(self):
        """Initialize trading session in database."""
        if DB_AVAILABLE:
            try:
                db = get_session()
                session = TradingSession(
                    session_id=self.session_id,
                    is_paper=True
                )
                db.add(session)
                db.commit()
                db.close()
            except Exception as e:
                logger.error(f"Failed to init session: {e}")
    
    # -------------------------------------------------------------------------
    # JSON FILE OPERATIONS (Always used as backup)
    # -------------------------------------------------------------------------
    
    def load_json(self, path: Path) -> list:
        """Load data from JSON file."""
        if path.exists():
            return json.loads(path.read_text())
        return []
    
    def save_json(self, path: Path, data: list):
        """Save data to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))
    
    # -------------------------------------------------------------------------
    # DATABASE OPERATIONS
    # -------------------------------------------------------------------------
    
    def save_position_to_db(self, bet_data: dict) -> Optional[str]:
        """Save position to database."""
        if not DB_AVAILABLE:
            return None
        
        try:
            db = get_session()
            
            # Get or create market
            condition_id = bet_data['condition_id']
            market = db.query(Market).filter_by(condition_id=condition_id).first()
            if not market:
                market = Market(
                    condition_id=condition_id,
                    question=bet_data.get('question', ''),
                )
                db.add(market)
                db.flush()
            
            # Create position
            entry_price = bet_data.get('entry_price', 0.02)
            position = Position(
                position_id=bet_data['id'],
                market_id=market.id,
                condition_id=condition_id,
                token_id=bet_data.get('token_id'),
                side="Yes",
                bet_type=BetType.TAIL,
                entry_price=Decimal(str(entry_price)),
                size=Decimal(str(bet_data.get('size', 100))),
                stake=Decimal(str(bet_data.get('stake', 2.0))),
                potential_multiplier=bet_data.get('potential_multiplier', 50),
                ml_score=bet_data.get('ml_score'),
                ml_features=bet_data.get('ml_features', {}),
                status=BetStatus.PENDING,
                is_paper=True,
            )
            db.add(position)
            db.commit()
            
            position_id = position.position_id
            db.close()
            
            return position_id
            
        except Exception as e:
            logger.error(f"DB save error: {e}")
            return None
    
    def update_position_resolution(self, position_id: str, status: str, payout: float, profit: float):
        """Update position with resolution data."""
        if not DB_AVAILABLE:
            return
        
        try:
            db = get_session()
            position = db.query(Position).filter_by(position_id=position_id).first()
            
            if position:
                position.status = BetStatus.WON if status == 'won' else BetStatus.LOST
                position.resolved_at = datetime.utcnow()
                position.payout = Decimal(str(payout))
                position.profit = Decimal(str(profit))
                position.exit_price = Decimal('1.0') if status == 'won' else Decimal('0.0')
                
                db.commit()
            
            db.close()
            
        except Exception as e:
            logger.error(f"DB update error: {e}")
    
    def log_to_db(self, level: str, component: str, message: str, details: dict = None):
        """Log entry to database."""
        if not DB_AVAILABLE:
            return
        
        try:
            db = get_session()
            log = SystemLog(
                level=level,
                component=component,
                message=message,
                details=details or {}
            )
            db.add(log)
            db.commit()
            db.close()
        except:
            pass
    
    # -------------------------------------------------------------------------
    # RESOLUTION CHECKING
    # -------------------------------------------------------------------------
    
    async def check_resolution(self, condition_id: str) -> Optional[str]:
        """Check if market has resolved."""
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
        except:
            return None
    
    async def check_all_resolutions(self) -> dict:
        """Check all pending bets for resolutions."""
        # Load from JSON (source of truth for pending)
        bets = self.load_json(Config.BETS_FILE)
        resolved = self.load_json(Config.RESOLVED_FILE)
        resolved_ids = {r.get("condition_id") for r in resolved}
        
        pending = [b for b in bets if b.get("status") == "pending" 
                   and b.get("condition_id") not in resolved_ids]
        
        results = {'checked': 0, 'resolved': [], 'won': 0, 'lost': 0}
        
        for bet in pending:
            condition_id = bet.get("condition_id")
            result = await self.check_resolution(condition_id)
            results['checked'] += 1
            
            if result:
                status = "won" if result == "Yes" else "lost"
                bet["status"] = status
                bet["resolved_at"] = datetime.now().isoformat()
                
                stake = bet.get("stake", 2)
                if status == "won":
                    mult = bet.get("potential_multiplier") or (1 / bet.get("entry_price", 0.02))
                    bet["payout"] = stake * mult
                    bet["profit"] = bet["payout"] - stake
                    results['won'] += 1
                else:
                    bet["payout"] = 0
                    bet["profit"] = -stake
                    results['lost'] += 1
                
                resolved.append(bet)
                results['resolved'].append(bet)
                
                # Update database
                self.update_position_resolution(
                    bet.get('id'), status, 
                    bet.get('payout', 0), bet.get('profit', 0)
                )
                
                # Log
                emoji = '🎉' if status == 'won' else '❌'
                logger.info(f"{emoji} {status.upper()}: {bet.get('question', '')[:50]}")
                self.log_to_db("INFO", "resolution", f"Position {status}", {
                    "position_id": bet.get('id'),
                    "profit": bet.get('profit', 0)
                })
            
            await asyncio.sleep(0.1)
        
        # Save to JSON (backup)
        if results['resolved']:
            self.save_json(Config.BETS_FILE, bets)
            self.save_json(Config.RESOLVED_FILE, resolved)
            self._append_training_data(results['resolved'])
        
        return results
    
    def _append_training_data(self, resolved_bets: list):
        """Append resolved bets to training data."""
        # JSON storage
        training = self.load_json(Config.TRAINING_FILE)
        
        for bet in resolved_bets:
            training_entry = {
                'question': bet.get('question', ''),
                'entry_price': bet.get('entry_price', 0),
                'multiplier': bet.get('potential_multiplier', 50),
                'ml_score': bet.get('ml_score', 0.5),
                'outcome': 1 if bet.get('status') == 'won' else 0,
                'profit': bet.get('profit', 0),
                'resolved_at': bet.get('resolved_at'),
                'features': bet.get('ml_features', {})
            }
            training.append(training_entry)
            
            # Also save to database
            if DB_AVAILABLE:
                try:
                    db = get_session()
                    ml_data = MLTrainingData(
                        position_id=bet.get('id'),
                        features=training_entry['features'],
                        category=training_entry['features'].get('category'),
                        entry_price=training_entry['entry_price'],
                        multiplier=training_entry['multiplier'],
                        ml_score=training_entry['ml_score'],
                        outcome=training_entry['outcome'],
                        profit=training_entry['profit'],
                    )
                    db.add(ml_data)
                    db.commit()
                    db.close()
                except:
                    pass
        
        self.save_json(Config.TRAINING_FILE, training)
        logger.info(f"Added {len(resolved_bets)} samples to training data")
    
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
                                mult = round(1/price, 1)
                                question = m.get('question', '')
                                
                                opportunities.append({
                                    'condition_id': cid,
                                    'question': question,
                                    'price': price,
                                    'mult': mult,
                                    'token_id': t.get('token_id'),
                                    'ml_score': self.scorer.score(question, mult),
                                    'ml_features': self.scorer.extract_features({
                                        'question': question, 
                                        'price': price, 
                                        'mult': mult
                                    })
                                })
                            break
            except Exception as e:
                logger.error(f"Scan error: {e}")
        
        # Deduplicate and filter by ML score
        seen = set()
        filtered = []
        for o in opportunities:
            if o['condition_id'] not in seen and o['ml_score'] >= Config.MIN_ML_SCORE:
                seen.add(o['condition_id'])
                filtered.append(o)
        
        filtered.sort(key=lambda x: x['ml_score'], reverse=True)
        return filtered
    
    async def auto_place_bets(self, opportunities: list, max_bets: int = None) -> int:
        """Automatically place paper bets."""
        max_bets = max_bets or Config.MAX_NEW_BETS_PER_CYCLE
        to_place = opportunities[:max_bets]
        
        if not to_place:
            return 0
        
        bets = self.load_json(Config.BETS_FILE)
        placed = 0
        
        for opp in to_place:
            bet_id = f"TAIL-{int(datetime.now().timestamp())}-{len(bets)}"
            entry_price = opp['price']
            
            bet = {
                'id': bet_id,
                'timestamp': datetime.now().timestamp(),
                'question': opp['question'],
                'condition_id': opp['condition_id'],
                'token_id': opp.get('token_id'),
                'entry_price': entry_price,
                'stake': Config.STAKE,
                'size': round(Config.STAKE / entry_price, 2),
                'potential_multiplier': opp['mult'],
                'ml_score': opp['ml_score'],
                'ml_features': opp['ml_features'],
                'status': 'pending',
                'payout': 0,
                'profit': 0,
                'resolved_at': None
            }
            
            bets.append(bet)
            
            # Save to database
            self.save_position_to_db(bet)
            
            logger.info(f"📝 Bet: ${entry_price:.3f} ({opp['mult']:.0f}x) ML:{opp['ml_score']:.0%} - {opp['question'][:40]}...")
            placed += 1
        
        # Save to JSON
        self.save_json(Config.BETS_FILE, bets)
        
        return placed
    
    # -------------------------------------------------------------------------
    # STATISTICS
    # -------------------------------------------------------------------------
    
    def get_stats(self) -> dict:
        """Get portfolio statistics from both sources."""
        # Try database first
        if DB_AVAILABLE:
            try:
                return get_portfolio_stats()
            except:
                pass
        
        # Fallback to JSON
        bets = self.load_json(Config.BETS_FILE)
        resolved = self.load_json(Config.RESOLVED_FILE)
        
        total_bets = len(bets)
        pending = len([b for b in bets if b.get('status') == 'pending'])
        won = len([r for r in resolved if r.get('status') == 'won'])
        lost = len([r for r in resolved if r.get('status') == 'lost'])
        
        return {
            'total_positions': total_bets,
            'pending_positions': pending,
            'won_positions': won,
            'lost_positions': lost,
            'total_invested': sum(b.get('stake', 2) for b in bets),
            'total_profit': sum(r.get('profit', 0) for r in resolved),
            'hit_rate': (won / (won + lost) * 100) if (won + lost) > 0 else 0,
            'resolved_count': won + lost
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
        logger.info(f"   Database: {'✅ Connected' if DB_AVAILABLE else '❌ JSON Only'}")
        logger.info("=" * 60)
        
        self.log_to_db("INFO", "monitor", f"Starting cycle {self.stats['cycles']}")
        
        # 1. Check resolutions
        logger.info("📊 Checking resolutions...")
        res_results = await self.check_all_resolutions()
        logger.info(f"   Checked: {res_results['checked']}, Resolved: {len(res_results['resolved'])}")
        
        if res_results['resolved']:
            self.stats['resolutions_found'] += len(res_results['resolved'])
            logger.info(f"   🎉 Won: {res_results['won']}, ❌ Lost: {res_results['lost']}")
        
        # 2. Scan opportunities
        logger.info("🔍 Scanning opportunities...")
        opportunities = await self.scan_opportunities()
        logger.info(f"   Found: {len(opportunities)} tail markets (ML >= {Config.MIN_ML_SCORE:.0%})")
        
        # 3. Auto-place bets
        if auto_bet and opportunities:
            logger.info("💰 Auto-placing bets...")
            placed = await self.auto_place_bets(opportunities)
            self.stats['new_bets_placed'] += placed
            logger.info(f"   Placed: {placed} new bets")
        
        # 4. Portfolio stats
        stats = self.get_stats()
        logger.info("-" * 40)
        logger.info(f"📈 Portfolio: {stats['total_positions']} positions, ${stats['total_invested']:.0f} invested")
        logger.info(f"   Pending: {stats['pending_positions']}, Resolved: {stats['resolved_count']}")
        if stats['resolved_count'] > 0:
            logger.info(f"   Hit Rate: {stats['hit_rate']:.1f}%, P&L: ${stats['total_profit']:+.2f}")
        
        duration = (datetime.now() - cycle_start).total_seconds()
        logger.info(f"⏱️ Cycle completed in {duration:.1f}s")
        
        self.log_to_db("INFO", "monitor", f"Cycle {self.stats['cycles']} complete", {
            "duration_seconds": duration,
            "resolutions": len(res_results['resolved']),
            "new_bets": self.stats['new_bets_placed']
        })
    
    async def run_daemon(self, interval_minutes: int = 30, auto_bet: bool = True):
        """Run as daemon."""
        logger.info(f"🚀 Starting daemon (interval: {interval_minutes} min)")
        logger.info(f"   Session ID: {self.session_id}")
        logger.info("   Press Ctrl+C to stop\n")
        
        while True:
            try:
                await self.run_cycle(auto_bet=auto_bet)
                logger.info(f"\n⏰ Next cycle in {interval_minutes} minutes...\n")
                await asyncio.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("\n👋 Daemon stopped")
                break
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"❌ Cycle error: {e}")
                self.log_to_db("ERROR", "monitor", str(e))
                await asyncio.sleep(60)

# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Production Tail Betting Monitor")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run as daemon")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Interval (minutes)")
    parser.add_argument("--no-auto-bet", action="store_true", help="Disable auto-betting")
    
    args = parser.parse_args()
    
    async with ProductionMonitor() as monitor:
        if args.daemon:
            await monitor.run_daemon(
                interval_minutes=args.interval,
                auto_bet=not args.no_auto_bet
            )
        else:
            await monitor.run_cycle(auto_bet=not args.no_auto_bet)

if __name__ == "__main__":
    asyncio.run(main())
