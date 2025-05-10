"""
Standalone version of the SecOps Dashboard backend with WebSocket and SSE support.
All code is in a single file to avoid import issues.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
import redis
import json
import asyncio
import os
import logging
import random
from datetime import datetime
import socket

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("dashboard-backend")

print("\n\n=== STARTING STANDALONE BACKEND ===\n\n")

app = FastAPI()

# Set logging level from environment
log_level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
logging.getLogger().setLevel(getattr(logging, log_level))

# Configure CORS
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connection manager for WebSockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.connection_count = 0
        logger.info("Connection manager initialized")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_count += 1
        logger.info(f"New websocket connection accepted. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Websocket disconnected. Remaining active: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        logger.debug(f"Broadcasting message to {len(self.active_connections)} connections")
        disconnected_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected_connections.append(connection)
        
        # Remove disconnected connections
        for connection in disconnected_connections:
            if connection in self.active_connections:
                self.active_connections.remove(connection)
                logger.info(f"Removed disconnected connection. Remaining active: {len(self.active_connections)}")

manager = ConnectionManager()

# Redis connection - FIXED to use only secops-redis URL and no fallback
REDIS_URL = "redis://secops-redis:6379"
redis_client = None
redis_pubsub_task = None  # Global var to track the pubsub task

# Attempt to connect to Redis with improved error handling and timeout
def connect_to_redis():
    global redis_client
    try:
        # Connect to Redis with secops-redis service name only - no fallback to host.docker.internal
        logger.info(f"Connecting to Redis at fixed URL: {REDIS_URL}")
        redis_client = redis.Redis.from_url(
            REDIS_URL, 
            decode_responses=True,
            socket_connect_timeout=3.0,
            socket_timeout=3.0,
            health_check_interval=30
        )
        
        # Test connection with timeout
        ping_result = redis_client.ping()
        if ping_result:
            logger.info(f"✅ Successfully connected to Redis at {REDIS_URL}")
            return True
        else:
            logger.error("Redis ping returned unexpected result")
            redis_client = None
            return False
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {REDIS_URL}: {e}")
        redis_client = None
        return False

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("WebSocket connection attempt from client")
    await manager.connect(websocket)
    
    try:
        # Send initial connection message
        initial_message = {
            "event_type": "connection_status",
            "status": "connected",
            "message": "Connected to SecOps Dashboard",
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_text(json.dumps(initial_message))
        logger.info("Sent initial connection message to client")
        
        # Keep the connection alive
        while True:
            # Process any incoming messages from the client
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                logger.debug(f"Received message from client: {data[:100]}...")
                try:
                    # Echo back any messages received (for testing)
                    client_data = json.loads(data)
                    if client_data.get("type") == "ping":
                        logger.debug("Received ping, sending pong")
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except Exception as e:
                    logger.error(f"Error processing client message: {e}")
            except asyncio.TimeoutError:
                # Just continue the loop if no message is received
                pass
            
            # Small sleep to prevent CPU spinning
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Helper function to get redis client for SSE
def get_redis_client():
    if redis_client:
        return redis_client
    try:
        return redis.Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.error(f"Failed to connect to Redis for SSE: {e}")
        return None

# SSE Generator function
async def sse_event_generator(request: Request):
    """Generate SSE events from Redis Pub/Sub."""
    logger.info("Starting SSE event generator")
    
    # Try to get a Redis client for SSE
    sse_redis = get_redis_client()
    if not sse_redis:
        yield f"data: {json.dumps({'error': 'Redis connection failed'})}\n\n"
        return

    pubsub = sse_redis.pubsub()
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
        
        # Listen for messages with a keepalive
        while True:
            # Check if client has disconnected
            if disconnect.done():
                logger.info("SSE: Client disconnected")
                break
                
            # Send a keepalive comment every 15 seconds
            yield f": keepalive {datetime.now().isoformat()}\n\n"
            
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
        except Exception as e:
            logger.error(f"Error cleaning up SSE connection: {e}")

# SSE endpoint (directly defined, not using a router)
@app.get("/sse")
async def sse_endpoint(request: Request):
    """SSE endpoint for dashboard events."""
    logger.info("SSE connection requested")
    return StreamingResponse(
        sse_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering in nginx
        }
    )

# Handle Redis messages in a separate task
async def redis_message_handler(message):
    if message["type"] == "message":
        data = message["data"]
        logger.debug(f"Received Redis message: {data[:100]}...")
        await manager.broadcast(data)

# Redis pubsub listener for WebSockets with improved error handling
async def redis_listener():
    global redis_pubsub_task
    
    if not redis_client:
        logger.warning("Redis client not available for listener - aborting listener")
        return
    
    logger.info("Starting Redis listener task...")
    
    retries = 0
    max_retries = 5
    
    while retries < max_retries:
        try:
            # Create a new pubsub connection for this listener
            pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
            
            # Subscribe to the channel - THIS IS THE CRITICAL STEP!
            pubsub.subscribe("secops_events")
            logger.info("✅ Successfully subscribed to 'secops_events' Redis channel!")
            
            # Check subscriber count after subscribing
            try:
                sub_count = redis_client.execute_command("PUBSUB", "NUMSUB", "secops_events")
                logger.info(f"Current subscribers to secops_events after our subscription: {sub_count}")
            except Exception as e:
                logger.error(f"Error checking subscriber count: {e}")
            
            # Loop through messages
            logger.info("Starting message processing loop")
            while True:
                message = pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    logger.info(f"Received message from Redis: {message}")
                    # Process message in a separate task to prevent blocking
                    asyncio.create_task(redis_message_handler(message))
                await asyncio.sleep(0.01)  # Prevent CPU spinning
                
        except redis.exceptions.ConnectionError as e:
            retries += 1
            logger.error(f"Redis listener connection error (retry {retries}/{max_retries}): {e}")
            await asyncio.sleep(5)  # Wait before retrying
            
        except Exception as e:
            logger.error(f"Unexpected Redis listener error: {e}")
            retries += 1
            await asyncio.sleep(5)  # Wait before retrying
    
    logger.error(f"Redis listener failed after {max_retries} retries. Dashboard updates will not work!")

# Startup event handler
@app.on_event("startup")
async def startup_event():
    global redis_pubsub_task
    
    # Print networking info for diagnostics
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "unknown"
    
    print("\n=== DASHBOARD BACKEND STARTING ===")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Hostname: {hostname}")
    print(f"Local IP: {local_ip}")
    print(f"Binding to: 0.0.0.0:8081")
    print(f"REDIS_URL: {REDIS_URL}")
    print(f"LOG_LEVEL: {log_level}")
    print("===================================\n")
    
    # Ensure Redis connection works
    redis_connected = connect_to_redis()
    if redis_connected:
        print(f"✅ Connected to Redis at {REDIS_URL}")
        
        # Start Redis listener in background task
        redis_pubsub_task = asyncio.create_task(redis_listener())
        print("✅ Started Redis pubsub listener task")
    else:
        print(f"❌ Failed to connect to Redis at {REDIS_URL} - Dashboard updates will not work!")
    
    print("🚀 FastAPI backend startup completed!")
    
    # Test Redis directly to verify subscription
    if redis_client:
        try:
            test_message = {
                "event_type": "startup_test",
                "message": "Backend startup test",
                "timestamp": datetime.now().isoformat()
            }
            subscribers = redis_client.publish("secops_events", json.dumps(test_message))
            print(f"📣 Published startup test message to Redis. Subscribers: {subscribers}")
        except Exception as e:
            print(f"❌ Failed to publish startup test message: {e}")
    
    return True  # Ensure startup completes

# Root endpoint
@app.get("/", response_class=HTMLResponse)
async def root():
    # Show Redis connection status
    redis_status = "Connected" if redis_client else "Disconnected"
    redis_color = "green" if redis_client else "red"
    
    return f"""
    <html>
        <head>
            <title>SecOps Dashboard Backend</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                h1 {{ color: #333; }}
                .status {{ font-weight: bold; }}
                .connected {{ color: green; }}
                .disconnected {{ color: red; }}
                pre {{ background: #f4f4f4; padding: 10px; border-radius: 5px; }}
                a {{ color: #0066cc; }}
            </style>
        </head>
        <body>
            <h1>SecOps Dashboard Backend</h1>
            <p>Status: <span class="status connected">Running</span></p>
            <p>Redis: <span class="status {redis_color}">{redis_status}</span></p>
            <p>WebSocket connections: {len(manager.active_connections)}</p>
            <p>WebSocket endpoint available at: <pre>ws://[hostname]:8081/ws</pre></p>
            <p>SSE endpoint available at: <pre>http://[hostname]:8081/sse</pre></p>
            <p>Health check endpoint: <a href="/health">/health</a></p>
            <p>Test broadcast endpoint: <a href="/test-broadcast">/test-broadcast</a></p>
            <p>Pipeline simulation: <a href="/test-pipeline-execution">/test-pipeline-execution</a></p>
            <p>Debug routes: <a href="/debug/routes">/debug/routes</a></p>
        </body>
    </html>
    """

# Healthcheck endpoint
@app.get("/health")
def health_check():
    # Check Redis connection
    redis_connected = False
    if redis_client:
        try:
            ping_result = redis_client.ping()
            redis_connected = ping_result
        except Exception as e:
            logger.warning(f"Redis ping failed in health check: {e}")
            redis_connected = False
    
    # Check if Redis pubsub task is running
    pubsub_running = redis_pubsub_task is not None and not redis_pubsub_task.done()
    
    return {
        "status": "ok",  # Always ok so nginx can connect
        "redis_status": "connected" if redis_connected else "disconnected",
        "redis_pubsub": "running" if pubsub_running else "stopped",
        "active_connections": len(manager.active_connections),
        "total_connections": manager.connection_count,
        "timestamp": datetime.now().isoformat()
    }

# Debug endpoint to list all routes
@app.get("/debug/routes")
async def debug_routes():
    routes = [{
        "path": route.path,
        "name": route.name,
        "methods": list(route.methods) if hasattr(route, "methods") and route.methods else ["NONE"]
    } for route in app.routes]
    return {"routes": routes}

# Test broadcast endpoint
@app.get("/test-broadcast")
async def test_broadcast():
    test_message = {
        "event_type": "test_event",
        "message": "This is a test broadcast event",
        "timestamp": datetime.now().isoformat()
    }
    
    # Broadcast to WebSocket clients
    message_str = json.dumps(test_message)
    await manager.broadcast(message_str)
    logger.info(f"Broadcast test message to {len(manager.active_connections)} WebSocket clients")
    
    # Also publish to Redis for SSE clients
    redis_published = False
    if redis_client:
        try:
            subscribers = redis_client.publish("secops_events", message_str)
            logger.info(f"Published test message to Redis. Subscribers: {subscribers}")
            redis_published = True
        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")
    
    return {
        "status": "test message broadcast",
        "websocket_recipients": len(manager.active_connections),
        "sse_published": redis_published,
        "message": test_message
    }

# Test pipeline execution endpoint
@app.get("/test-pipeline-execution")
async def test_pipeline_execution():
    """
    Simulates a complete pipeline execution for testing the dashboard.
    Publishes a realistic sequence of pipeline events.
    """
    if not redis_client:
        return {
            "status": "error", 
            "message": "Redis client not available, cannot publish events"
        }
    
    # Start with a base execution ID using current timestamp
    exec_id = f"secops-{datetime.now().strftime('%Y%m%d%H%M%S')}-{os.urandom(3).hex()}"
    
    # Generate realistic events that match what the frontend expects
    events = [
        # Initial state
        {
            "event_type": "pipeline_execution",
            "status": "STARTING",
            "project_id": exec_id,
            "step": "start",
            "step_number": 1,
            "message": "Pipeline execution starting",
            "timestamp": datetime.now().isoformat()
        },
        # Ingest alert
        {
            "event_type": "pipeline_execution",
            "status": "IN_PROGRESS",
            "project_id": exec_id,
            "step": "ingest_alert",
            "step_number": 2,
            "message": "Ingested alert from Firewall",
            "alert": {
                "name": "Suspicious Authentication Activity",
                "source": "Firewall", 
                "time": datetime.now().isoformat(),
                "user": "admin@example.com",
                "source_ip": "198.51.100.42",
                "description": "Multiple failed login attempts followed by successful login from unusual geographical location"
            },
            "timestamp": datetime.now().isoformat()
        },
        # Enrichment 
        {
            "event_type": "pipeline_execution",
            "status": "IN_PROGRESS",
            "project_id": exec_id,
            "step": "enrichment", 
            "step_number": 3,
            "message": "Enriched alert data with threat intelligence",
            "enrichment_results": [
                {"indicator": "198.51.100.42", "type": "IP Address", "verdict": "Suspicious"},
                {"indicator": "admin@example.com", "type": "Username", "verdict": "Legitimate"}
            ],
            "timestamp": datetime.now().isoformat()
        },
        # Investigation
        {
            "event_type": "pipeline_execution",
            "status": "IN_PROGRESS",
            "project_id": exec_id,
            "step": "investigation",
            "step_number": 4, 
            "message": "Completed investigation",
            "timestamp": datetime.now().isoformat()
        },
        # LLM Decision
        {
            "event_type": "pipeline_execution",
            "status": "IN_PROGRESS", 
            "project_id": exec_id,
            "step": "determine_response",
            "step_number": 5,
            "message": "LLM has determined appropriate response",
            "llm_decision": {
                "severity": "Medium",
                "confidence_percentage": 87,
                "recommended_action": "CREATE_TICKET",
                "reasoning": "The login activity shows a suspicious pattern from an unusual IP address. While the user account is legitimate, the behavior is anomalous enough to warrant investigation. Since there's no evidence of data exfiltration or system compromise, a medium-severity ticket is appropriate rather than immediate blocking or isolation."
            },
            "timestamp": datetime.now().isoformat()
        },
        # Execute Response
        {
            "event_type": "pipeline_execution",
            "status": "IN_PROGRESS",
            "project_id": exec_id, 
            "step": "execute_response",
            "step_number": 6,
            "message": "Executing response action: Create Ticket",
            "response_action": {
                "action_type": "CREATE_TICKET",
                "status": "Success", 
                "details": {
                    "ticket_id": f"SEC-{datetime.now().strftime('%Y')}-{random.randint(1000, 9999)}"
                },
                "parameters": {
                    "summary": "Suspicious authentication activity for admin@example.com", 
                    "priority": "Medium",
                    "affected_systems": ["firewall.example.com", "auth.example.com"]
                }
            },
            "timestamp": datetime.now().isoformat()
        },
        # Completion
        {
            "event_type": "pipeline_execution",
            "status": "COMPLETED",
            "project_id": exec_id,
            "step": "complete", 
            "step_number": 7,
            "message": "Pipeline execution completed successfully",
            "duration_seconds": 8.42,
            "timestamp": datetime.now().isoformat()
        }
    ]
    
    # Use asyncio to publish events with realistic timing
    async def publish_events():
        for idx, event in enumerate(events):
            # Publish the event
            try:
                redis_client.publish("secops_events", json.dumps(event))
                logger.info(f"Published test event {idx+1}/{len(events)}: {event['step']}")
            except Exception as e:
                logger.error(f"Error publishing test event: {e}")
            
            # Wait before publishing the next event (simulate real processing time)
            if idx < len(events) - 1:  # Don't wait after the last event
                await asyncio.sleep(1.5)  # 1.5 seconds between events
    
    # Start the publishing task
    asyncio.create_task(publish_events())
    
    return {
        "status": "started",
        "message": "Test pipeline execution started",
        "project_id": exec_id,
        "events_count": len(events)
    }

# For testing: endpoint to trigger a deliberate error
@app.get("/test-error")
async def test_error():
    try:
        # Try something that might fail
        if redis_client:
            redis_client.ping()
            return {"status": "Redis connection is working"}
        else:
            return {"status": "Redis client is not initialized", "error": True}
    except Exception as e:
        logger.error(f"Test error endpoint: {e}")
        return {"status": "error", "message": str(e)}

# For testing: direct Redis communication
@app.get("/redis-test")
async def redis_test():
    if not redis_client:
        return {"status": "error", "message": "Redis client not available"}
    
    try:
        # Test Redis connection
        ping_result = redis_client.ping()
        
        # Check subscribers - Changed to direct command format to avoid previous potential issues
        subscribers = redis_client.execute_command("PUBSUB", "NUMSUB", "secops_events")
        
        # Publish a test message
        test_message = {
            "event_type": "redis_test",
            "message": "Direct Redis test",
            "timestamp": datetime.now().isoformat()
        }
        publish_result = redis_client.publish("secops_events", json.dumps(test_message))
        
        return {
            "status": "success",
            "ping": ping_result,
            "subscribers": subscribers,
            "published": publish_result
        }
    except Exception as e:
        logger.error(f"Redis test error: {e}")
        return {"status": "error", "message": str(e)}

# Run the app directly when this file is executed
if __name__ == "__main__":
    import uvicorn
    print("\n\n=== STARTING STANDALONE BACKEND ===\n\n")
    print("⚠️ Attempting to start HTTP server on 0.0.0.0:8081")
    try:
        uvicorn.run(app, host="0.0.0.0", port=8081, log_level="debug", log_config={
            "version": 1,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                }
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "DEBUG"},
                "uvicorn.error": {"handlers": ["default"], "level": "DEBUG"},
                "uvicorn.access": {"handlers": ["default"], "level": "DEBUG"},
            }
        })
        print("Server has stopped.")
    except Exception as e:
        print(f"⚠️ ERROR STARTING SERVER: {e}")
        import traceback
        traceback.print_exc()
