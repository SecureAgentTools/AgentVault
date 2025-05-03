import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
import uuid
import json
from pathlib import Path

# Import state definition, models, config, and utilities for this pipeline
from etl_orchestrator.state_definition import EtlProcessingState
from etl_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
# No local storage utils needed as artifacts are in DB
from etl_orchestrator.config import EtlPipelineConfig

logger = logging.getLogger(__name__)

# --- Constants for node names ---
START_PIPELINE_NODE = "start_etl_pipeline"
EXTRACT_DATA_NODE = "extract_data"
TRANSFORM_DATA_NODE = "transform_data"
VALIDATE_DATA_NODE = "validate_data"
LOAD_DATA_NODE = "load_data"
ERROR_HANDLER_NODE = "handle_pipeline_error"

# --- Node Functions (REQ-ETL-ORCH-004) ---

async def start_etl_pipeline(state: EtlProcessingState) -> Dict[str, Any]:
    """Initial node: Logs start, validates essential state components."""
    project_id = state["project_id"]
    source_id = state["source_identifier"]
    config: EtlPipelineConfig = state.get("pipeline_config") # type: ignore
    a2a_wrapper: A2AClientWrapper = state.get("a2a_wrapper") # type: ignore

    if not config or not isinstance(config, EtlPipelineConfig): return {"error_message": "Pipeline configuration missing/invalid."}
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper): return {"error_message": "A2AClientWrapper missing/invalid."}
    if not source_id: return {"error_message": "Initial source_identifier missing."}

    logger.info(f"NODE: {START_PIPELINE_NODE} (Project: {project_id}) - Starting ETL for Source: {source_id}")
    logger.debug(f"Configured Registry URL: {config.orchestration.registry_url}")
    logger.debug(f"A2A Wrapper Initialized: {a2a_wrapper._is_initialized}")

    # Initialize artifact references dict
    return {
        "current_step": START_PIPELINE_NODE,
        "error_message": None,
        "db_artifact_references": {}, # Initialize empty dict (REQ-ETL-ORCH-003)
        "final_load_status": None
    }

