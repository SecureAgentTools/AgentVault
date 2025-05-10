"""
FastAPI application for SecOps Orchestrator
Note: This is primarily for development/testing, as the orchestrator
typically runs as a CLI command via run.py in production.
"""

import logging
import os
import sys
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
import json

# Import lifecycle management
from .lifecycle import register_shutdown_handler

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the run function for the pipeline
try:
    from .run import run_pipeline
except ImportError as e:
    logger.critical(f"Failed to import run_pipeline: {e}")
    raise

# Define API models
class AlertInput(BaseModel):
    """Model for alert input data."""
    alert_data: Dict[str, Any]
    project_id: Optional[str] = None
    config_path: Optional[str] = None

class PipelineResponse(BaseModel):
    """Model for pipeline execution response."""
    project_id: str
    status: str
    error_message: Optional[str] = None
    current_step: Optional[str] = None
    # Add other fields as needed

# Create FastAPI app
app = FastAPI(
    title="SecOps Orchestrator API",
    description="API for running the SecOps pipeline",
    version="0.1.0"
)

# Register shutdown handler
register_shutdown_handler(app)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "secops-orchestrator"}

@app.post("/run", response_model=PipelineResponse)
async def run(alert_input: AlertInput, background_tasks: BackgroundTasks):
    """Run the SecOps pipeline with the provided alert data."""
    try:
        # Run the pipeline
        logger.info(f"Running pipeline for alert with project_id: {alert_input.project_id or 'auto-generated'}")
        result = await run_pipeline(
            initial_alert_data=alert_input.alert_data,
            project_id=alert_input.project_id,
            config_path=alert_input.config_path
        )
        
        # Return the result
        return PipelineResponse(
            project_id=result.get("project_id", "unknown"),
            status=result.get("status", "UNKNOWN"),
            error_message=result.get("error_message"),
            current_step=result.get("current_step")
        )
    except Exception as e:
        logger.exception(f"Error running pipeline: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    uvicorn.run("secops_orchestrator.main:app", host="0.0.0.0", port=port, log_level=log_level, reload=True)
