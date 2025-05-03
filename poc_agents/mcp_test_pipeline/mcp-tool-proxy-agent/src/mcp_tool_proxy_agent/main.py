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

# Import agent logic
from .agent import MCPToolProxyAgent

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="MCP Tool Proxy Agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Corrected Agent Card Path Logic ---
# AGENT_CARD_PATH is set via ENV VAR in Dockerfile to /app/agent-card.json
CARD_PATH_STR = os.environ.get("AGENT_CARD_PATH", "/app/agent-card.json") # Default if env var missing
CARD_PATH = Path(CARD_PATH_STR)
# --- End Correction ---

try:
    task_store: BaseTaskStore = InMemoryTaskStore()
    agent_instance = MCPToolProxyAgent()
    if hasattr(agent_instance, 'task_store'): agent_instance.task_store = task_store

    # --- Corrected Card Path Check ---
    if not CARD_PATH.is_file():
         logger.error(f"Agent card not found at expected path: {CARD_PATH.resolve()}")
         # Optionally raise an error or exit if card is critical for startup
         raise ConfigurationError(f"Agent card not found at: {CARD_PATH.resolve()}")
    # --- End Correction ---

    a2a_router = create_a2a_router(agent=agent_instance, task_store=task_store, prefix="/a2a", tags=["A2A"], dependencies=[Depends(lambda: BackgroundTasks())])
    app.include_router(a2a_router)
    app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
    app.add_exception_handler(ValueError, validation_exception_handler); app.add_exception_handler(TypeError, validation_exception_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)
    app.add_exception_handler(ConfigurationError, agent_server_error_handler); app.add_exception_handler(AgentServerError, agent_server_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
except Exception as e: logger.critical(f"Unexpected error during agent setup: {e}", exc_info=True)

@app.get("/", tags=["Status"])
async def read_root(): return {"message": "MCP Tool Proxy Agent running"}

# --- Corrected Card Path for Endpoint ---
# Use the same CARD_PATH variable defined above
@app.get("/agent-card.json", tags=["Agent Card"], response_model=Dict[str, Any])
async def get_agent_card_json():
    if not CARD_PATH.is_file():
        logger.error(f"Agent card endpoint: File not found at {CARD_PATH.resolve()}")
        raise HTTPException(status_code=500, detail="Agent card file not found.")
    try:
        with open(CARD_PATH, 'r', encoding='utf-8') as f: return json.load(f)
    except Exception as e:
        logger.error(f"Agent card endpoint: Failed to load card from {CARD_PATH.resolve()}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load agent card: {e}")
# --- End Correction ---

@app.on_event("shutdown")
async def shutdown_event():
    if hasattr(agent_instance, 'close') and callable(agent_instance.close):
        logger.info("Closing agent resources (HTTP client)..."); await agent_instance.close(); logger.info("Agent resources closed.")

logger.info("MCP Tool Proxy Agent application initialized.")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8059))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    logger.info(f"Starting Uvicorn server for MCP Tool Proxy Agent on host 0.0.0.0, port {port}")
    uvicorn.run("mcp_tool_proxy_agent.main:app", host="0.0.0.0", port=port, log_level=log_level, reload=False)
