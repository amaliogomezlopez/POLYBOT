"""
AI Cache - TTL-based caching for AI decisions
Reduces API calls and provides consistent decisions within time windows.
"""

import time
import logging
from typing import Optional, Dict, Any, Generic, TypeVar
from dataclasses import dataclass, field
from threading import Lock
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CacheStrategy(Enum):
    """Cache eviction strategies"""
    TTL = "ttl"              # Time-to-live based
    LRU = "lru"              # Least recently used
    SLIDING = "sliding"      # Sliding window TTL


@dataclass
class CacheEntry(Generic[T]):
    """Single cache entry with metadata"""
    value: T
    created_at: float
    expires_at: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    @property
    def ttl_remaining(self) -> float:
        return max(0, self.expires_at - time.time())


class AICache:
    """
    Thread-safe TTL cache optimized for AI trading decisions.
    
    Features:
    - Configurable TTL per entry type
    - Thread-safe operations
    - Automatic cleanup of expired entries
    - Statistics tracking
    - Sliding window support
    """
    
    # Default TTLs for different decision types (seconds)
    DEFAULT_TTLS = {
        "bias": 300,           # 5 minutes for market bias
        "prediction": 60,      # 1 minute for predictions
        "market_data": 30,     # 30 seconds for market data
        "default": 120         # 2 minutes default
    }
    
    def __init__(
        self,
        default_ttl: float = 300,
        max_size: int = 1000,
        strategy: CacheStrategy = CacheStrategy.TTL,
        cleanup_interval: float = 60
    ):
        """
        Initialize cache.
        
        Args:
            default_ttl: Default time-to-live in seconds
            max_size: Maximum number of entries
            strategy: Cache eviction strategy
            cleanup_interval: How often to clean expired entries
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._strategy = strategy
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        
        # Stats
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        
        logger.info(f"AICache initialized: TTL={default_ttl}s, max_size={max_size}")
    
    def get(self, key: str, default: Any = None) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            default: Default value if not found
            
        Returns:
            Cached value or default
        """
        with self._lock:
            self._maybe_cleanup()
            
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                logger.debug(f"Cache MISS: {key}")
                return default
            
            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                self._evictions += 1
                logger.debug(f"Cache EXPIRED: {key}")
                return default
            
            # Update access stats
            entry.access_count += 1
            entry.last_accessed = time.time()
            
            # Sliding window - extend TTL on access
            if self._strategy == CacheStrategy.SLIDING:
                entry.expires_at = time.time() + self._default_ttl
            
            self._hits += 1
            logger.debug(f"Cache HIT: {key} (TTL: {entry.ttl_remaining:.0f}s)")
            return entry.value
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        category: Optional[str] = None
    ) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Custom TTL (uses default if not specified)
            category: Category for TTL lookup (e.g., "bias", "prediction")
        """
        with self._lock:
            self._maybe_cleanup()
            
            # Determine TTL
            if ttl is None:
                if category and category in self.DEFAULT_TTLS:
                    ttl = self.DEFAULT_TTLS[category]
                else:
                    ttl = self._default_ttl
            
            # Check size limit
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            
            now = time.time()
            self._cache[key] = CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + ttl,
                last_accessed=now
            )
            
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
    
    def delete(self, key: str) -> bool:
        """Delete entry from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> int:
        """Clear all entries, returns count of cleared entries"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache cleared: {count} entries removed")
            return count
    
    def get_or_set(
        self,
        key: str,
        factory: callable,
        ttl: Optional[float] = None,
        category: Optional[str] = None
    ) -> Any:
        """
        Get from cache or compute and cache value.
        
        Args:
            key: Cache key
            factory: Function to call if cache miss
            ttl: Custom TTL
            category: Category for TTL lookup
            
        Returns:
            Cached or newly computed value
        """
        value = self.get(key)
        if value is not None:
            return value
        
        # Compute value (outside lock to avoid blocking)
        value = factory()
        
        if value is not None:
            self.set(key, value, ttl=ttl, category=category)
        
        return value
    
    def _maybe_cleanup(self) -> None:
        """Cleanup expired entries if interval has passed"""
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup_expired()
            self._last_cleanup = now
    
    def _cleanup_expired(self) -> int:
        """Remove all expired entries"""
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired
        ]
        
        for key in expired_keys:
            del self._cache[key]
            self._evictions += 1
        
        if expired_keys:
            logger.debug(f"Cache cleanup: {len(expired_keys)} expired entries removed")
        
        return len(expired_keys)
    
    def _evict_oldest(self) -> None:
        """Evict oldest entry when cache is full"""
        if not self._cache:
            return
        
        # Find oldest entry
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at
        )
        
        del self._cache[oldest_key]
        self._evictions += 1
        logger.debug(f"Cache evicted oldest: {oldest_key}")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / max(total_requests, 1)
            
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "evictions": self._evictions,
                "strategy": self._strategy.value
            }
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def __contains__(self, key: str) -> bool:
        with self._lock:
            entry = self._cache.get(key)
            return entry is not None and not entry.is_expired


# Global cache instance
_global_cache: Optional[AICache] = None


def get_ai_cache() -> AICache:
    """Get or create the global AI cache"""
    global _global_cache
    if _global_cache is None:
        _global_cache = AICache(
            default_ttl=300,  # 5 minutes
            max_size=1000
        )
    return _global_cache
