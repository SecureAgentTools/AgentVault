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
from .agent import UserProfileAgent

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- FastAPI App Setup ---
app = FastAPI(
    title="User Profile Agent",
    description="Retrieves user profile data for e-commerce recommendations.",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# --- Agent and Router Setup ---
try:
    task_store: BaseTaskStore = InMemoryTaskStore()
    agent_instance = UserProfileAgent()
    agent_instance.task_store = task_store

    # Create router with BackgroundTasks dependency
    a2a_router = create_a2a_router(
        agent=agent_instance,
        task_store=task_store,
        prefix="/a2a",
        tags=["A2A"],
        dependencies=[Depends(lambda: BackgroundTasks())] # Inject BackgroundTasks
    )
    app.include_router(a2a_router)

    # --- Exception Handlers ---
    app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
    app.add_exception_handler(ValueError, validation_exception_handler)
    app.add_exception_handler(TypeError, validation_exception_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)
    app.add_exception_handler(ConfigurationError, agent_server_error_handler)
    app.add_exception_handler(AgentServerError, agent_server_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

except ConfigurationError as e:
    logger.critical(f"Agent configuration failed: {e}. Application cannot start.")
    # Optionally, define a fallback startup sequence or exit
    # For now, FastAPI will fail to start fully if agent init fails.

# --- Root Endpoint ---
@app.get("/", tags=["Status"])
async def read_root():
    return {"message": "User Profile Agent running"}

# --- Serve Agent Card ---
# Assumes agent-card.json is in the root of the agent project directory
# The path needs to be relative to *this file's location*
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

logger.info("User Profile Agent application initialized.")

# --- Uvicorn Runner (for direct execution) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8020))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    logger.info(f"Starting Uvicorn server on host 0.0.0.0, port {port}")
    # Use the package name for the app string
    uvicorn.run("ecommerce_user_profile_agent.main:app", host="0.0.0.0", port=port, log_level=log_level, reload=False)
