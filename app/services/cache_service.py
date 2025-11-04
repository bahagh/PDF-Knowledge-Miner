"""
Redis caching service for embeddings, search results, and frequently accessed data.
Provides high-performance caching with TTL management and serialization.
"""
import asyncio
import json
import logging
import pickle
from typing import Any, Optional, List, Dict, Union
import redis.asyncio as redis
import numpy as np
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheService:
    """High-performance Redis caching service"""
    
    def __init__(self):
        self.settings = get_settings().redis
        self.redis: Optional[redis.Redis] = None
        self._initialized = False
        
        # Cache key prefixes for different data types
        self.EMBEDDING_PREFIX = "emb:"
        self.SEARCH_PREFIX = "search:"
        self.DOCUMENT_PREFIX = "doc:"
        self.MODEL_PREFIX = "model:"
        self.STATS_PREFIX = "stats:"
        
        # Default TTL values (in seconds)
        self.DEFAULT_TTL = 3600  # 1 hour
        self.EMBEDDING_TTL = 86400  # 24 hours
        self.SEARCH_TTL = 1800  # 30 minutes
        self.DOCUMENT_TTL = 7200  # 2 hours
        self.STATS_TTL = 300  # 5 minutes
    
    async def initialize(self) -> None:
        """Initialize Redis connection"""
        if self._initialized:
            return
        
        try:
            self.redis = redis.from_url(
                self.settings.url,
                max_connections=self.settings.max_connections,
                encoding=self.settings.encoding,
                decode_responses=False,  # We'll handle encoding ourselves
                socket_timeout=self.settings.socket_timeout,
                socket_connect_timeout=self.settings.socket_connect_timeout,
                health_check_interval=self.settings.health_check_interval,
                retry_on_timeout=True,
            )
            
            # Test connection
            await self.redis.ping()
            
            self._initialized = True
            logger.info("Redis cache service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            raise
    
    async def close(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")
    
    async def health_check(self) -> bool:
        """Check Redis health"""
        try:
            if not self.redis:
                return False
            await self.redis.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    # Generic cache operations
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            if not self.redis:
                await self.initialize()
            
            value = await self.redis.get(key)
            if value is None:
                return None
            
            # Try to deserialize as pickle first, then JSON
            try:
                return pickle.loads(value)
            except:
                try:
                    return json.loads(value.decode('utf-8'))
                except:
                    return value.decode('utf-8')
                    
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        serialize_method: str = "pickle"
    ) -> bool:
        """Set value in cache with optional TTL"""
        try:
            if not self.redis:
                await self.initialize()
            
            # Serialize value
            if serialize_method == "pickle":
                serialized_value = pickle.dumps(value)
            elif serialize_method == "json":
                serialized_value = json.dumps(value).encode('utf-8')
            else:
                serialized_value = str(value).encode('utf-8')
            
            # Set with TTL
            ttl = ttl or self.DEFAULT_TTL
            await self.redis.setex(key, ttl, serialized_value)
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            if not self.redis:
                await self.initialize()
            
            result = await self.redis.delete(key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            if not self.redis:
                await self.initialize()
            
            return await self.redis.exists(key) > 0
            
        except Exception as e:
            logger.error(f"Cache exists check error for key {key}: {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        try:
            if not self.redis:
                await self.initialize()
            
            keys = await self.redis.keys(pattern)
            if keys:
                return await self.redis.delete(*keys)
            return 0
            
        except Exception as e:
            logger.error(f"Cache clear pattern error for {pattern}: {e}")
            return 0
    
    # Specialized cache operations for embeddings
    
    async def get_embedding(self, text_hash: str) -> Optional[np.ndarray]:
        """Get embedding vector from cache"""
        key = f"{self.EMBEDDING_PREFIX}{text_hash}"
        embedding_data = await self.get(key)
        
        if embedding_data:
            try:
                return np.array(embedding_data)
            except Exception as e:
                logger.error(f"Failed to deserialize embedding: {e}")
                await self.delete(key)
        
        return None
    
    async def set_embedding(self, text_hash: str, embedding: np.ndarray) -> bool:
        """Cache embedding vector"""
        key = f"{self.EMBEDDING_PREFIX}{text_hash}"
        return await self.set(
            key, 
            embedding.tolist(), 
            ttl=self.EMBEDDING_TTL,
            serialize_method="pickle"
        )
    
    async def get_embeddings_batch(self, text_hashes: List[str]) -> Dict[str, Optional[np.ndarray]]:
        """Get multiple embeddings in batch"""
        if not self.redis:
            await self.initialize()
        
        keys = [f"{self.EMBEDDING_PREFIX}{h}" for h in text_hashes]
        
        try:
            # Use pipeline for batch operations
            pipe = self.redis.pipeline()
            for key in keys:
                pipe.get(key)
            
            results = await pipe.execute()
            
            # Process results
            embeddings = {}
            for text_hash, result in zip(text_hashes, results):
                if result:
                    try:
                        embedding_data = pickle.loads(result)
                        embeddings[text_hash] = np.array(embedding_data)
                    except Exception as e:
                        logger.error(f"Failed to deserialize embedding for {text_hash}: {e}")
                        embeddings[text_hash] = None
                else:
                    embeddings[text_hash] = None
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Batch embedding get error: {e}")
            return {h: None for h in text_hashes}
    
    async def set_embeddings_batch(self, embeddings: Dict[str, np.ndarray]) -> bool:
        """Set multiple embeddings in batch"""
        if not self.redis:
            await self.initialize()
        
        try:
            pipe = self.redis.pipeline()
            
            for text_hash, embedding in embeddings.items():
                key = f"{self.EMBEDDING_PREFIX}{text_hash}"
                serialized = pickle.dumps(embedding.tolist())
                pipe.setex(key, self.EMBEDDING_TTL, serialized)
            
            await pipe.execute()
            return True
            
        except Exception as e:
            logger.error(f"Batch embedding set error: {e}")
            return False
    
    # Search result caching
    
    async def get_search_results(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached search results"""
        key = f"{self.SEARCH_PREFIX}{query_hash}"
        return await self.get(key)
    
    async def set_search_results(
        self, 
        query_hash: str, 
        results: Dict[str, Any]
    ) -> bool:
        """Cache search results"""
        key = f"{self.SEARCH_PREFIX}{query_hash}"
        return await self.set(key, results, ttl=self.SEARCH_TTL)
    
    # Document caching
    
    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get cached document metadata"""
        key = f"{self.DOCUMENT_PREFIX}{doc_id}"
        return await self.get(key)
    
    async def set_document(self, doc_id: str, document: Dict[str, Any]) -> bool:
        """Cache document metadata"""
        key = f"{self.DOCUMENT_PREFIX}{doc_id}"
        return await self.set(key, document, ttl=self.DOCUMENT_TTL)
    
    # Statistics caching
    
    async def get_stats(self, stats_type: str) -> Optional[Dict[str, Any]]:
        """Get cached statistics"""
        key = f"{self.STATS_PREFIX}{stats_type}"
        return await self.get(key)
    
    async def set_stats(self, stats_type: str, stats: Dict[str, Any]) -> bool:
        """Cache statistics"""
        key = f"{self.STATS_PREFIX}{stats_type}"
        return await self.set(key, stats, ttl=self.STATS_TTL)
    
    # Cache management
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """Get cache information and statistics"""
        try:
            if not self.redis:
                await self.initialize()
            
            info = await self.redis.info()
            
            # Get key counts by prefix
            key_counts = {}
            for prefix in [self.EMBEDDING_PREFIX, self.SEARCH_PREFIX, 
                          self.DOCUMENT_PREFIX, self.MODEL_PREFIX, self.STATS_PREFIX]:
                keys = await self.redis.keys(f"{prefix}*")
                key_counts[prefix.rstrip(':')] = len(keys)
            
            return {
                "memory_usage": info.get("used_memory_human"),
                "memory_peak": info.get("used_memory_peak_human"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "key_counts": key_counts,
                "uptime_seconds": info.get("uptime_in_seconds"),
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache info: {e}")
            return {"error": str(e)}
    
    async def clear_cache(self, cache_type: Optional[str] = None) -> int:
        """Clear cache by type or all"""
        if cache_type:
            prefix_map = {
                "embeddings": self.EMBEDDING_PREFIX,
                "search": self.SEARCH_PREFIX,
                "documents": self.DOCUMENT_PREFIX,
                "models": self.MODEL_PREFIX,
                "stats": self.STATS_PREFIX,
            }
            
            if cache_type in prefix_map:
                pattern = f"{prefix_map[cache_type]}*"
                return await self.clear_pattern(pattern)
            else:
                logger.warning(f"Unknown cache type: {cache_type}")
                return 0
        else:
            # Clear all cache
            if not self.redis:
                await self.initialize()
            
            await self.redis.flushdb()
            return 1


# Global cache instance
cache = CacheService()


async def get_cache() -> CacheService:
    """Get cache service instance"""
    if not cache._initialized:
        await cache.initialize()
    return cache


async def init_cache() -> None:
    """Initialize cache - called at application startup"""
    await cache.initialize()


async def close_cache() -> None:
    """Close cache connections - called at application shutdown"""
    await cache.close()