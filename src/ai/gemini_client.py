"""
Gemini Client - Optimized for low-latency trading decisions
Uses gemini-2.5-flash for best balance of speed and accuracy.
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

logger = logging.getLogger(__name__)


class GeminiModel(Enum):
    """Available Gemini models for trading"""
    FLASH_25 = "gemini-2.5-flash"          # Best balance (recommended)
    FLASH_20 = "gemini-2.0-flash"          # Faster, slightly less stable
    FLASH_LITE = "gemini-2.0-flash-lite"   # Fastest, less accurate
    PRO_25 = "gemini-2.5-pro"              # Most accurate, slower
    FLASH_LITE_25 = "gemini-2.5-flash-lite" # Fastest 2.5 version


# Default model to use
DEFAULT_MODEL = GeminiModel.FLASH_25


@dataclass
class GeminiResponse:
    """Structured response from Gemini API"""
    content: str
    latency_ms: float
    model: str
    tokens_used: int
    success: bool
    error: Optional[str] = None


class GeminiClient:
    """
    Optimized Gemini client for trading decisions.
    
    Features:
    - Connection pooling (reuse model instance)
    - Automatic retry with exponential backoff
    - Timeout handling
    - Response validation
    - Latency tracking
    """
    
    # Default configuration optimized for trading
    DEFAULT_CONFIG = {
        "max_output_tokens": 10,      # Minimal tokens for UP/DOWN
        "temperature": 0,              # Deterministic responses
        "top_p": 1,
        "top_k": 1,
    }
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 0.5  # seconds
    REQUEST_TIMEOUT = 10    # seconds
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: GeminiModel = GeminiModel.FLASH_25,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize Gemini client.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Which Gemini model to use
            config: Optional custom generation config
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        # Configure API
        genai.configure(api_key=self.api_key)
        
        # Store model name
        self.model_name = model.value
        
        # Create model instance (reused for all requests)
        self._model = genai.GenerativeModel(self.model_name)
        
        # Generation config
        config_dict = {**self.DEFAULT_CONFIG, **(config or {})}
        self._generation_config = GenerationConfig(**config_dict)
        
        # Stats tracking
        self._total_requests = 0
        self._total_latency = 0
        self._errors = 0
        
        logger.info(f"GeminiClient initialized with model: {self.model_name}")
    
    def generate(
        self,
        prompt: str,
        max_retries: Optional[int] = None,
        timeout: Optional[float] = None
    ) -> GeminiResponse:
        """
        Generate response from Gemini with retry logic.
        
        Args:
            prompt: The prompt to send
            max_retries: Override default max retries
            timeout: Override default timeout (not directly supported, for future use)
        
        Returns:
            GeminiResponse with content and metadata
        """
        retries = max_retries or self.MAX_RETRIES
        last_error = None
        
        for attempt in range(retries):
            try:
                start_time = time.time()
                
                response = self._model.generate_content(
                    prompt,
                    generation_config=self._generation_config
                )
                
                latency_ms = (time.time() - start_time) * 1000
                
                # Extract content
                content = response.text.strip() if response.text else ""
                
                # Estimate tokens (rough approximation)
                tokens_used = len(prompt.split()) + len(content.split())
                
                # Update stats
                self._total_requests += 1
                self._total_latency += latency_ms
                
                logger.debug(f"Gemini response in {latency_ms:.0f}ms: {content}")
                
                return GeminiResponse(
                    content=content,
                    latency_ms=latency_ms,
                    model=self.model_name,
                    tokens_used=tokens_used,
                    success=True
                )
                
            except Exception as e:
                last_error = str(e)
                self._errors += 1
                error_str = str(e).lower()
                
                # Check if retryable
                if "429" in str(e) or "rate" in error_str:
                    # Rate limit - wait longer
                    wait_time = self.RETRY_DELAY_BASE * (2 ** attempt) * 2
                    logger.warning(f"Rate limit hit, waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                elif "500" in str(e) or "503" in str(e):
                    # Server error - retry with backoff
                    wait_time = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(f"Server error, retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                elif "finish_reason" in error_str or "valid `part`" in error_str:
                    # Model returned empty/blocked response - retry with simpler prompt
                    wait_time = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning(f"Empty response, retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                elif "403" in str(e) or "ip" in error_str:
                    # IP restriction - don't retry
                    logger.error(f"IP restriction error: {e}")
                    break
                else:
                    # Non-retryable error
                    logger.error(f"Gemini error (non-retryable): {e}")
                    break
        
        # All retries failed
        logger.error(f"Gemini failed after {retries} attempts: {last_error}")
        return GeminiResponse(
            content="",
            latency_ms=0,
            model=self.model_name,
            tokens_used=0,
            success=False,
            error=last_error
        )
    
    def quick_decision(self, prompt: str) -> Optional[str]:
        """
        Quick helper for simple UP/DOWN decisions.
        Returns just the content string or None on error.
        """
        response = self.generate(prompt)
        return response.content if response.success else None
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        avg_latency = (self._total_latency / self._total_requests 
                      if self._total_requests > 0 else 0)
        return {
            "total_requests": self._total_requests,
            "total_errors": self._errors,
            "avg_latency_ms": avg_latency,
            "error_rate": self._errors / max(self._total_requests, 1),
            "model": self.model_name
        }
    
    def health_check(self) -> bool:
        """Quick health check - sends minimal request"""
        try:
            response = self.generate("Say OK", max_retries=1)
            return response.success
        except Exception:
            return False


# Singleton instance for global use
_default_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Get or create the default Gemini client"""
    global _default_client
    if _default_client is None:
        _default_client = GeminiClient()
    return _default_client