async def extract_data(state: EtlProcessingState) -> Dict[str, Any]:
    """Node to call the Data Extractor Agent."""
    try:
        config: EtlPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        source_id = state["source_identifier"]
        db_refs = state.get("db_artifact_references", {})
    except KeyError as e: return {"error_message": f"State is missing required key: {e}"}

    agent_hri = config.extractor_agent.hri
    logger.info(f"NODE: {EXTRACT_DATA_NODE} (Project: {project_id}) - Calling agent {agent_hri} for source '{source_id}'")

    try:
        input_payload = {
            "source_path": source_id, # Pass the source identifier from state
            "run_id": project_id      # Pass the pipeline run ID
        }
        # Agent returns a dict like {"artifact_db_id": 123, "rows_extracted": 20}
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)

        artifact_db_id = result_data.get("artifact_db_id")
        rows_extracted = result_data.get("rows_extracted", "N/A")

        if artifact_db_id is None or not isinstance(artifact_db_id, int):
            raise AgentProcessingError(f"Agent {agent_hri} did not return a valid integer 'artifact_db_id'. Received: {result_data}")

        db_refs["raw_data"] = artifact_db_id # Store the DB ID (REQ-ETL-ORCH-004)
        logger.info(f"Extractor agent reported {rows_extracted} rows extracted. Raw data artifact ID: {artifact_db_id}")

        return {
            "db_artifact_references": db_refs,
            "current_step": EXTRACT_DATA_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {EXTRACT_DATA_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def transform_data(state: EtlProcessingState) -> Dict[str, Any]:
    """Node to call the Data Transformer Agent."""
    try:
        config: EtlPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        db_refs = state.get("db_artifact_references", {})
        raw_data_artifact_id = db_refs.get("raw_data")
    except KeyError as e: return {"error_message": f"State is missing required key: {e}"}

    if raw_data_artifact_id is None:
        return {"error_message": "Raw data artifact ID not found in state."}

    agent_hri = config.transformer_agent.hri
    logger.info(f"NODE: {TRANSFORM_DATA_NODE} (Project: {project_id}) - Calling agent {agent_hri} for raw data artifact ID {raw_data_artifact_id}")

    try:
        input_payload = {
            "raw_data_artifact_id": raw_data_artifact_id,
            "run_id": project_id
        }
        # Agent returns {"artifact_db_id": 456, "rows_transformed": 18}
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)

        artifact_db_id = result_data.get("artifact_db_id")
        rows_transformed = result_data.get("rows_transformed", "N/A")

        if artifact_db_id is None or not isinstance(artifact_db_id, int):
            raise AgentProcessingError(f"Agent {agent_hri} did not return a valid integer 'artifact_db_id'. Received: {result_data}")

        db_refs["transformed_data"] = artifact_db_id # Store the new DB ID
        logger.info(f"Transformer agent reported {rows_transformed} rows transformed. Transformed data artifact ID: {artifact_db_id}")

        return {
            "db_artifact_references": db_refs,
            "current_step": TRANSFORM_DATA_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {TRANSFORM_DATA_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def validate_data(state: EtlProcessingState) -> Dict[str, Any]:
    """Node to call the Data Validator Agent."""
    try:
        config: EtlPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        db_refs = state.get("db_artifact_references", {})
        transformed_data_artifact_id = db_refs.get("transformed_data")
    except KeyError as e: return {"error_message": f"State is missing required key: {e}"}

    if transformed_data_artifact_id is None:
        return {"error_message": "Transformed data artifact ID not found in state."}

    agent_hri = config.validator_agent.hri
    logger.info(f"NODE: {VALIDATE_DATA_NODE} (Project: {project_id}) - Calling agent {agent_hri} for transformed data artifact ID {transformed_data_artifact_id}")

    try:
        input_payload = {
            "transformed_data_artifact_id": transformed_data_artifact_id,
            "run_id": project_id
        }
        # Agent returns {"artifact_db_id": 789, "validation_status": "Success", "invalid_rows": 0}
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)

        artifact_db_id = result_data.get("artifact_db_id")
        validation_status = result_data.get("validation_status", "Unknown")
        invalid_rows = result_data.get("invalid_rows", -1)

        if artifact_db_id is None or not isinstance(artifact_db_id, int):
            raise AgentProcessingError(f"Agent {agent_hri} did not return a valid integer 'artifact_db_id'. Received: {result_data}")

        db_refs["validation_report"] = artifact_db_id # Store the report ID
        logger.info(f"Validator agent reported status '{validation_status}' with {invalid_rows} invalid rows. Report artifact ID: {artifact_db_id}")

        # Optionally check status here and set error_message if validation failed severely
        # if validation_status == "Failed":
        #     return {"error_message": f"Data validation failed with {invalid_rows} invalid rows."}

        return {
            "db_artifact_references": db_refs,
            "current_step": VALIDATE_DATA_NODE,
            "error_message": None # Let loader decide based on report
        }
    except Exception as e:
        logger.exception(f"NODE: {VALIDATE_DATA_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def load_data(state: EtlProcessingState) -> Dict[str, Any]:
    """Node to call the Data Loader Agent."""
    try:
        config: EtlPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        db_refs = state.get("db_artifact_references", {})
        transformed_data_artifact_id = db_refs.get("transformed_data")
        validation_report_artifact_id = db_refs.get("validation_report")
    except KeyError as e: return {"error_message": f"State is missing required key: {e}"}

    if transformed_data_artifact_id is None or validation_report_artifact_id is None:
        return {"error_message": "Required artifact IDs (transformed_data, validation_report) not found in state."}

    agent_hri = config.loader_agent.hri
    logger.info(f"NODE: {LOAD_DATA_NODE} (Project: {project_id}) - Calling agent {agent_hri} with data ID {transformed_data_artifact_id} and report ID {validation_report_artifact_id}")

    try:
        input_payload = {
            "transformed_data_artifact_id": transformed_data_artifact_id,
            "validation_report_artifact_id": validation_report_artifact_id,
            "run_id": project_id
        }
        # Agent returns {"artifact_db_id": 101, "load_status": "Success", "rows_processed": 18, "rows_loaded": 18}
        result_data = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)

        artifact_db_id = result_data.get("artifact_db_id")
        load_status = result_data.get("load_status", "Failed")
        rows_processed = result_data.get("rows_processed", "N/A")
        rows_loaded = result_data.get("rows_loaded", "N/A")

        if artifact_db_id is None or not isinstance(artifact_db_id, int):
            raise AgentProcessingError(f"Agent {agent_hri} did not return a valid integer 'artifact_db_id'. Received: {result_data}")

        db_refs["load_confirmation"] = artifact_db_id # Store the confirmation ID
        logger.info(f"Loader agent reported status '{load_status}'. Processed: {rows_processed}, Loaded: {rows_loaded}. Confirmation artifact ID: {artifact_db_id}")

        final_error = None
        if load_status != "Success":
            final_error = f"Data load step finished with status: {load_status}"
            logger.error(f"Project {project_id}: {final_error}")

        return {
            "db_artifact_references": db_refs,
            "final_load_status": load_status, # Store final status
            "current_step": LOAD_DATA_NODE,
            "error_message": final_error # Set error only if load wasn't successful
        }
    except Exception as e:
        logger.exception(f"NODE: {LOAD_DATA_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def handle_pipeline_error(state: EtlProcessingState) -> Dict[str, Any]:
    """Node to handle pipeline errors."""
    error = state.get("error_message", "Unknown error")
    last_step = state.get("current_step", "Unknown step")
    project_id = state["project_id"]
    logger.error(f"ETL PIPELINE FAILED (Project: {project_id}) at step '{last_step}'. Error: {error}")
    # Update final status to reflect failure
    return {
        "error_message": f"Pipeline failed at step: {last_step}. Reason: {error}",
        "final_load_status": "Failed" # Ensure final status indicates failure
        }

logger.info("ETL pipeline node functions defined.")
