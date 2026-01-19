from __future__ import annotations

import logging
from typing import Optional

from redis import Redis, ConnectionPool
import weaviate

from app.utils.config import get_settings

logger = logging.getLogger(__name__)

# Module-level connection pools (singletons)
_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None
_weaviate_client: Optional[weaviate.WeaviateClient] = None
_settings = get_settings()


def get_redis_client() -> Redis:
    """Get or create a shared Redis client with connection pooling."""
    global _redis_client, _redis_pool
    
    if _redis_client is None:
        # Create connection pool for Redis
        _redis_pool = ConnectionPool.from_url(
            _settings.redis_url,
            decode_responses=True,
            max_connections=50,  # Maximum connections in pool
            retry_on_timeout=True,
        )
        _redis_client = Redis(connection_pool=_redis_pool)
        logger.info("Created Redis connection pool")
    
    return _redis_client


def get_weaviate_client() -> Optional[weaviate.WeaviateClient]:
    """Get or create a shared Weaviate client."""
    global _weaviate_client
    
    if not _settings.use_weaviate:
        return None
    
    if _weaviate_client is None:
        try:
            from app.cache.weaviate_schema import create_schema
            
            # Create Weaviate client connection
            auth_config = None
            if _settings.weaviate_api_key:
                auth_config = weaviate.auth.AuthApiKey(api_key=_settings.weaviate_api_key)
            
            # Parse URL to extract host and port
            url_clean = _settings.weaviate_url.replace("http://", "").replace("https://", "").rstrip("/")
            
            if ":" in url_clean:
                host, port_str = url_clean.split(":", 1)
                port = int(port_str)
            else:
                host = url_clean
                port = 8080
            
            # Connect to local Weaviate instance
            _weaviate_client = weaviate.connect_to_local(
                host=host,
                port=port,
                auth_credentials=auth_config,
            )
            
            # Create schema if it doesn't exist
            create_schema(_weaviate_client)
            
            logger.info("Created Weaviate client connection")
        except Exception as exc:
            logger.warning("Failed to create Weaviate client: %s", exc)
            return None
    
    return _weaviate_client


def close_connections() -> None:
    """Close all connections. Useful for cleanup/shutdown."""
    global _redis_client, _redis_pool, _weaviate_client
    
    if _redis_client:
        try:
            _redis_client.close()
            logger.info("Closed Redis client")
        except Exception as exc:
            logger.warning("Error closing Redis client: %s", exc)
        finally:
            _redis_client = None
    
    if _redis_pool:
        try:
            _redis_pool.disconnect()
            logger.info("Closed Redis connection pool")
        except Exception as exc:
            logger.warning("Error closing Redis pool: %s", exc)
        finally:
            _redis_pool = None
    
    if _weaviate_client:
        try:
            _weaviate_client.close()
            logger.info("Closed Weaviate client")
        except Exception as exc:
            logger.warning("Error closing Weaviate client: %s", exc)
        finally:
            _weaviate_client = None
