"""
GROQ Client for Fast LLM Inference
Supports Kimi-K2, Llama 3.3, and other models.
"""

import os
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class GroqModel(Enum):
    """Available GROQ models"""
    # Kimi K2 - Best for reasoning
    KIMI_K2 = "moonshotai/kimi-k2-instruct"
    KIMI_K2_0905 = "moonshotai/kimi-k2-instruct-0905"
    
    # Llama models
    LLAMA_33_70B = "llama-3.3-70b-versatile"
    LLAMA_31_8B = "llama-3.1-8b-instant"
    LLAMA_4_MAVERICK = "meta-llama/llama-4-maverick-17b-128e-instruct"
    LLAMA_4_SCOUT = "meta-llama/llama-4-scout-17b-16e-instruct"
    
    # Qwen
    QWEN3_32B = "qwen/qwen3-32b"
    
    # Groq compound (multi-model)
    COMPOUND = "groq/compound"
    COMPOUND_MINI = "groq/compound-mini"


# Default model for trading decisions
DEFAULT_MODEL = GroqModel.LLAMA_33_70B  # Fast and capable


@dataclass
class GroqResponse:
    """Response from GROQ API"""
    success: bool
    content: str
    model: str
    latency_ms: float
    tokens_used: int
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        return self.success and len(self.content) > 0


class GroqClient:
    """
    GROQ API client for ultra-fast LLM inference.
    
    Features:
    - Multiple model support (Kimi, Llama, Qwen)
    - Automatic retry with backoff
    - Latency tracking
    - Rate limit handling
    """
    
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: GroqModel = DEFAULT_MODEL,
        max_retries: int = 3
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found")
        
        self.model = model
        self.max_retries = max_retries
        
        # Stats
        self.total_requests = 0
        self.total_tokens = 0
        self.total_latency_ms = 0
        
        logger.info(f"GroqClient initialized with model: {model.value}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 150,
        model: Optional[GroqModel] = None
    ) -> GroqResponse:
        """
        Generate completion from GROQ.
        
        Args:
            prompt: User prompt
            system_prompt: System instructions
            temperature: Randomness (0-1)
            max_tokens: Max response length
            model: Override default model
            
        Returns:
            GroqResponse with content and metadata
        """
        start_time = time.time()
        use_model = model or self.model
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": use_model.value,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        self.BASE_URL,
                        headers=headers,
                        json=payload
                    )
                
                latency_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 429:
                    # Rate limited
                    wait_time = 2 ** attempt
                    logger.warning(f"GROQ rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                if response.status_code != 200:
                    error_msg = response.text[:200]
                    logger.error(f"GROQ error {response.status_code}: {error_msg}")
                    return GroqResponse(
                        success=False,
                        content="",
                        model=use_model.value,
                        latency_ms=latency_ms,
                        tokens_used=0,
                        error=error_msg
                    )
                
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                tokens = data.get("usage", {}).get("total_tokens", 0)
                
                # Update stats
                self.total_requests += 1
                self.total_tokens += tokens
                self.total_latency_ms += latency_ms
                
                return GroqResponse(
                    success=True,
                    content=content,
                    model=use_model.value,
                    latency_ms=latency_ms,
                    tokens_used=tokens
                )
                
            except Exception as e:
                logger.error(f"GROQ request failed (attempt {attempt+1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        
        return GroqResponse(
            success=False,
            content="",
            model=use_model.value,
            latency_ms=(time.time() - start_time) * 1000,
            tokens_used=0,
            error="Max retries exceeded"
        )
    
    def quick_decision(
        self,
        market_data: Dict[str, Any],
        asset: str = "BTC"
    ) -> tuple[str, float, float]:
        """
        Get quick UP/DOWN decision for trading.
        
        Args:
            market_data: Dict with price, trend, etc.
            asset: BTC or ETH
            
        Returns:
            (direction, confidence, latency_ms)
        """
        prompt = f"""You are an expert crypto trader analyzing a 15-minute flash market.

ASSET: {asset}
MARKET DATA:
- Current Price: ${market_data.get('price', 0.50):.2f}
- Trend Score: {market_data.get('trend', 0):.2f} (positive=bullish, negative=bearish)
- Volatility: {market_data.get('volatility', 1.0):.2f}
- Momentum: {market_data.get('momentum', 0):.2f}
- Volume Ratio: {market_data.get('volume_ratio', 1.0):.2f}

TASK: Predict if {asset} will go UP or DOWN in the next 15 minutes.

Respond with EXACTLY this format:
DIRECTION: [UP or DOWN]
CONFIDENCE: [0.50 to 0.95]
REASON: [One sentence explanation]"""

        system = "You are a professional quantitative trader. Be decisive and confident."
        
        response = self.generate(prompt, system_prompt=system, temperature=0.2)
        
        if not response.success:
            return "UP", 0.50, response.latency_ms
        
        # Parse response
        content = response.content.upper()
        
        # Extract direction
        direction = "UP"
        if "DIRECTION: DOWN" in content or "DIRECTION:DOWN" in content:
            direction = "DOWN"
        elif "DIRECTION: UP" in content or "DIRECTION:UP" in content:
            direction = "UP"
        
        # Extract confidence
        confidence = 0.55
        import re
        conf_match = re.search(r'CONFIDENCE[:\s]+([0-9.]+)', content)
        if conf_match:
            try:
                confidence = float(conf_match.group(1))
                confidence = max(0.50, min(0.95, confidence))
            except:
                pass
        
        return direction, confidence, response.latency_ms
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        avg_latency = self.total_latency_ms / self.total_requests if self.total_requests > 0 else 0
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": avg_latency,
            "model": self.model.value
        }
    
    def health_check(self) -> bool:
        """Check if API is accessible"""
        response = self.generate("Say OK", max_tokens=5)
        return response.success


# Global instance
_groq_client: Optional[GroqClient] = None


def get_groq_client(model: GroqModel = DEFAULT_MODEL) -> GroqClient:
    """Get or create global GROQ client"""
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqClient(model=model)
    return _groq_client
