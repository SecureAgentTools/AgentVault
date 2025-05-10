"""
Server-Sent Events (SSE) implementation for dashboard events.
This is an alternative to WebSockets for clients that have issues with WebSocket connections.
"""

import asyncio
import logging
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import redis
import os

# Configure logging
logger = logging.getLogger("sse-endpoint")

# Set a more detailed log format for debugging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Create router with explicit prefix
router = APIRouter(prefix="", tags=["sse"])

# Print statement to confirm module is loaded
print("SSE endpoint module loaded successfully")
logger.info("SSE endpoint module initialized")

# Redis connection
REDIS_URL = os.environ.get("REDIS_URL", "redis://secops-redis:6379")
logging.info(f"SSE endpoint using Redis URL: {REDIS_URL}")

# Helper function to connect to Redis
def get_redis_client():
    try:
        return redis.Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None

# SSE implementation
async def event_generator(request: Request):
    """Generate SSE events from Redis Pub/Sub."""
    redis_client = get_redis_client()
    if not redis_client:
        yield f"data: {json.dumps({'error': 'Redis connection failed'})}\n\n"
        return

    pubsub = redis_client.pubsub()
    try:
        pubsub.subscribe("secops_events")
        logger.info("SSE: Subscribed to secops_events channel")
        
        # Send initial connection event
        initial_message = {
            "event_type": "connection_status",
            "status": "connected",
            "message": "Connected to SSE stream"
        }
        yield f"data: {json.dumps(initial_message)}\n\n"
        
        # Monitor for client disconnect
        disconnect = asyncio.create_task(request.is_disconnected())
        
        # Listen for messages
        while True:
            # Check if client has disconnected
            if disconnect.done():
                logger.info("SSE: Client disconnected")
                break
                
            # Process messages with timeout
            message = pubsub.get_message(timeout=1.0)
            if message and message["type"] == "message":
                data = message["data"]
                if data:
                    yield f"data: {data}\n\n"
                    logger.debug(f"SSE: Sent message: {data[:50]}...")
            
            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.1)
                
    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    finally:
        # Clean up
        try:
            pubsub.unsubscribe("secops_events")
            pubsub.close()
            logger.info("SSE: Unsubscribed and closed pubsub")
        except:
            pass

# SSE endpoint
@router.get("/sse")
async def sse_endpoint(request: Request):
    """SSE endpoint for dashboard events."""
    logger.info("SSE connection requested")
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering in nginx
        }
    )
