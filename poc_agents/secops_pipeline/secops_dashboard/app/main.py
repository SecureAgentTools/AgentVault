import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("dashboard-api")

# Initialize FastAPI app
app = FastAPI(title="SecOps Pipeline Dashboard API")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection settings
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
logger.info(f"Using Redis URL: {REDIS_URL}")

# Test Redis connection on startup
try:
    async def test_redis_connection():
        redis = aioredis.Redis.from_url(REDIS_URL)
        try:
            await redis.ping()
            logger.info("Successfully connected to Redis")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False
        finally:
            await redis.close()
            
    @app.on_event("startup")
    async def test_redis_on_startup():
        await test_redis_connection()
        
except Exception as e:
    logger.error(f"Error setting up Redis test: {e}")

# Store recent executions in memory for demo purposes
# In production, use a persistent store
recent_executions: List[Dict] = []
pipeline_states: Dict[str, Dict] = {}

# Store active websocket connections
connected_clients = set()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                # Don't remove here to avoid modifying list during iteration


manager = ConnectionManager()

async def redis_listener():
    """Background task to listen for Redis events and broadcast to clients."""
    try:
        redis = aioredis.Redis.from_url(REDIS_URL)
        pubsub = redis.pubsub()
        await pubsub.subscribe("pipeline_events")
        logger.info("Started Redis listener for pipeline events")
        
        while True:
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message and message["type"] == "message":
                    data = message["data"].decode()
                    logger.info(f"========= RECEIVED EVENT: {data[:150]}...")
                    
                    # Process the message
                    event_data = json.loads(data)
                    
                    # Store execution data if it's a new execution or update
                    project_id = event_data.get("data", {}).get("project_id")
                    if project_id:
                        pipeline_states[project_id] = {
                            **pipeline_states.get(project_id, {}),
                            **event_data.get("data", {}),
                            "last_updated": datetime.now(timezone.utc).isoformat(),
                        }
                        
                        # If this is a new execution or final state, add to recent_executions
                        if event_data.get("type") == "execution_started" or event_data.get("type") == "execution_completed":
                            # Check if we already have this execution
                            existing = next((x for x in recent_executions if x.get("project_id") == project_id), None)
                            if existing:
                                # Update existing entry
                                existing.update(pipeline_states[project_id])
                            else:
                                # Add new entry, keeping only the most recent 10
                                recent_executions.insert(0, pipeline_states[project_id])
                                if len(recent_executions) > 10:
                                    recent_executions.pop()
                    
                    # Broadcast to all connected clients
                    await manager.broadcast(data)
                
                # Small sleep to prevent high CPU usage
                await asyncio.sleep(0.1)
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from Redis message: {e}")
            except Exception as e:
                logger.error(f"Error processing Redis message: {e}")
                await asyncio.sleep(1)  # Longer sleep on error
                
    except Exception as e:
        logger.error(f"Redis listener error: {e}")
    finally:
        # Ensure pubsub and redis are properly closed
        try:
            await pubsub.unsubscribe("pipeline_events")
            await redis.close()
            logger.info("Closed Redis connection")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")


@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    asyncio.create_task(redis_listener())
    logger.info("Dashboard API started")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Websocket endpoint for real-time updates."""
    await manager.connect(websocket)
    logger.info("New WebSocket client connected")
    
    # Send initial data to the new client
    try:
        # Send recent executions and pipeline states
        initial_data = {
            "type": "initial_data",
            "data": {
                "recent_executions": recent_executions,
                "pipeline_states": pipeline_states,
            }
        }
        await websocket.send_text(json.dumps(initial_data))
        
        # Keep connection alive until client disconnects
        while True:
            # Just wait for client to disconnect
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.get("/api/recent-executions")
async def get_recent_executions():
    """Get list of recent pipeline executions."""
    return {"executions": recent_executions}


@app.get("/api/pipeline-state/{project_id}")
async def get_pipeline_state(project_id: str):
    """Get current state of a specific pipeline execution."""
    if project_id not in pipeline_states:
        return {"error": "Pipeline execution not found"}, 404
    return pipeline_states[project_id]


# Serve static files (React frontend)
import os
static_dir = os.path.join(os.getcwd(), "static")
logger.info(f"Mounting static files from: {static_dir}")

if os.path.exists(static_dir) and os.listdir(static_dir):
    logger.info(f"Static directory exists: {os.listdir(static_dir)}")
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
else:
    # Use fallback static page
    fallback_dir = os.path.join(os.getcwd(), "static_fallback")
    logger.warning(f"Static directory empty or missing, using fallback: {fallback_dir}")
    if os.path.exists(fallback_dir):
        app.mount("/", StaticFiles(directory="static_fallback", html=True), name="static")
    else:
        logger.error(f"Neither static nor fallback directories exist!")
        
        # Create emergency index.html
        os.makedirs(static_dir, exist_ok=True)
        with open(os.path.join(static_dir, "index.html"), "w") as f:
            f.write('<html><body style="background:#1a202c;color:white;font-family:sans-serif;padding:2rem;">' + 
                   '<h1>SecOps Pipeline Dashboard</h1>' + 
                   '<p>Dashboard is starting up. Please refresh in a few seconds.</p>' + 
                   '<script>setTimeout(()=>location.reload(),5000)</script>' + 
                   '</body></html>')
        app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
