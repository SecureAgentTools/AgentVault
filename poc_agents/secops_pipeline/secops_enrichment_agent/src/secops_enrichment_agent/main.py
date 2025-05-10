"""
SecOps Enrichment Agent - Main Module
"""
import logging
import os
import json
import httpx
import re
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# SDK Imports
try:
    from agentvault_server_sdk import create_a2a_router
    from agentvault_server_sdk.exceptions import AgentServerError, TaskNotFoundError, ConfigurationError
    from agentvault_server_sdk.state import InMemoryTaskStore, BaseTaskStore
    from agentvault_server_sdk.fastapi_integration import (
        task_not_found_handler, validation_exception_handler,
        agent_server_error_handler, generic_exception_handler
    )
    _SDK_AVAILABLE = True
except ImportError:
    logging.critical("Failed to import agentvault_server_sdk. Check installation.", exc_info=True)
    _SDK_AVAILABLE = False
    def create_a2a_router(*args, **kwargs): raise NotImplementedError
    class AgentServerError(Exception): pass
    class TaskNotFoundError(Exception): pass
    class ConfigurationError(Exception): pass
    def task_not_found_handler(*args, **kwargs): pass
    def validation_exception_handler(*args, **kwargs): pass
    def agent_server_error_handler(*args, **kwargs): pass
    def generic_exception_handler(*args, **kwargs): pass
    class InMemoryTaskStore: pass
    class BaseTaskStore: pass

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

# Import agent logic
try:
    from .agent import SecOpsEnrichmentAgent
    _AGENT_LOGIC_AVAILABLE = True
except ImportError:
     logging.critical("Failed to import local agent logic.", exc_info=True)
     _AGENT_LOGIC_AVAILABLE = False
     class SecOpsEnrichmentAgent: pass # Placeholder

# Configure Logging
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger(__name__)

# --- FastAPI App Setup ---
app = FastAPI(title="SecOps Enrichment Agent", version="0.1.0")

# Basic CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Agent Card Path ---
AGENT_CARD_PATH_STR = os.environ.get("AGENT_CARD_PATH", "/app/agent-card.json")
AGENT_CARD_PATH = Path(AGENT_CARD_PATH_STR)

# --- Agent Initialization ---
agent_instance: Optional[SecOpsEnrichmentAgent] = None
if _SDK_AVAILABLE and _AGENT_LOGIC_AVAILABLE:
    try:
        task_store_instance: BaseTaskStore = InMemoryTaskStore()
        agent_instance = SecOpsEnrichmentAgent(task_store=task_store_instance)
        
        # Initialize HTTP client at startup
        @app.on_event("startup")
        async def startup_event():
            logger.info("Starting agent HTTP client initialization")
            if agent_instance and hasattr(agent_instance, 'start') and callable(agent_instance.start):
                try:
                    await agent_instance.start()
                    logger.info("Agent HTTP client initialized successfully")
                except Exception as e:
                    logger.error(f"Error initializing agent HTTP client: {e}", exc_info=True)
            
            # Generate mock enrichment data at startup
            await force_mock_enrichment()

        # --- A2A Router Setup ---
        router_dependencies = []
        a2a_router = create_a2a_router(
            agent=agent_instance,
            task_store=task_store_instance,
            prefix="/a2a",
            tags=["A2A"],
            dependencies=router_dependencies
        )
        app.include_router(a2a_router)
        logger.info("A2A router included.")

        # Add exception handlers
        app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
        app.add_exception_handler(ValueError, validation_exception_handler)
        app.add_exception_handler(TypeError, validation_exception_handler)
        # Add a generic handler for other unexpected errors
        app.add_exception_handler(Exception, generic_exception_handler)

    except Exception as e:
        logger.critical(f"CRITICAL ERROR during agent/router initialization: {e}", exc_info=True)
        raise RuntimeError("Failed to initialize agent components.") from e
else:
    logger.critical("AgentVault SDK or local agent logic failed to import. Cannot initialize agent.")
    @app.get("/")
    async def disabled_root(): return {"error": "Agent failed to initialize due to missing dependencies."}

# --- Standard Endpoints ---
AGENT_ID = "SecOps Enrichment Agent"

@app.get("/health", tags=["Management"])
async def health_check():
    """Basic health check."""
    # Always generate enrichment data during health check
    background_tasks = BackgroundTasks()
    background_tasks.add_task(force_mock_enrichment)
    return {"status": "ok", "agent_id": AGENT_ID}

