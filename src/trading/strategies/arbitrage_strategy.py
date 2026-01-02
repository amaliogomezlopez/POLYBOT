"""
🔀 STRATEGY A: CROSS-EXCHANGE ARBITRAGE
========================================
Polymarket vs PredictBase arbitrage detection.

Logic:
- Find matching markets across exchanges using fuzzy matching
- Calculate synthetic arbitrage: Cost(Poly_YES) + Cost(PB_NO) < 0.975
- Minimum 2.5% ROI threshold (covers bridging fees)
- If profitable, generate BUY signal

Features:
- Batch fuzzy matching for efficiency (ARBScanner)
- Ambiguity detection (opposite indicators like "NOT")
- Two arbitrage types: DIRECT and SYNTHETIC
- Circuit breaker for fault tolerance

Strategy ID: ARB_PREDICTBASE_V1
Scan Interval: 60 seconds (non-blocking asyncio.create_task)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List
from collections import defaultdict

from .base_strategy import BaseStrategy, MarketData, TradeSignal, SignalType

logger = logging.getLogger(__name__)

# Try to import fuzzy matching
try:
    from thefuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logger.warning("thefuzz not installed - using basic matching")

# Try to import PredictBase client
try:
    from src.exchanges.predictbase_client import PredictBaseClient
    PB_AVAILABLE = True
except ImportError:
    PB_AVAILABLE = False
    logger.warning("PredictBase client not available")

# Try to import ARB Scanner (new efficient batch scanner)
try:
    from src.scanner.arb_scanner import ARBScanner, ArbSignal
    ARB_SCANNER_AVAILABLE = True
except ImportError:
    ARB_SCANNER_AVAILABLE = False
    logger.warning("ARBScanner not available - using legacy per-market lookup")


class ArbitrageStrategy(BaseStrategy):
    """
    Cross-exchange arbitrage between Polymarket and PredictBase.
    
    NEW: Uses ARBScanner for batch processing (much more efficient).
    
    Looks for SYNTHETIC arbitrage where:
    - Poly YES + PB NO < 0.975 (2.5% profit margin to cover bridging)
    - Or Poly NO + PB YES < 0.975
    
    Parameters:
        min_spread_pct: Minimum ROI to trigger (default: 2.5%)
        max_spread_pct: Maximum ROI (avoid suspicious spreads)
        fuzzy_threshold: Minimum fuzzy match score (0-100)
        min_liquidity: Minimum volume for trade
        scan_interval: Seconds between ARB scans (default: 60)
    """
    
    STRATEGY_ID = "ARB_PREDICTBASE_V1"
    
    def __init__(
        self,
        paper_mode: bool = True,
        stake_size: float = 50.0,  # Higher stake for arb
        min_spread_pct: float = 2.5,  # Lower threshold (bridging costs)
        max_spread_pct: float = 25.0,
        fuzzy_threshold: int = 85,
        min_liquidity: float = 1000,
        scan_interval: int = 60,
        **kwargs
    ):
        super().__init__(
            strategy_id=self.STRATEGY_ID,
            paper_mode=paper_mode,
            stake_size=stake_size,
            max_daily_trades=50,  # More trades for arb
            **kwargs
        )
        
        self.min_spread_pct = min_spread_pct
        self.max_spread_pct = max_spread_pct
        self.fuzzy_threshold = fuzzy_threshold
        self.min_liquidity = min_liquidity
        self.scan_interval = scan_interval
        
        # ARB Scanner (new efficient batch scanner)
        self._arb_scanner: Optional[ARBScanner] = None if not ARB_SCANNER_AVAILABLE else None
        self._scanner_initialized = False
        
        # Legacy: PredictBase client (fallback)
        self._pb_client: Optional[PredictBaseClient] = None
        self._pb_initialized = False
        
        # Cache for matched markets
        self._matched_pairs: Dict[str, dict] = {}  # question_hash -> pb_data
        self._match_cache_ttl = 600  # 10 minutes
        
        # Track pending signals from batch scan
        self._pending_signals: List = []
        self._last_batch_scan: Optional[datetime] = None
    
    def get_config(self) -> Dict:
        return {
            "strategy_id": self.STRATEGY_ID,
            "type": "ARBITRAGE",
            "min_spread_pct": self.min_spread_pct,
            "max_spread_pct": self.max_spread_pct,
            "fuzzy_threshold": self.fuzzy_threshold,
            "min_liquidity": self.min_liquidity,
            "stake_size": self.stake_size,
            "paper_mode": self.paper_mode,
            "scan_interval": self.scan_interval,
            "pb_available": PB_AVAILABLE,
            "arb_scanner_available": ARB_SCANNER_AVAILABLE,
        }
    
    async def _ensure_arb_scanner(self):
        """Initialize ARB Scanner lazily."""
        if not ARB_SCANNER_AVAILABLE:
            return await self._ensure_pb_client()  # Fallback
        
        if not self._scanner_initialized:
            try:
                self._arb_scanner = ARBScanner(
                    min_roi_pct=self.min_spread_pct,
                    max_roi_pct=self.max_spread_pct,
                    fuzzy_threshold=self.fuzzy_threshold,
                    stake_size=self.stake_size,
                    paper_mode=self.paper_mode,
                )
                await self._arb_scanner.__aenter__()
                self._scanner_initialized = True
                logger.info("✅ ARBScanner initialized")
            except Exception as e:
                logger.warning(f"⚠️ Failed to init ARBScanner: {e}")
                self._scanner_initialized = True  # Don't retry
                return await self._ensure_pb_client()  # Fallback
    
    async def run_batch_scan(self, poly_markets: List[Dict]) -> List[TradeSignal]:
        """
        Run batch ARB scan across all markets.
        
        This is MORE EFFICIENT than per-market lookup because:
        - Single API call to PredictBase
        - Batch fuzzy matching
        - Parallelized arbitrage detection
        
        Args:
            poly_markets: List of Polymarket market dicts
            
        Returns:
            List of TradeSignal objects
        """
        await self._ensure_arb_scanner()
        
        if not self._arb_scanner:
            logger.warning("ARBScanner not available, skipping batch scan")
            return []
        
        signals: List[TradeSignal] = []
        
        try:
            # Run batch scan
            arb_signals = await self._arb_scanner.scan(poly_markets)
            
            # Convert ARBSignals to TradeSignals
            for arb_sig in arb_signals:
                trade_signal = self._convert_arb_signal(arb_sig)
                if trade_signal:
                    signals.append(trade_signal)
            
            self._last_batch_scan = datetime.utcnow()
            logger.info(f"🔀 ARB batch scan complete: {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"❌ ARB batch scan error: {e}")
        
        return signals
    
    def _convert_arb_signal(self, arb_sig) -> Optional[TradeSignal]:
        """Convert ARBSignal to TradeSignal for unified recording."""
        try:
            return TradeSignal(
                strategy_id=self.strategy_id,
                signal_type=SignalType.BUY,
                condition_id=arb_sig.poly_condition_id,
                token_id=arb_sig.poly_token_id,
                question=arb_sig.question,
                outcome=arb_sig.poly_side,
                entry_price=arb_sig.poly_price,
                stake=arb_sig.poly_stake * arb_sig.poly_price,  # USD value
                confidence=arb_sig.confidence,
                expected_value=arb_sig.gross_profit,
                trigger_reason=f"arb_{arb_sig.arb_type.lower()}_{arb_sig.roi_pct:.1f}pct",
                signal_data={
                    "arb_type": arb_sig.arb_type,
                    "poly_side": arb_sig.poly_side,
                    "poly_price": arb_sig.poly_price,
                    "pb_side": arb_sig.pb_side,
                    "pb_price": arb_sig.pb_price,
                    "pb_market_id": arb_sig.pb_market_id,
                    "total_cost": arb_sig.total_cost,
                    "gross_profit": arb_sig.gross_profit,
                    "roi_pct": arb_sig.roi_pct,
                    "match_score": arb_sig.match_score,
                    "hedge_exchange": "predictbase",
                },
                snapshot_data={},
            )
        except Exception as e:
            logger.error(f"Failed to convert ARB signal: {e}")
            return None
    
    async def _ensure_pb_client(self):
        """Initialize PredictBase client lazily (legacy fallback)."""
        if not PB_AVAILABLE:
            return
        
        if not self._pb_initialized:
            try:
                self._pb_client = PredictBaseClient()
                await self._pb_client.__aenter__()
                self._pb_initialized = True
                logger.info("✅ PredictBase client initialized")
            except Exception as e:
                logger.warning(f"⚠️ Failed to init PredictBase: {e}")
                self._pb_initialized = True  # Don't retry
    
    async def _get_pb_prices(self, question: str) -> Optional[Dict]:
        """Get PredictBase prices with caching."""
        # Check cache first
        cache_key = question[:100]
        if cache_key in self._matched_pairs:
            return self._matched_pairs[cache_key]
        
        await self._ensure_pb_client()
        
        if not self._pb_client:
            return None
        
        try:
            pb_market = await asyncio.wait_for(
                self._pb_client.get_market_by_question(question, threshold=self.fuzzy_threshold),
                timeout=5.0  # 5 second timeout
            )
            
            if pb_market:
                result = {
                    "yes": pb_market.yes_price,
                    "no": pb_market.no_price,
                    "market_id": pb_market.market_id,
                }
                self._matched_pairs[cache_key] = result
                return result
        except asyncio.TimeoutError:
            logger.debug(f"PB timeout for: {question[:40]}")
        except Exception as e:
            logger.debug(f"PB lookup error: {e}")
        
        # Cache negative result too
        self._matched_pairs[cache_key] = None
        return None
    
    async def process_market(self, market: MarketData) -> Optional[TradeSignal]:
        """
        Check for arbitrage opportunity.
        
        Steps:
        1. Pre-filter: skip markets unlikely to have arb
        2. Lazy lookup PredictBase prices
        3. Calculate synthetic spread
        4. If profitable, generate signal
        """
        # Pre-filter: only check markets with reasonable Poly prices
        # (Very high or very low prices unlikely to have arb)
        if market.yes_price < 0.05 or market.yes_price > 0.95:
            return None
        
        # Pre-filter: need minimum liquidity
        if market.volume_24h and market.volume_24h < self.min_liquidity:
            return None
        
        # Check competitor_prices if already populated (from cache)
        pb_data = market.competitor_prices.get("predictbase", {})
        
        # If not populated, do lazy lookup (but only 1 in 10 markets to save API calls)
        if not pb_data:
            # Only lookup for "interesting" markets (mid-range prices)
            if 0.20 <= market.yes_price <= 0.80:
                pb_data = await self._get_pb_prices(market.question) or {}
        
        if not pb_data:
            return None
        
        pb_yes = pb_data.get("yes", 0)
        pb_no = pb_data.get("no", 0)
        
        if pb_yes == 0 and pb_no == 0:
            return None
        
        # Calculate arbitrage opportunities
        poly_yes = market.yes_price
        poly_no = market.no_price or (1 - poly_yes)
        
        # Strategy 1: Buy Poly YES + Buy PB NO
        cost_1 = poly_yes + pb_no
        profit_1 = 1 - cost_1  # Guaranteed $1 payout
        spread_1_pct = profit_1 * 100
        
        # Strategy 2: Buy Poly NO + Buy PB YES
        cost_2 = poly_no + pb_yes
        profit_2 = 1 - cost_2
        spread_2_pct = profit_2 * 100
        
        # Check if either strategy is profitable
        best_spread = max(spread_1_pct, spread_2_pct)
        
        if best_spread < self.min_spread_pct:
            # ⚠️ NEAR MISS: Spread close to threshold (50%+)
            near_miss_spread = self.min_spread_pct * 0.5
            if best_spread >= near_miss_spread:
                logger.info(
                    f"⚠️ NEAR_MISS [ARB]: {best_spread:.1f}% spread (need {self.min_spread_pct:.1f}%) | "
                    f"Poly: ${poly_yes:.3f}/{poly_no:.3f} | PB: ${pb_yes:.3f}/{pb_no:.3f} | "
                    f"{market.question[:40]}..."
                )
            return None
        
        if best_spread > self.max_spread_pct:
            # Suspicious - might be stale data or error
            logger.warning(f"Suspicious spread {best_spread:.1f}% on {market.question[:40]}")
            return None
        
        # Determine which side to trade
        if spread_1_pct >= spread_2_pct:
            outcome = "YES"
            entry_price = poly_yes
            pb_price = pb_no
            spread_pct = spread_1_pct
        else:
            outcome = "NO"
            entry_price = poly_no
            pb_price = pb_yes
            spread_pct = spread_2_pct
        
        # Calculate expected value
        ev = (1 - entry_price - pb_price) * self.stake_size
        
        signal = TradeSignal(
            strategy_id=self.strategy_id,
            signal_type=SignalType.BUY,
            condition_id=market.condition_id,
            token_id=market.token_id,
            question=market.question,
            outcome=outcome,
            entry_price=entry_price,
            stake=self.stake_size,
            confidence=min(0.95, spread_pct / 10),  # Higher spread = higher confidence
            expected_value=ev,
            trigger_reason=f"arb_spread_{spread_pct:.1f}pct",
            signal_data={
                "poly_yes": poly_yes,
                "poly_no": poly_no,
                "pb_yes": pb_yes,
                "pb_no": pb_no,
                "cost": entry_price + pb_price,
                "spread_pct": spread_pct,
                "expected_profit": ev,
                "hedge_exchange": "predictbase",
                "hedge_side": "NO" if outcome == "YES" else "YES",
                "hedge_price": pb_price,
            },
            snapshot_data=market.to_snapshot()
        )
        
        logger.info(f"🔀 ARB: {spread_pct:.1f}% spread | Poly {outcome}@{entry_price:.3f} + PB@{pb_price:.3f}")
        
        return signal
    
    def match_markets(self, poly_question: str, pb_question: str) -> float:
        """
        Calculate match score between Polymarket and PredictBase questions.
        
        Returns:
            Score 0-100 (higher = better match)
        """
        if FUZZY_AVAILABLE:
            # Use token sort ratio for better matching with reordered words
            score = fuzz.token_sort_ratio(
                poly_question.lower(),
                pb_question.lower()
            )
        else:
            # Basic word overlap matching
            poly_words = set(poly_question.lower().split())
            pb_words = set(pb_question.lower().split())
            
            # Remove common stop words
            stop_words = {'will', 'the', 'be', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'by'}
            poly_words -= stop_words
            pb_words -= stop_words
            
            if not poly_words:
                return 0
            
            overlap = len(poly_words & pb_words)
            score = (overlap / len(poly_words)) * 100
        
        return score


class ArbitrageDetector:
    """
    Utility class to detect arbitrage opportunities across exchanges.
    Used by the orchestrator to enrich market data.
    """
    
    def __init__(self, pb_client=None):
        self.pb_client = pb_client
        self._cache: Dict[str, dict] = {}
        self._last_fetch = None
        self._fetch_interval = 300  # seconds
    
    async def get_competitor_prices(self, poly_question: str) -> Dict[str, Dict[str, float]]:
        """
        Get competitor prices for a Polymarket question.
        
        Returns:
            {"predictbase": {"yes": 0.03, "no": 0.95}}
        """
        if not self.pb_client:
            return {}
        
        try:
            pb_market = await self.pb_client.get_market_by_question(
                poly_question,
                threshold=0.85
            )
            
            if pb_market:
                return {
                    "predictbase": {
                        "yes": pb_market.yes_price,
                        "no": pb_market.no_price,
                        "market_id": pb_market.market_id,
                        "url": pb_market.url
                    }
                }
        except Exception as e:
            logger.debug(f"Failed to get competitor prices: {e}")
        
        return {}
