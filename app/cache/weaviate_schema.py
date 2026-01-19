from __future__ import annotations

import logging
from typing import Optional

import weaviate
from weaviate.classes.config import Configure, Property, DataType, VectorDistances

logger = logging.getLogger(__name__)

COLLECTION_NAME = "SemanticCache"


def create_schema(client: weaviate.WeaviateClient) -> None:
    """Create or verify Weaviate schema for semantic cache."""
    if client.collections.exists(COLLECTION_NAME):
        logger.info("Weaviate collection %s already exists", COLLECTION_NAME)
        return

    logger.info("Creating Weaviate collection %s", COLLECTION_NAME)
    
    client.collections.create(
        name=COLLECTION_NAME,
        vectorizer_config=None,  # We provide vectors directly
        properties=[
            Property(name="query_text", data_type=DataType.TEXT),
            Property(name="response", data_type=DataType.TEXT),
            Property(name="created_at", data_type=DataType.DATE),
            Property(name="ttl_seconds", data_type=DataType.INT),
            Property(name="cache_key", data_type=DataType.TEXT),  # Redis key reference
        ],
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
            ef_construction=128,
            max_connections=16,
        ),
    )
    logger.info("Successfully created Weaviate collection %s", COLLECTION_NAME)


def get_weaviate_client(url: str, api_key: Optional[str] = None) -> weaviate.WeaviateClient:
    """Create and return a Weaviate client."""
    auth_config = None
    if api_key:
        auth_config = weaviate.auth.AuthApiKey(api_key=api_key)
    
    # Parse URL to extract host and port
    # Remove protocol prefix
    url_clean = url.replace("http://", "").replace("https://", "").rstrip("/")
    
    # Extract host and port
    if ":" in url_clean:
        host, port_str = url_clean.split(":", 1)
        port = int(port_str)
    else:
        host = url_clean
        port = 8080
    
    # Connect to local Weaviate instance
    # For Docker, host will be "weaviate" (service name)
    client = weaviate.connect_to_local(
        host=host,
        port=port,
        auth_credentials=auth_config,
    )
    
    # Create schema if it doesn't exist
    create_schema(client)
    
    return client
