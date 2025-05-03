import logging
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError as PydanticValidationError

# SDK Imports
from agentvault_server_sdk import create_a2a_router
from agentvault_server_sdk.exceptions import AgentServerError, TaskNotFoundError, ConfigurationError
from agentvault_server_sdk.state import InMemoryTaskStore, BaseTaskStore
from agentvault_server_sdk.fastapi_integration import (
    task_not_found_handler, validation_exception_handler,
    agent_server_error_handler, generic_exception_handler
)

# Import agent logic from the current package
from .agent import CustomerHistoryAgent

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- FastAPI App Setup ---
app = FastAPI(
    title="Customer History Agent",
    description="Retrieves customer status and interaction summary.",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for PoC
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Agent and Router Setup ---
try:
    task_store: BaseTaskStore = InMemoryTaskStore()
    agent_instance = CustomerHistoryAgent()
    if hasattr(agent_instance, 'task_store'):
        agent_instance.task_store = task_store
    else:
        logger.warning("Agent instance does not have a 'task_store' attribute.")

    # Create router using the SDK helper
    a2a_router = create_a2a_router(
        agent=agent_instance,
        task_store=task_store,
        prefix="/a2a", # Standard A2A prefix
        tags=["A2A"],
        dependencies=[Depends(lambda: BackgroundTasks())] # Inject BackgroundTasks
    )
    app.include_router(a2a_router)

    # --- Exception Handlers (Standard SDK handlers) ---
    app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
    app.add_exception_handler(ValueError, validation_exception_handler)
    app.add_exception_handler(TypeError, validation_exception_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)
    app.add_exception_handler(ConfigurationError, agent_server_error_handler)
    app.add_exception_handler(AgentServerError, agent_server_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

except ConfigurationError as e:
    logger.critical(f"Agent configuration failed during setup: {e}. Application cannot start properly.")
except Exception as e:
     logger.critical(f"Unexpected error during agent setup: {e}", exc_info=True)


# --- Root Endpoint ---
@app.get("/", tags=["Status"])
async def read_root():
    return {"message": "Customer History Agent running"}

# --- Serve Agent Card ---
AGENT_ROOT_DIR = Path(__file__).parent.parent.parent
CARD_PATH = AGENT_ROOT_DIR / "agent-card.json"

@app.get("/agent-card.json", tags=["Agent Card"], response_model=Dict[str, Any])
async def get_agent_card_json():
    """Serves the agent-card.json file."""
    if not CARD_PATH.is_file():
        logger.error(f"Agent card file not found at expected location: {CARD_PATH}")
        raise HTTPException(status_code=500, detail="Agent card configuration file not found on server.")
    try:
        with open(CARD_PATH, 'r', encoding='utf-8') as f:
            card_data = json.load(f)
        return card_data
    except Exception as e:
        logger.exception("Failed to load or parse agent-card.json")
        raise HTTPException(status_code=500, detail=f"Failed to load agent card: {e}")

logger.info("Customer History Agent application initialized.")

# --- Uvicorn Runner (for direct execution) ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8032)) # Default port for this agent
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    logger.info(f"Starting Uvicorn server for Customer History Agent on host 0.0.0.0, port {port}")
    uvicorn.run("customer_history_agent.main:app", host="0.0.0.0", port=port, log_level=log_level, reload=False)
