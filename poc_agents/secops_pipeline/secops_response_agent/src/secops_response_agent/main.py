import logging
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Apply TaskState patch from shared helpers
import sys
sys.path.insert(0, '/app/shared')
try:
    from task_state_helpers import apply_taskstate_patch
    apply_taskstate_patch()
    print("Applied TaskState patch successfully")
except Exception as e:
    print(f"Warning: Failed to apply TaskState patch: {e}")

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
# Ensure Pydantic core validation error is imported if using Pydantic V2 elsewhere
try:
    from pydantic.v1 import ValidationError as PydanticV1ValidationError
    from pydantic import ValidationError as PydanticV2ValidationError
    # Instead of tuple, track individual validation errors
    HAS_PYDANTIC_V1 = True
    HAS_PYDANTIC_V2 = True
except ImportError:
    try: # Fallback for only Pydantic V2
        from pydantic import ValidationError as PydanticV2ValidationError
        HAS_PYDANTIC_V1 = False
        HAS_PYDANTIC_V2 = True
    except ImportError: # Fallback for only Pydantic V1
         from pydantic import ValidationError as PydanticV1ValidationError
         HAS_PYDANTIC_V1 = True
         HAS_PYDANTIC_V2 = False


# SDK Imports
try:
    from agentvault_server_sdk import create_a2a_router
    from agentvault_server_sdk.exceptions import AgentServerError, TaskNotFoundError, ConfigurationError, AgentProcessingError
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
    class AgentProcessingError(Exception): pass
    def task_not_found_handler(*args, **kwargs): pass
    def validation_exception_handler(*args, **kwargs): pass
    def agent_server_error_handler(*args, **kwargs): pass
    def generic_exception_handler(*args, **kwargs): pass
    class InMemoryTaskStore: pass
    class BaseTaskStore: pass

# Import agent logic
try:
    from .agent import SecOpsResponseAgent
    _AGENT_LOGIC_AVAILABLE = True
except ImportError:
     logging.critical("Failed to import local agent logic.", exc_info=True)
     _AGENT_LOGIC_AVAILABLE = False
     class SecOpsResponseAgent: pass # Placeholder

# Configure Logging
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level_str, logging.INFO), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# --- FastAPI App Setup ---
app = FastAPI(title="SecOps Response Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Agent Card Path ---
AGENT_CARD_PATH_STR = os.environ.get("AGENT_CARD_PATH", "/app/agent-card.json")
AGENT_CARD_PATH = Path(AGENT_CARD_PATH_STR)

# --- Agent Initialization ---
agent_instance: Optional[SecOpsResponseAgent] = None
if _SDK_AVAILABLE and _AGENT_LOGIC_AVAILABLE:
    try:
        task_store_instance: BaseTaskStore = InMemoryTaskStore()
        agent_instance = SecOpsResponseAgent(task_store=task_store_instance)

        # --- A2A Router Setup ---
        router_dependencies = []
        a2a_router = create_a2a_router(
            agent=agent_instance, task_store=task_store_instance,
            prefix="/a2a", tags=["A2A"], dependencies=router_dependencies
        )
        app.include_router(a2a_router)
        logger.info("A2A router included.")

        # --- Add Standard SDK Exception Handlers ---
        app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
        app.add_exception_handler(ValueError, validation_exception_handler)
        app.add_exception_handler(TypeError, validation_exception_handler)
        # Register individual Pydantic validation error classes
        if HAS_PYDANTIC_V1:
            app.add_exception_handler(PydanticV1ValidationError, validation_exception_handler)
        if HAS_PYDANTIC_V2:
            app.add_exception_handler(PydanticV2ValidationError, validation_exception_handler)
        app.add_exception_handler(ConfigurationError, agent_server_error_handler)
        # Handle specific processing errors from agent logic
        # Ensure we have a local reference to the module
        import agentvault_server_sdk
        if hasattr(agentvault_server_sdk.exceptions, 'AgentProcessingError'):
             app.add_exception_handler(agentvault_server_sdk.exceptions.AgentProcessingError, agent_server_error_handler)
        app.add_exception_handler(AgentServerError, agent_server_error_handler) # Base SDK server error
        app.add_exception_handler(Exception, generic_exception_handler) # Catch-all LAST
        logger.info("Standard AgentVault exception handlers added.")

    except Exception as e:
        logger.critical(f"CRITICAL ERROR during agent/router initialization: {e}", exc_info=True)
        raise RuntimeError("Failed to initialize agent components.") from e
else:
     logger.critical("AgentVault SDK or local agent logic failed to import. Cannot initialize agent.")
     @app.get("/")
     async def disabled_root(): return {"error": "Agent failed to initialize due to missing dependencies."}
     @app.post("/a2a")
     async def disabled_a2a(): raise HTTPException(status_code=503, detail="Agent service unavailable - initialization failed.")

# --- Standard Endpoints ---
# Agent ID for health check and logs
AGENT_ID = "SecOps Response Agent"
@app.get("/health", tags=["Management"])
async def health_check():
    """Basic health check."""
    return {"status": "ok", "agent_id": AGENT_ID if _AGENT_LOGIC_AVAILABLE else "UNKNOWN"}

@app.get("/agent-card.json", tags=["Agent Card"], response_model=Dict[str, Any])
async def get_agent_card_json():
    """Serves the agent's description card."""
    if not AGENT_CARD_PATH.is_file():
        logger.error(f"Agent card file not found at configured path: {AGENT_CARD_PATH.resolve()}")
        raise HTTPException(status_code=500, detail=f"Agent card configuration error: File not found at {AGENT_CARD_PATH}")
    try:
        with open(AGENT_CARD_PATH, 'r', encoding='utf-8') as f: return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load or parse agent card from {AGENT_CARD_PATH.resolve()}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load agent card: {e}")

@app.get("/", include_in_schema=False)
async def read_root():
    return {"message": f"{AGENT_ID} running. A2A endpoint at /a2a"}

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("SecOps Response Agent shutting down...")
    if agent_instance and hasattr(agent_instance, 'close') and callable(agent_instance.close):
        try: await agent_instance.close()
        except Exception as e: logger.error(f"Error during agent shutdown: {e}", exc_info=True)
    logger.info("Shutdown complete.")

logger.info(f"{AGENT_ID} application initialized successfully.")

# Allow running directly for local dev
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8073)) # Use the agent's default port
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    logger.info(f"Starting Uvicorn server for {AGENT_ID} on host 0.0.0.0, port {port}")
    uvicorn.run("secops_response_agent.main:app", host="0.0.0.0", port=port, log_level=log_level, reload=True)