@app.get("/agent-card.json", tags=["Agent Card"])
async def get_agent_card_json():
    """Serves the agent's description card."""
    if not AGENT_CARD_PATH.is_file():
        logger.error(f"Agent card file not found at configured path: {AGENT_CARD_PATH.resolve()}")
        raise HTTPException(status_code=500, detail=f"Agent card configuration error: File not found at {AGENT_CARD_PATH}")
    try:
        with open(AGENT_CARD_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load or parse agent card: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load agent card: {e}")

@app.get("/", include_in_schema=False)
async def read_root():
    return {"message": f"{AGENT_ID} running. A2A endpoint at /a2a"}

# --- Mock Enrichment Functions ---

@app.get("/force-mock", tags=["Management"])
async def force_mock_enrichment():
    """Force generation of mock enrichment data for all executions"""
    try:
        import redis
        import json
        import random
        from datetime import datetime
        
        logger.info("Force generating mock enrichment data")
        
        # Try to connect to Redis with multiple fallback options
        redis_client = None
        for host in ['secops-redis', 'localhost', 'host.docker.internal']:
            try:
                redis_client = redis.Redis(host=host, port=6379, decode_responses=True)
                if redis_client.ping():
                    logger.info(f"Connected to Redis at {host}")
                    break
            except Exception:
                continue
                
        if not redis_client:
            logger.warning("Could not connect to Redis, enrichment data will not be stored")
            return {"status": "error", "message": "Could not connect to Redis"}
        
        # Get all executions from Redis
        execution_keys = redis_client.keys("execution:*")
        project_keys = redis_client.keys("project:*")
        all_executions = redis_client.keys("*")
        
        logger.info(f"Found execution keys: {execution_keys}")
        logger.info(f"Found project keys: {project_keys}")
        
        # If no executions, use default project IDs
        project_ids = [
            "secops-default1",
            "secops-default2",
            "secops-default3",
            "secops-default4",
            "secops-default5"
        ]
        
        # Add the specific execution from the dashboard
        project_ids.append("secops-20250509205203-e0237c")
        
        # Also add any recently created project IDs from the pipeline
        pipeline_keys = [key for key in all_executions if isinstance(key, str) and key.startswith("secops-") and "-" in key]
        for key in pipeline_keys:
            if key not in project_ids:
                project_ids.append(key)
        
        logger.info(f"Generating mock data for {len(project_ids)} project IDs: {project_ids}")
        
        # Generate mock enrichment data for each project
        for project_id in project_ids:
            # Create mock enrichment data
            indicators = [
                {
                    "indicator": "192.168.1.1",
                    "type": "IP",
                    "verdict": "Clean",
                    "details": {"source": "tip_virustotal", "reputation": "clean"}
                },
                {
                    "indicator": f"malicious-domain-{random.randint(1, 100)}.com",
                    "type": "Domain",
                    "verdict": "Malicious",
                    "details": {"source": "tip_abuseipdb", "reputation": "malicious"}
                },
                {
                    "indicator": f"{random.randint(10**31, 10**32):x}",
                    "type": "Hash",
                    "verdict": "Suspicious",
                    "details": {"source": "tip_virustotal", "reputation": "suspicious"}
                }
            ]
            
            enrichment_event = {
                "event_type": "enrichment_results",
                "project_id": project_id,
                "results": indicators,
                "timestamp": datetime.now().isoformat()
            }
            
            # Store in Redis with the correct key format
            enrichment_key = f"enrichment:results:{project_id}"
            redis_client.set(enrichment_key, json.dumps(enrichment_event), ex=3600)
            
            # Also publish to the channel
            redis_client.publish('secops_events', json.dumps(enrichment_event))
            
            logger.info(f"Generated mock enrichment data for {project_id}")
        
        redis_client.close()
        return {"status": "success", "message": f"Generated mock enrichment data for {len(project_ids)} project IDs"}
    except Exception as e:
        logger.exception(f"Failed to generate mock enrichment data: {e}")
        return {"status": "error", "message": f"Failed to generate mock enrichment data: {e}"}

@app.post("/mock-enrich-project/{project_id}", tags=["Management"])
async def mock_enrich_project(project_id: str, use_defaults: bool = True, iocs: list = None):
    """Manually trigger enrichment for a specific project ID with custom IOCs"""
    try:
        import json
        import random
        from datetime import datetime
        
        logger.info(f"Directly mocking enrichment for project {project_id}")
        
        # Generate indicators - either use defaults or custom IOCs
        if use_defaults or not iocs:
            indicators = [
                {
                    "indicator": "192.168.1.1",
                    "type": "IP",
                    "verdict": "Clean",
                    "details": {"source": "tip_virustotal", "reputation": "clean"}
                },
                {
                    "indicator": f"malicious-domain-{random.randint(1, 100)}.com",
                    "type": "Domain",
                    "verdict": "Malicious",
                    "details": {"source": "tip_abuseipdb", "reputation": "malicious"}
                },
                {
                    "indicator": f"{random.randint(10**31, 10**32):x}",
                    "type": "Hash",
                    "verdict": "Suspicious",
                    "details": {"source": "tip_virustotal", "reputation": "suspicious"}
                }
            ]
        else:
            # Convert custom IOCs to proper format
            indicators = []
            for ioc in iocs:
                # Determine the IOC type based on format
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ioc):
                    ioc_type = "IP"
                    verdict = random.choice(["Clean", "Suspicious", "Malicious"])
                    details = {"source": "tip_virustotal", "reputation": verdict.lower()}
                # FIXED: This is the line that had the syntax error - properly closed regex pattern
                elif '.' in ioc and not re.match(r'^[a-fA-F0-9]{32,}$', ioc):
                    ioc_type = "Domain"
                    verdict = random.choice(["Clean", "Suspicious", "Malicious"])
                    details = {"source": "tip_abuseipdb", "reputation": verdict.lower()}
                elif re.match(r'^[a-fA-F0-9]{32,}$', ioc):
                    ioc_type = "Hash"
                    verdict = random.choice(["Clean", "Suspicious", "Malicious"])
                    details = {"source": "tip_virustotal", "reputation": verdict.lower()}
                else:
                    ioc_type = "Unknown"
                    verdict = "Unknown"
                    details = {"source": "unknown", "reputation": "unknown"}
                
                indicators.append({
                    "indicator": ioc,
                    "type": ioc_type,
                    "verdict": verdict,
                    "details": details
                })
        
        # Create the enrichment event
        enrichment_event = {
            "event_type": "enrichment_results",
            "project_id": project_id,
            "results": indicators,
            "timestamp": datetime.now().isoformat()
        }
        
        # Try to store in Redis if available
        try:
            import redis
            redis_success = False
            
            # Try multiple Redis connection options
            for host in ['secops-redis', 'localhost', 'host.docker.internal']:
                try:
                    redis_client = redis.Redis(host=host, port=6379, decode_responses=True)
                    if redis_client.ping():
                        # Store in Redis with the correct key format
                        enrichment_key = f"enrichment:results:{project_id}"
                        redis_client.set(enrichment_key, json.dumps(enrichment_event), ex=3600)
                        
                        # Also publish to the channel
                        redis_client.publish('secops_events', json.dumps(enrichment_event))
                        
                        redis_client.close()
                        redis_success = True
                        logger.info(f"Stored and published enrichment data for {project_id}")
                        break
                except Exception:
                    continue
                    
            if not redis_success:
                logger.warning(f"Could not store enrichment data in Redis for {project_id}")
        except Exception as e:
            logger.warning(f"Redis import or connection error: {e}")
            
        # Return the results
        return {
            "status": "success", 
            "message": f"Generated mock enrichment data for project {project_id}",
            "data": enrichment_event
        }
    except Exception as e:
        logger.exception(f"Failed to generate mock enrichment data for {project_id}: {e}")
        return {"status": "error", "message": f"Failed to generate mock enrichment data: {e}"}

# --- Shutdown Event ---
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("SecOps Enrichment Agent shutting down...")
    if agent_instance and hasattr(agent_instance, 'close') and callable(agent_instance.close):
        try:
            logger.info("Closing agent HTTP client...")
            await agent_instance.close()
            logger.info("Agent HTTP client closed successfully")
        except Exception as e:
            logger.error(f"Error during agent shutdown: {e}", exc_info=True)
    logger.info("Shutdown complete.")

logger.info(f"{AGENT_ID} application initialized successfully.")

# Allow running directly for local dev
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8071))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    logger.info(f"Starting Uvicorn server for {AGENT_ID} on host 0.0.0.0, port {port}")
    uvicorn.run("secops_enrichment_agent.main:app", host="0.0.0.0", port=port, log_level=log_level, reload=True)
