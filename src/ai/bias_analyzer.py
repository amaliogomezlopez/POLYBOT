"""
Bias Analyzer - AI-powered market direction prediction
Determines UP/DOWN bias for flash markets using Gemini.
"""

import os
import time
import logging
from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass
from enum import Enum

from .gemini_client import GeminiClient, get_gemini_client
from .cache import AICache, get_ai_cache

logger = logging.getLogger(__name__)


class MarketBias(Enum):
    """Market direction bias"""
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"
    ERROR = "ERROR"


@dataclass
class BiasDecision:
    """Complete bias decision with metadata"""
    bias: MarketBias
    confidence: float          # 0.0 to 1.0
    reasoning: str
    latency_ms: float
    from_cache: bool
    timestamp: float
    model: str
    raw_response: str
    
    @property
    def is_actionable(self) -> bool:
        """Whether this decision can be acted upon"""
        return self.bias in (MarketBias.UP, MarketBias.DOWN) and self.confidence >= 0.5


class BiasAnalyzer:
    """
    AI-powered market bias analyzer for flash trading.
    
    Features:
    - Cached decisions to reduce API calls
    - Multiple prompt strategies
    - Confidence scoring
    - BTC/ETH specific analysis
    """
    
    # Prompt templates optimized for trading decisions
    PROMPTS = {
        "simple": """You are a professional crypto trader. 
Based on the data, predict if BTC will go UP or DOWN in the next 15 minutes.
Respond with ONLY: UP or DOWN

Data: {data}""",

        "detailed": """You are a professional quantitative trader analyzing 15-minute BTC flash markets on Polymarket.

TASK: Predict the price direction for the NEXT 15 minutes.

MARKET DATA:
{data}

RULES:
1. Analyze the trend, volume, and momentum
2. Consider mean reversion vs trend continuation
3. Respond with EXACTLY one word: UP or DOWN
4. No explanations, no punctuation

YOUR PREDICTION:""",

        "contrarian": """You are a contrarian crypto trader who profits from market reversals.
When markets are extremely bullish, you expect pullbacks.
When markets are extremely bearish, you expect bounces.

Data: {data}

Based on mean reversion principles, will the next 15 minutes be UP or DOWN?
Answer with ONE word only:""",

        "momentum": """You are a momentum trader who follows trends.
Strong trends tend to continue in the short term.

Data: {data}

Following the current momentum, will the next 15 minutes be UP or DOWN?
Answer with ONE word only:"""
    }
    
    # Cache key prefix
    CACHE_PREFIX = "bias"
    CACHE_TTL = 300  # 5 minutes
    
    def __init__(
        self,
        client: Optional[GeminiClient] = None,
        cache: Optional[AICache] = None,
        prompt_strategy: str = "detailed"
    ):
        """
        Initialize bias analyzer.
        
        Args:
            client: Gemini client (uses default if not provided)
            cache: AI cache (uses default if not provided)
            prompt_strategy: Which prompt template to use
        """
        self._client = client or get_gemini_client()
        self._cache = cache or get_ai_cache()
        self._prompt_strategy = prompt_strategy
        
        # Stats
        self._total_analyses = 0
        self._cache_hits = 0
        self._errors = 0
        
        logger.info(f"BiasAnalyzer initialized with strategy: {prompt_strategy}")
    
    def analyze(
        self,
        market_data: Dict[str, Any],
        asset: str = "BTC",
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> BiasDecision:
        """
        Analyze market data and return bias decision.
        
        Args:
            market_data: Dict with price_change, volume, trend, etc.
            asset: Asset being analyzed (BTC, ETH)
            use_cache: Whether to use cached decisions
            force_refresh: Force new API call even if cached
            
        Returns:
            BiasDecision with direction and metadata
        """
        start_time = time.time()
        self._total_analyses += 1
        
        # Generate cache key from market data
        cache_key = self._generate_cache_key(market_data, asset)
        
        # Check cache first
        if use_cache and not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache_hits += 1
                logger.debug(f"Bias cache hit for {asset}")
                # Return cached decision with updated flag
                return BiasDecision(
                    bias=cached["bias"],
                    confidence=cached["confidence"],
                    reasoning=cached["reasoning"],
                    latency_ms=0,
                    from_cache=True,
                    timestamp=cached["timestamp"],
                    model=cached["model"],
                    raw_response=cached["raw_response"]
                )
        
        # Generate prompt
        prompt = self._build_prompt(market_data, asset)
        
        # Call Gemini
        response = self._client.generate(prompt)
        
        latency_ms = (time.time() - start_time) * 1000
        
        if not response.success:
            self._errors += 1
            return BiasDecision(
                bias=MarketBias.ERROR,
                confidence=0.0,
                reasoning=f"API Error: {response.error}",
                latency_ms=latency_ms,
                from_cache=False,
                timestamp=time.time(),
                model=response.model,
                raw_response=""
            )
        
        # Parse response
        bias, confidence = self._parse_response(response.content, market_data)
        
        decision = BiasDecision(
            bias=bias,
            confidence=confidence,
            reasoning=self._generate_reasoning(bias, market_data),
            latency_ms=latency_ms,
            from_cache=False,
            timestamp=time.time(),
            model=response.model,
            raw_response=response.content
        )
        
        # Cache the decision
        if use_cache and bias != MarketBias.ERROR:
            self._cache.set(
                cache_key,
                {
                    "bias": bias,
                    "confidence": confidence,
                    "reasoning": decision.reasoning,
                    "timestamp": decision.timestamp,
                    "model": decision.model,
                    "raw_response": decision.raw_response
                },
                ttl=self.CACHE_TTL,
                category="bias"
            )
        
        logger.info(f"Bias analysis for {asset}: {bias.value} (conf: {confidence:.2f}, latency: {latency_ms:.0f}ms)")
        
        return decision
    
    def get_quick_bias(
        self,
        price_change_pct: float,
        volume: str = "normal",
        trend: str = "neutral"
    ) -> MarketBias:
        """
        Quick helper for getting bias from simple inputs.
        
        Args:
            price_change_pct: Price change percentage (e.g., 1.5 for +1.5%)
            volume: "low", "normal", "high", "extreme"
            trend: "bearish", "neutral", "bullish"
            
        Returns:
            MarketBias enum value
        """
        market_data = {
            "price_change": f"{'+' if price_change_pct >= 0 else ''}{price_change_pct:.1f}%",
            "volume": volume,
            "trend": trend
        }
        
        decision = self.analyze(market_data)
        return decision.bias
    
    def _build_prompt(self, market_data: Dict[str, Any], asset: str) -> str:
        """Build prompt from template and market data"""
        template = self.PROMPTS.get(self._prompt_strategy, self.PROMPTS["detailed"])
        
        # Format market data as string
        data_str = "\n".join([
            f"- {key}: {value}" 
            for key, value in market_data.items()
        ])
        
        return template.format(data=data_str, asset=asset)
    
    def _parse_response(
        self,
        response: str,
        market_data: Dict[str, Any]
    ) -> tuple[MarketBias, float]:
        """
        Parse Gemini response into bias and confidence.
        
        Returns:
            Tuple of (MarketBias, confidence score)
        """
        response_upper = response.upper().strip()
        
        # Check for clear UP/DOWN
        if "UP" in response_upper and "DOWN" not in response_upper:
            bias = MarketBias.UP
            confidence = 0.8
        elif "DOWN" in response_upper and "UP" not in response_upper:
            bias = MarketBias.DOWN
            confidence = 0.8
        elif "UP" in response_upper and "DOWN" in response_upper:
            # Ambiguous - default to NEUTRAL
            bias = MarketBias.NEUTRAL
            confidence = 0.3
        else:
            # Couldn't parse
            bias = MarketBias.NEUTRAL
            confidence = 0.2
        
        # Adjust confidence based on market data clarity
        price_change = market_data.get("price_change", "0%")
        try:
            pct = float(price_change.replace("%", "").replace("+", ""))
            # Higher price change = higher confidence
            if abs(pct) > 2:
                confidence = min(confidence + 0.1, 1.0)
            elif abs(pct) < 0.5:
                confidence = max(confidence - 0.1, 0.1)
        except (ValueError, AttributeError):
            pass
        
        return bias, confidence
    
    def _generate_reasoning(
        self,
        bias: MarketBias,
        market_data: Dict[str, Any]
    ) -> str:
        """Generate human-readable reasoning for the decision"""
        price_change = market_data.get("price_change", "0%")
        volume = market_data.get("volume", "normal")
        trend = market_data.get("trend", "neutral")
        
        if bias == MarketBias.UP:
            return f"Bullish signal: {price_change} change, {volume} volume, {trend} trend"
        elif bias == MarketBias.DOWN:
            return f"Bearish signal: {price_change} change, {volume} volume, {trend} trend"
        else:
            return f"Uncertain: {price_change} change, {volume} volume, {trend} trend"
    
    def _generate_cache_key(self, market_data: Dict[str, Any], asset: str) -> str:
        """Generate unique cache key for market data"""
        # Simplify to key metrics that determine bias
        price_change = market_data.get("price_change", "0%")
        volume = market_data.get("volume", "normal")
        trend = market_data.get("trend", "neutral")
        
        # Bucket price changes to improve cache hits
        try:
            pct = float(price_change.replace("%", "").replace("+", ""))
            if pct > 2:
                price_bucket = "strong_up"
            elif pct > 0.5:
                price_bucket = "up"
            elif pct > -0.5:
                price_bucket = "flat"
            elif pct > -2:
                price_bucket = "down"
            else:
                price_bucket = "strong_down"
        except (ValueError, AttributeError):
            price_bucket = "unknown"
        
        return f"{self.CACHE_PREFIX}:{asset}:{price_bucket}:{volume}:{trend}"
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get analyzer statistics"""
        return {
            "total_analyses": self._total_analyses,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": self._cache_hits / max(self._total_analyses, 1),
            "errors": self._errors,
            "prompt_strategy": self._prompt_strategy,
            "gemini_stats": self._client.stats,
            "cache_stats": self._cache.stats
        }


# Convenience function
def get_market_bias(
    price_change_pct: float,
    volume: str = "normal",
    trend: str = "neutral",
    asset: str = "BTC"
) -> str:
    """
    Simple function to get market bias.
    
    Args:
        price_change_pct: Price change in percent (e.g., 1.5)
        volume: "low", "normal", "high"
        trend: "bearish", "neutral", "bullish"
        asset: "BTC" or "ETH"
        
    Returns:
        "UP", "DOWN", "NEUTRAL", or "ERROR"
    """
    analyzer = BiasAnalyzer()
    bias = analyzer.get_quick_bias(price_change_pct, volume, trend)
    return bias.value
