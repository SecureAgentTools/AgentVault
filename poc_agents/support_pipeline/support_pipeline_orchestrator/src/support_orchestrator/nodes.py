import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
import uuid
import os
import json
from pathlib import Path

# Import state definition, models, config, and utilities for this pipeline
from support_orchestrator.state_definition import TicketProcessingState
from support_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
from support_orchestrator import local_storage_utils
from support_orchestrator.config import SupportPipelineConfig
from support_orchestrator.models import (
    TicketAnalysis, KnowledgeBaseArticle, CustomerHistorySummary,
    TicketAnalysisArtifactContent, KBSearchResultsArtifactContent,
    CustomerHistoryArtifactContent, SuggestedResponseArtifactContent
)

logger = logging.getLogger(__name__)

# --- Constants for node names (REQ-SUP-ORCH-004) ---
START_PIPELINE_NODE = "start_ticket_processing"
ANALYZE_TICKET_NODE = "analyze_ticket"
FETCH_KB_NODE = "fetch_kb_articles"
FETCH_HISTORY_NODE = "fetch_customer_history"
AGGREGATE_CONTEXT_NODE = "aggregate_response_context"
SUGGEST_RESPONSE_NODE = "suggest_response"
ERROR_HANDLER_NODE = "handle_pipeline_error" # Reusing name for consistency

# --- Helper to get artifact path ---
def _get_artifact_path(state: TicketProcessingState, artifact_type: str) -> Optional[str]:
    """Safely gets an artifact path from the state's local references."""
    return state.get("local_artifact_references", {}).get(artifact_type)

# --- Node Functions (REQ-SUP-ORCH-004) ---

async def start_ticket_processing(state: TicketProcessingState) -> Dict[str, Any]:
    """Initial node: Logs start, validates essential state components."""
    project_id = state["project_id"]
    ticket_text = state["ticket_text"]
    customer_id = state["customer_identifier"]
    config: SupportPipelineConfig = state.get("pipeline_config") # type: ignore
    a2a_wrapper: A2AClientWrapper = state.get("a2a_wrapper") # type: ignore

    if not config or not isinstance(config, SupportPipelineConfig):
         return {"error_message": "Pipeline configuration missing or invalid in state."}
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
         return {"error_message": "A2AClientWrapper instance missing or invalid in state."}
    if not ticket_text or not customer_id:
         return {"error_message": "Initial ticket_text or customer_identifier missing in state."}

    logger.info(f"NODE: {START_PIPELINE_NODE} (Project: {project_id}) - Starting pipeline for Customer: {customer_id}")
    logger.debug(f"Ticket Text (start): {ticket_text[:100]}...")
    logger.debug(f"Configured Registry URL: {config.orchestration.registry_url}")
    logger.debug(f"A2A Wrapper Initialized: {a2a_wrapper._is_initialized}")

    # Return updates needed for the state
    return {
        "current_step": START_PIPELINE_NODE,
        "error_message": None,
        "local_artifact_references": state.get("local_artifact_references", {}) # Ensure it exists
    }

