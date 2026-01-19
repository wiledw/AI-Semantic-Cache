from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.utils.connection_pool import get_redis_client, get_async_redis_client, get_weaviate_client, close_connections
from app.utils.structured_logging import setup_structured_logging, get_logger

# Setup structured logging
log_level = os.getenv("LOG_LEVEL", "INFO")
use_json_logging = os.getenv("USE_JSON_LOGGING", "true").lower() == "true"
setup_structured_logging(level=log_level, use_json=use_json_logging)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: initialize connections on startup, cleanup on shutdown."""
    # Startup: Initialize connection pools
    logger.info("Initializing connection pools...")
    try:
        get_redis_client()  # Initialize synchronous Redis connection pool (for backward compatibility)
        await get_async_redis_client()  # Initialize async Redis connection pool
        get_weaviate_client()  # Initialize Weaviate client if enabled
        logger.info("Connection pools initialized successfully")
    except Exception as exc:
        logger.error("Failed to initialize connection pools: %s", exc)
    
    yield
    
    # Shutdown: Close all connections
    logger.info("Closing connection pools...")
    await close_connections()
    logger.info("Connection pools closed")


app = FastAPI(title="Boardy Semantic Cache", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.websocket("/realtime")
async def realtime_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time communication."""
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info("Received WebSocket message: %s", data)
            # Echo back the message for now
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
