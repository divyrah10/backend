import redis
import orjson
from typing import Optional, Any, Callable
from functools import wraps
from datetime import timedelta
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis caching layer for the application"""

    def __init__(self):
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=False,  # We handle encoding ourselves with orjson
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
        return self._client

    def is_available(self) -> bool:
        """Check if Redis is available"""
        try:
            self.client.ping()
            return True
        except (redis.ConnectionError, redis.TimeoutError):
            return False

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache"""
        try:
            data = self.client.get(key)
            if data:
                return orjson.loads(data)
            return None
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis get failed for key {key}: {e}")
            return None
        except orjson.JSONDecodeError as e:
            logger.warning(f"JSON decode failed for key {key}: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Set a value in cache"""
        try:
            ttl = ttl or settings.CACHE_DEFAULT_TTL
            data = orjson.dumps(value)
            self.client.setex(key, ttl, data)
            return True
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis set failed for key {key}: {e}")
            return False
        except (TypeError, orjson.JSONEncodeError) as e:
            logger.warning(f"JSON encode failed for key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from cache"""
        try:
            self.client.delete(key)
            return True
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis delete failed for key {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern"""
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
            return 0
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis delete_pattern failed for pattern {pattern}: {e}")
            return 0

    def flush_all(self) -> bool:
        """Flush all keys (use with caution!)"""
        try:
            self.client.flushdb()
            return True
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis flush failed: {e}")
            return False


# Global cache instance
cache = RedisCache()


# Cache key builders
class CacheKeys:
    """Cache key patterns for different entities"""

    # Products
    PRODUCT_BY_ID = "product:id:{product_id}"
    PRODUCT_BY_SLUG = "product:slug:{slug}"
    PRODUCTS_LIST = "products:list:{params_hash}"
    PRODUCTS_FEATURED = "products:featured:{limit}"

    # Categories
    CATEGORY_BY_ID = "category:id:{category_id}"
    CATEGORY_BY_SLUG = "category:slug:{slug}"
    CATEGORIES_LIST = "categories:list"
    CATEGORIES_TREE = "categories:tree"

    # Cart (per user/session)
    CART_USER = "cart:user:{user_id}"
    CART_SESSION = "cart:session:{session_id}"

    @staticmethod
    def product_id(product_id: str) -> str:
        return CacheKeys.PRODUCT_BY_ID.format(product_id=product_id)

    @staticmethod
    def product_slug(slug: str) -> str:
        return CacheKeys.PRODUCT_BY_SLUG.format(slug=slug)

    @staticmethod
    def products_list(params_hash: str) -> str:
        return CacheKeys.PRODUCTS_LIST.format(params_hash=params_hash)

    @staticmethod
    def products_featured(limit: int) -> str:
        return CacheKeys.PRODUCTS_FEATURED.format(limit=limit)

    @staticmethod
    def category_id(category_id: str) -> str:
        return CacheKeys.CATEGORY_BY_ID.format(category_id=category_id)

    @staticmethod
    def category_slug(slug: str) -> str:
        return CacheKeys.CATEGORY_BY_SLUG.format(slug=slug)


class CacheInvalidator:
    """Utility class to invalidate related cache entries"""

    @staticmethod
    def invalidate_product(product_id: str, slug: str = None):
        """Invalidate all cache entries for a product"""
        cache.delete(CacheKeys.product_id(product_id))
        if slug:
            cache.delete(CacheKeys.product_slug(slug))
        # Invalidate product lists and featured
        cache.delete_pattern("products:list:*")
        cache.delete_pattern("products:featured:*")

    @staticmethod
    def invalidate_all_products():
        """Invalidate all product-related cache"""
        cache.delete_pattern("product:*")
        cache.delete_pattern("products:*")

    @staticmethod
    def invalidate_category(category_id: str, slug: str = None):
        """Invalidate all cache entries for a category"""
        cache.delete(CacheKeys.category_id(category_id))
        if slug:
            cache.delete(CacheKeys.category_slug(slug))
        cache.delete(CacheKeys.CATEGORIES_LIST)
        cache.delete(CacheKeys.CATEGORIES_TREE)

    @staticmethod
    def invalidate_all_categories():
        """Invalidate all category-related cache"""
        cache.delete_pattern("category:*")
        cache.delete_pattern("categories:*")

    @staticmethod
    def invalidate_cart(user_id: str = None, session_id: str = None):
        """Invalidate cart cache"""
        if user_id:
            cache.delete(CacheKeys.CART_USER.format(user_id=user_id))
        if session_id:
            cache.delete(CacheKeys.CART_SESSION.format(session_id=session_id))


def hash_params(**kwargs) -> str:
    """Create a hash from parameters for cache key"""
    import hashlib
    # Sort and serialize params
    sorted_params = sorted(kwargs.items())
    param_str = str(sorted_params)
    return hashlib.md5(param_str.encode()).hexdigest()[:12]