async def analyze_ticket(state: TicketProcessingState) -> Dict[str, Any]:
    """Node to call the Ticket Analyzer Agent."""
    try:
        config: SupportPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        ticket_text = state["ticket_text"]
        customer_id = state["customer_identifier"]
        local_refs = state.get("local_artifact_references", {})
    except KeyError as e:
        return {"error_message": f"State is missing required key: {e}"}

    agent_hri = config.ticket_analyzer_agent.hri
    logger.info(f"NODE: {ANALYZE_TICKET_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        input_payload = {
            "ticket_text": ticket_text,
            "customer_identifier": customer_id
        }
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        # Content is expected within the 'ticket_analysis' key of the returned dict
        analysis_content = result_artifacts.get("ticket_analysis")

        if analysis_content is None:
            logger.warning(f"Agent {agent_hri} did not return 'ticket_analysis' artifact content. Using default empty analysis.")
            # Create a default based on the model
            analysis_data = TicketAnalysis(summary="Analysis failed or missing.", category="Unknown", sentiment="Neutral")
            analysis_content = TicketAnalysisArtifactContent(ticket_analysis=analysis_data).model_dump(mode='json')

        # Save the artifact content locally (REQ-SUP-ORCH-006)
        file_path = await local_storage_utils.save_local_artifact(
            analysis_content, project_id, ANALYZE_TICKET_NODE, "ticket_analysis.json",
            is_json=True, base_path=artifact_base_path
        )
        if not file_path: raise AgentProcessingError("Failed to save ticket_analysis artifact locally.")
        local_refs["ticket_analysis"] = file_path # Store path using simple key

        return {
            "local_artifact_references": local_refs,
            "current_step": ANALYZE_TICKET_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {ANALYZE_TICKET_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def fetch_kb_articles(state: TicketProcessingState) -> Dict[str, Any]:
    """Node to call the Knowledge Base Search Agent."""
    try:
        config: SupportPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        local_refs = state.get("local_artifact_references", {})
        # Load analysis from previous step's artifact
        analysis_path = _get_artifact_path(state, "ticket_analysis")
        if not analysis_path: return {"error_message": "Ticket analysis artifact path not found."}
        analysis_artifact_content = await local_storage_utils.load_local_artifact(analysis_path, is_json=True)
        if not analysis_artifact_content or not isinstance(analysis_artifact_content, dict): return {"error_message": "Failed to load ticket analysis artifact."}
        ticket_analysis = TicketAnalysisArtifactContent.model_validate(analysis_artifact_content).ticket_analysis
    except (KeyError, ValidationError, FileNotFoundError, TypeError) as e: # type: ignore
        return {"error_message": f"State or prerequisite artifact missing/invalid for KB search: {e}"}

    agent_hri = config.kb_search_agent.hri
    logger.info(f"NODE: {FETCH_KB_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        # Use category and maybe keywords from analysis
        input_payload = {
            "category": ticket_analysis.category,
            # Example: derive keywords from summary or entities if needed
            # "keywords": ticket_analysis.summary.split()[:5]
        }
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        kb_results_content = result_artifacts.get("kb_results")

        if kb_results_content is None:
            logger.warning(f"Agent {agent_hri} did not return 'kb_results' artifact content. Using empty list.")
            kb_results_content = KBSearchResultsArtifactContent(kb_results=[]).model_dump(mode='json')

        # Save artifact (REQ-SUP-ORCH-006)
        file_path = await local_storage_utils.save_local_artifact(
            kb_results_content, project_id, FETCH_KB_NODE, "kb_results.json",
            is_json=True, base_path=artifact_base_path
        )
        if not file_path: raise AgentProcessingError("Failed to save kb_results artifact locally.")
        local_refs["kb_results"] = file_path

        return {
            "local_artifact_references": local_refs,
            "current_step": FETCH_KB_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {FETCH_KB_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def fetch_customer_history(state: TicketProcessingState) -> Dict[str, Any]:
    """Node to call the Customer History Agent."""
    try:
        config: SupportPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        customer_id = state["customer_identifier"]
        local_refs = state.get("local_artifact_references", {})
    except KeyError as e:
        return {"error_message": f"State is missing required key: {e}"}

    agent_hri = config.customer_history_agent.hri
    logger.info(f"NODE: {FETCH_HISTORY_NODE} (Project: {project_id}) - Calling agent {agent_hri} for customer {customer_id}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        input_payload = {"customer_identifier": customer_id}
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        history_content = result_artifacts.get("customer_history")

        if history_content is None:
            logger.warning(f"Agent {agent_hri} did not return 'customer_history' artifact content. Using default empty history.")
            history_data = CustomerHistorySummary(customer_identifier=customer_id, status="Unknown")
            history_content = CustomerHistoryArtifactContent(customer_history=history_data).model_dump(mode='json')

        # Save artifact (REQ-SUP-ORCH-006)
        file_path = await local_storage_utils.save_local_artifact(
            history_content, project_id, FETCH_HISTORY_NODE, "customer_history.json",
            is_json=True, base_path=artifact_base_path
        )
        if not file_path: raise AgentProcessingError("Failed to save customer_history artifact locally.")
        local_refs["customer_history"] = file_path

        return {
            "local_artifact_references": local_refs,
            "current_step": FETCH_HISTORY_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {FETCH_HISTORY_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def aggregate_response_context(state: TicketProcessingState) -> Dict[str, Any]:
    """
    Node to load results from previous steps (analysis, kb, history) into state.
    REQ-SUP-ORCH-004, REQ-SUP-ORCH-007
    """
    project_id = state["project_id"]
    logger.info(f"NODE: {AGGREGATE_CONTEXT_NODE} (Project: {project_id}) - Aggregating context for response generation.")
    local_refs = state.get("local_artifact_references", {})
    analysis: Optional[TicketAnalysis] = None
    kb_articles: Optional[List[KnowledgeBaseArticle]] = None
    history: Optional[CustomerHistorySummary] = None
    error_messages = []

    # Load Ticket Analysis
    analysis_path = _get_artifact_path(state, "ticket_analysis")
    if analysis_path:
        content = await local_storage_utils.load_local_artifact(analysis_path, is_json=True)
        if content and isinstance(content, dict):
            try: analysis = TicketAnalysisArtifactContent.model_validate(content).ticket_analysis; logger.info("Loaded ticket analysis.")
            except Exception as e: error_messages.append(f"Failed validation: ticket_analysis ({e})")
        else: error_messages.append("Failed load: ticket_analysis")
    else: error_messages.append("Missing path: ticket_analysis")

    # Load KB Results
    kb_path = _get_artifact_path(state, "kb_results")
    if kb_path:
        content = await local_storage_utils.load_local_artifact(kb_path, is_json=True)
        if content and isinstance(content, dict):
            try: kb_articles = KBSearchResultsArtifactContent.model_validate(content).kb_results; logger.info(f"Loaded {len(kb_articles)} KB articles.")
            except Exception as e: error_messages.append(f"Failed validation: kb_results ({e})")
        else: error_messages.append("Failed load: kb_results")
    else: error_messages.append("Missing path: kb_results") # Non-critical? Maybe log warning instead.

    # Load Customer History
    history_path = _get_artifact_path(state, "customer_history")
    if history_path:
        content = await local_storage_utils.load_local_artifact(history_path, is_json=True)
        if content and isinstance(content, dict):
            try: history = CustomerHistoryArtifactContent.model_validate(content).customer_history; logger.info("Loaded customer history.")
            except Exception as e: error_messages.append(f"Failed validation: customer_history ({e})")
        else: error_messages.append("Failed load: customer_history")
    else: error_messages.append("Missing path: customer_history") # Non-critical? Maybe log warning instead.

    # Check for critical missing data
    if not analysis:
        logger.error("CRITICAL FAILURE: Ticket analysis data could not be loaded or validated.")
        error_messages.append("Critical failure: Ticket analysis missing.")

    update: Dict[str, Any] = {
        "ticket_analysis": analysis,
        "kb_results": kb_articles or [], # Default to empty list if load failed
        "customer_history": history, # Can be None if load failed
        "current_step": AGGREGATE_CONTEXT_NODE
    }

    if error_messages:
        update["error_message"] = "; ".join(error_messages)
        logger.error(f"Errors during aggregation for project {project_id}: {update['error_message']}")
    else:
        update["error_message"] = None
        logger.info(f"Successfully aggregated context for project {project_id}.")

    return update

async def suggest_response(state: TicketProcessingState) -> Dict[str, Any]:
    """Node to call the Response Suggestion Agent."""
    try:
        config: SupportPipelineConfig = state["pipeline_config"] # type: ignore
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # type: ignore
        project_id = state["project_id"]
        local_refs = state.get("local_artifact_references", {})
        # Get aggregated data from state
        ticket_analysis = state.get("ticket_analysis")
        kb_results = state.get("kb_results")
        customer_history = state.get("customer_history")
    except KeyError as e:
        return {"error_message": f"State is missing required key: {e}"}

    # Check if critical data is present after aggregation
    if not ticket_analysis:
        return {"error_message": "Cannot suggest response: Ticket analysis data is missing."}

    agent_hri = config.response_suggester_agent.hri
    logger.info(f"NODE: {SUGGEST_RESPONSE_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        # Prepare payload for the suggestion agent
        input_payload = {
            "ticket_analysis": ticket_analysis.model_dump(mode='json'),
            # Ensure kb_results is a list of dicts, even if empty
            "kb_results": [kb.model_dump(mode='json') for kb in kb_results] if kb_results else [],
            # Pass history only if available
            "customer_history": customer_history.model_dump(mode='json') if customer_history else None,
        }

        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        # Agent is expected to return artifact type 'suggested_response' with string content
        response_content = result_artifacts.get("suggested_response") # Direct content expected

        if response_content is None or not isinstance(response_content, str):
            logger.warning(f"Agent {agent_hri} did not return valid 'suggested_response' string content. Using placeholder.")
            response_content = "Placeholder: Could not generate suggested response."

        # Save artifact (REQ-SUP-ORCH-006) - Save as text
        file_path = await local_storage_utils.save_local_artifact(
            response_content, project_id, SUGGEST_RESPONSE_NODE, "suggested_response.txt",
            is_json=False, base_path=artifact_base_path # Save as raw text
        )
        if not file_path: raise AgentProcessingError("Failed to save suggested_response artifact locally.")
        local_refs["suggested_response"] = file_path

        # Update state with the actual response string for potential immediate use
        return {
            "local_artifact_references": local_refs,
            "suggested_response": response_content,
            "current_step": SUGGEST_RESPONSE_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {SUGGEST_RESPONSE_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}


async def handle_pipeline_error(state: TicketProcessingState) -> Dict[str, Any]:
    """Node to handle pipeline errors (identical logic to e-commerce)."""
    error = state.get("error_message", "Unknown error")
    last_step = state.get("current_step", "Unknown step")
    project_id = state["project_id"]
    logger.error(f"PIPELINE FAILED (Project: {project_id}) at step '{last_step}'. Error: {error}")
    # Potentially add logic here to notify someone or save final error state
    return {"error_message": f"Pipeline failed at step: {last_step}. Reason: {error}"}

logger.info("Support pipeline node functions defined.")
