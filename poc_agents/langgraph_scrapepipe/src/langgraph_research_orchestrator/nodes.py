import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
import uuid
import os
import re
import json
from pathlib import Path

# Import the state definition and A2A wrapper
from .state import ResearchState
from .a2a_client_wrapper import A2AClientWrapper, AgentProcessingError, AGENT_HRIS
from . import local_storage_utils
from .config.pipeline_config import ResearchPipelineConfig, ensure_config_object

logger = logging.getLogger(__name__)

# --- Constants for node names ---
TOPIC_RESEARCH_NODE = "topic_research"
CONTENT_CRAWLER_NODE = "content_crawler"
INFO_EXTRACTION_NODE = "information_extraction"
FACT_VERIFICATION_NODE = "fact_verification"
CONTENT_SYNTHESIS_NODE = "content_synthesis"
EDITOR_NODE = "editor"
VISUALIZATION_NODE = "visualization"
ERROR_HANDLER_NODE = "handle_error"

# Helper function to convert any object to a dictionary
def convert_to_dict(obj):
    """Convert an object to a dictionary, regardless of its type."""
    if hasattr(obj, "model_dump"):  # Pydantic v2
        return obj.model_dump()
    elif hasattr(obj, "dict") and not isinstance(obj, dict):  # Pydantic v1 (but not a dict itself)
        return obj.dict()
    elif isinstance(obj, dict):  # Already a dict
        return obj
    else:  # Fallback to __dict__
        try:
            return obj.__dict__
        except AttributeError:
            logger.warning(f"Could not convert {type(obj)} to dictionary, using string representation")
            return {"__string_repr__": str(obj)}

# Node Functions using A2A Client Wrapper & Local Storage

async def run_topic_research(state: ResearchState, a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> Dict[str, Any]:
    """ Node for the Topic Research Agent using A2A. """
    agent_hri = AGENT_HRIS[0]
    project_id = state.get("project_id", "unknown_proj")
    logger.info(f"NODE: run_topic_research (Project: {project_id}) - Preparing A2A call.")
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
        logger.error("A2AClientWrapper instance was not provided to the node.")
        return {"error_message": "Internal orchestrator configuration error: A2A wrapper missing."}
    input_payload = { "topic": state.get("initial_topic"), "depth": state.get("initial_config", {}).get("depth", "comprehensive"), "focus_areas": state.get("initial_config", {}).get("focus_areas", []) }
    try:
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        research_plan = result_artifacts.get("research_plan")
        search_queries_data = result_artifacts.get("search_queries")
        if not research_plan: raise AgentProcessingError(f"Agent {agent_hri} did not return expected 'research_plan' artifact.")
        if not search_queries_data: raise AgentProcessingError(f"Agent {agent_hri} did not return expected 'search_queries' artifact.")
        if isinstance(search_queries_data, dict) and "search_queries" in search_queries_data:
            logger.info("Detected nested search_queries structure, extracting inner list.")
            search_queries_list = search_queries_data.get("search_queries", [])
            if not isinstance(search_queries_list, list):
                if isinstance(search_queries_list, dict):
                    logger.info(f"Converting search_queries dict to list format: {search_queries_list}")
                    converted_list = [{"subtopic": subtopic, "query": query} for subtopic, queries in search_queries_list.items() for query in (queries if isinstance(queries, list) else [str(queries)])]
                    search_queries_data = converted_list
                    logger.info(f"Successfully converted to list format with {len(converted_list)} entries")
                else: raise AgentProcessingError(f"Agent {agent_hri} returned invalid search_queries format.")
            else:
                # Convert list of strings to proper dictionary format for each item
                if search_queries_list and all(isinstance(q, str) for q in search_queries_list):
                    logger.info(f"Converting list of {len(search_queries_list)} string queries to dictionary format")
                    search_queries_data = [{"subtopic": "General", "queries": [q]} for q in search_queries_list]
                    logger.info(f"Successfully converted string queries to {len(search_queries_data)} dictionary items")
                else:
                    search_queries_data = search_queries_list
        if not isinstance(search_queries_data, list): raise AgentProcessingError(f"Agent {agent_hri} returned invalid search_queries format (not a list).")
        logger.info(f"NODE: run_topic_research completed via A2A for project {project_id}. Got {len(search_queries_data)} search query groups.")
        return { "research_plan": research_plan, "search_queries": search_queries_data, "current_step": TOPIC_RESEARCH_NODE, "error_message": None }
    except Exception as e:
        logger.exception(f"NODE: run_topic_research failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def run_content_crawler(state: ResearchState, a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> Dict[str, Any]:
    """
    Node for the Content Crawler Agent using A2A. Saves artifact even if empty,
    then checks if the *original* content was empty before returning state.
    """
    agent_hri = AGENT_HRIS[1]
    project_id = state.get("project_id", "unknown_proj")
    logger.info(f"NODE: run_content_crawler (Project: {project_id}) - Preparing A2A call.")
    local_artifact_references = state.get("local_artifact_references", {})
    file_path = None
    # --- MODIFIED: Initialize raw_content_data_to_save ---
    raw_content_data_to_save = [] # Default to empty list for saving
    crawler_produced_content = False # Flag to track if agent returned non-empty content
    raw_content_key_present = False # Flag to track if the key was returned
    # --- END MODIFIED ---

    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
        logger.error("A2AClientWrapper instance was not provided to the node.")
        return {"error_message": "Internal orchestrator configuration error: A2A wrapper missing."}

    search_queries = state.get("search_queries")
    if not search_queries:
        logger.error(f"Missing 'search_queries' in state for {agent_hri}.")
        return {"error_message": f"Missing 'search_queries' input for {agent_hri}."}

    input_payload = {"search_queries": search_queries}
    if config and hasattr(config, 'scraper'):
        input_payload["config"] = convert_to_dict(config.scraper)
        logger.info(f"Added scraper configuration to payload for {agent_hri}")

    try:
        logger.info(f"Calling {agent_hri} via A2A...")
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)

        # --- MODIFIED: Check key, assign original data, set save data ---
        raw_content_key_present = "raw_content" in result_artifacts

        if raw_content_key_present:
            raw_content_data_from_agent = result_artifacts["raw_content"]
            if raw_content_data_from_agent and isinstance(raw_content_data_from_agent, list):
                # Agent returned the key and a non-empty list
                raw_content_data_to_save = raw_content_data_from_agent
                crawler_produced_content = True
                logger.info(f"Agent {agent_hri} returned 'raw_content' artifact with {len(raw_content_data_from_agent)} items.")
            elif isinstance(raw_content_data_from_agent, list): # Key present, but list is empty
                 logger.warning(f"Agent {agent_hri} returned 'raw_content' artifact, but the content list is empty.")
                 raw_content_data_to_save = [] # Save empty list
                 crawler_produced_content = False
            else: # Key present, but content is None or wrong type
                 logger.warning(f"Agent {agent_hri} returned 'raw_content' artifact with unexpected content type: {type(raw_content_data_from_agent)}. Treating as empty.")
                 raw_content_data_to_save = [] # Save empty list
                 crawler_produced_content = False
        else:
            # Key missing - this is an agent error
            error_msg = f"Content Crawler Agent ({agent_hri}) did not return the expected 'raw_content' artifact key in its results."
            logger.error(f"Task {project_id}: {error_msg}")
            raw_content_data_to_save = {"error": error_msg} # Save error info
            crawler_produced_content = False # No usable content produced
            # We will save this error artifact, then the check below will return the error state
        # --- END MODIFIED ---

        # Determine artifact base path
        artifact_base_path = None
        if config and hasattr(config, 'orchestration'):
            artifact_base_path = config.orchestration.artifact_base_path

        # Always attempt to save the artifact
        artifact_type = "raw_content"
        logger.info(f"Saving {artifact_type} artifact (key present: {raw_content_key_present}, content has items: {crawler_produced_content})")
        file_path = await local_storage_utils.save_local_artifact(
            raw_content_data_to_save, project_id, CONTENT_CRAWLER_NODE, f"{artifact_type}.json",
            is_json=True, base_path=artifact_base_path
        )

        if not file_path:
            error_msg = f"Failed to save '{artifact_type}' artifact locally for task {project_id}"
            logger.error(error_msg)
            return { "local_artifact_references": local_artifact_references, "current_step": CONTENT_CRAWLER_NODE, "error_message": error_msg }

        local_artifact_references[artifact_type] = file_path
        logger.info(f"NODE: run_content_crawler - Saved artifact locally: {file_path}")

        # Check original content status *after* saving
        if not raw_content_key_present:
            # Error if the key was missing from the start
             error_msg = f"Content Crawler Agent ({agent_hri}) did not return the expected 'raw_content' artifact key."
             # Error already logged above
             return { "local_artifact_references": local_artifact_references, "current_step": CONTENT_CRAWLER_NODE, "error_message": error_msg }
        elif not crawler_produced_content: # Check if the original data was empty/None
            error_msg = f"Content Crawler Agent ({agent_hri}) returned no usable content."
            logger.error(f"Task {project_id}: {error_msg}")
            return { "local_artifact_references": local_artifact_references, "current_step": CONTENT_CRAWLER_NODE, "error_message": error_msg }

        # If we reach here, content key was present, content was not empty, and saving succeeded
        return {
            "local_artifact_references": local_artifact_references,
            "current_step": CONTENT_CRAWLER_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: run_content_crawler failed for project {project_id}: {e}")
        return { "local_artifact_references": local_artifact_references, "current_step": CONTENT_CRAWLER_NODE, "error_message": f"Error in {agent_hri}: {str(e)}" }


async def run_information_extraction(state: ResearchState, a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> Dict[str, Any]:
    """ Node for the Information Extraction Agent using A2A. """
    agent_hri = AGENT_HRIS[2]
    project_id = state.get("project_id", "unknown_proj")
    logger.info(f"NODE: run_information_extraction (Project: {project_id}) - Preparing A2A call.")
    logger.debug(f"Information Extraction Node processing project_id: {project_id}")
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
        logger.error("A2AClientWrapper instance was not provided to the node.")
        return {"error_message": "Internal orchestrator configuration error: A2A wrapper missing."}
    local_artifact_references = state.get("local_artifact_references", {})
    raw_content_path = local_artifact_references.get("raw_content")
    if not raw_content_path or not Path(raw_content_path).is_file():
        error_msg = f"Missing or invalid 'raw_content' local file path in state for {agent_hri}. Path: '{raw_content_path}'"
        logger.error(error_msg); return {"error_message": error_msg}
    logger.info(f"NODE: run_information_extraction - Loading input from {raw_content_path}")
    raw_content_data = await local_storage_utils.load_local_artifact(raw_content_path, is_json=True)
    if raw_content_data is None:
        error_msg = f"Failed to load 'raw_content' from {raw_content_path}"; logger.error(error_msg); return {"error_message": error_msg}
    if not raw_content_data: logger.warning(f"Loaded 'raw_content' from {raw_content_path} is empty. Proceeding with empty input for extraction.")
    input_payload = {"raw_content": raw_content_data}
    if config and hasattr(config, 'fact_extraction'):
        input_payload["config"] = convert_to_dict(config.fact_extraction); logger.info(f"Added fact extraction configuration to payload: {input_payload['config']}")
    try:
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        extracted_info_data = result_artifacts.get("extracted_information")
        info_by_subtopic_data = result_artifacts.get("info_by_subtopic")
        if extracted_info_data is None: extracted_info_data = {"extracted_facts": []}; logger.warning(f"No extracted_information received from {agent_hri}, using empty default.")
        if info_by_subtopic_data is None: info_by_subtopic_data = {"subtopics": {}}; logger.warning(f"No info_by_subtopic received from {agent_hri}, using empty default.")
        artifact_type_info = "extracted_information"; artifact_type_subtopic = "info_by_subtopic"
        artifact_base_path = config.orchestration.artifact_base_path if config and hasattr(config, 'orchestration') else None
        logger.info(f"Saving extracted_information artifact with {len(extracted_info_data.get('extracted_facts', []))} facts")
        file_path_info = await local_storage_utils.save_local_artifact(extracted_info_data, project_id, INFO_EXTRACTION_NODE, f"{artifact_type_info}.json", is_json=True, base_path=artifact_base_path)
        logger.info(f"Saving info_by_subtopic artifact with {len(info_by_subtopic_data.get('subtopics', {}))} subtopics")
        file_path_subtopic = await local_storage_utils.save_local_artifact(info_by_subtopic_data, project_id, INFO_EXTRACTION_NODE, f"{artifact_type_subtopic}.json", is_json=True, base_path=artifact_base_path)
        if not file_path_info: return {"error_message": f"Failed to save '{artifact_type_info}' artifact."}
        if not file_path_subtopic: return {"error_message": f"Failed to save '{artifact_type_subtopic}' artifact."}
        local_artifact_references[artifact_type_info] = file_path_info; local_artifact_references[artifact_type_subtopic] = file_path_subtopic
        logger.info(f"NODE: run_information_extraction completed via A2A. Saved artifacts locally.")
        return { "local_artifact_references": local_artifact_references, "current_step": INFO_EXTRACTION_NODE, "error_message": None }
    except Exception as e:
        logger.exception(f"NODE: run_information_extraction failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def run_fact_verification(state: ResearchState, a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> Dict[str, Any]:
    """ Node for the Fact Verification Agent using A2A. """
    agent_hri = AGENT_HRIS[3]
    project_id = state.get("project_id", "unknown_proj")
    logger.info(f"NODE: run_fact_verification (Project: {project_id}) - Preparing A2A call.")
    logger.debug(f"Fact Verification Node processing project_id: {project_id}")
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
        logger.error("A2AClientWrapper instance was not provided to the node.")
        return {"error_message": "Internal orchestrator configuration error: A2A wrapper missing."}
    local_artifact_references = state.get("local_artifact_references", {})
    extracted_info_path = local_artifact_references.get("extracted_information")
    if not extracted_info_path or not Path(extracted_info_path).is_file():
        error_msg = f"Missing or invalid 'extracted_information' path for {agent_hri}. Path: '{extracted_info_path}'"; logger.error(error_msg); return {"error_message": error_msg}
    logger.info(f"NODE: run_fact_verification - Loading input from {extracted_info_path}")
    extracted_info_data = await local_storage_utils.load_local_artifact(extracted_info_path, is_json=True)
    if extracted_info_data is None:
        error_msg = f"Failed to load 'extracted_information' from {extracted_info_path}"; logger.error(error_msg); return {"error_message": error_msg}
    if not extracted_info_data or not extracted_info_data.get("extracted_facts"):
        logger.warning(f"Loaded 'extracted_information' from {extracted_info_path} is empty or missing facts. Proceeding with empty input for verification.")
        extracted_info_data = {"extracted_facts": []}
    input_payload = {"extracted_information": extracted_info_data}
    if config and hasattr(config, 'fact_verification'):
        input_payload["config"] = convert_to_dict(config.fact_verification); logger.info(f"Added fact verification configuration to payload: {input_payload['config']}")
    try:
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        verified_facts_data = result_artifacts.get("verified_facts")
        verification_report_data = result_artifacts.get("verification_report")
        if verified_facts_data is None: verified_facts_data = {"verified_facts": []}; logger.warning(f"No verified_facts received from {agent_hri}, using empty default.")
        if verification_report_data is None: verification_report_data = {"issues_found": []}; logger.warning(f"No verification_report received from {agent_hri}, using empty default.")
        artifact_base_path = config.orchestration.artifact_base_path if config and hasattr(config, 'orchestration') else None
        artifact_type_facts = "verified_facts"; artifact_type_report = "verification_report"
        logger.info(f"Saving verified_facts artifact with {len(verified_facts_data.get('verified_facts', []))} facts")
        file_path_facts = await local_storage_utils.save_local_artifact(verified_facts_data, project_id, FACT_VERIFICATION_NODE, f"{artifact_type_facts}.json", is_json=True, base_path=artifact_base_path)
        logger.info(f"Saving verification_report artifact with {len(verification_report_data.get('issues_found', []))} issues")
        file_path_report = await local_storage_utils.save_local_artifact(verification_report_data, project_id, FACT_VERIFICATION_NODE, f"{artifact_type_report}.json", is_json=True, base_path=artifact_base_path)
        if not file_path_facts: return {"error_message": f"Failed to save '{artifact_type_facts}' artifact."}
        if not file_path_report: return {"error_message": f"Failed to save '{artifact_type_report}' artifact."}
        local_artifact_references[artifact_type_facts] = file_path_facts; local_artifact_references[artifact_type_report] = file_path_report
        logger.info(f"NODE: run_fact_verification completed via A2A. Saved artifacts locally.")
        return { "local_artifact_references": local_artifact_references, "current_step": FACT_VERIFICATION_NODE, "error_message": None }
    except Exception as e:
        logger.exception(f"NODE: run_fact_verification failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def run_content_synthesis(state: ResearchState, a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> Dict[str, Any]:
    """ Node for the Content Synthesis Agent using A2A. """
    agent_hri = AGENT_HRIS[4]
    project_id = state.get("project_id", "unknown_proj")
    logger.info(f"NODE: run_content_synthesis (Project: {project_id}) - Preparing A2A call.")
    logger.debug(f"Content Synthesis Node processing project_id: {project_id}")
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
        logger.error("A2AClientWrapper instance was not provided to the node.")
        return {"error_message": "Internal orchestrator configuration error: A2A wrapper missing."}
    local_artifact_references = state.get("local_artifact_references", {})
    verified_facts_path = local_artifact_references.get("verified_facts"); research_plan = state.get("research_plan")
    if not verified_facts_path or not Path(verified_facts_path).is_file():
        error_msg = f"Missing or invalid 'verified_facts' path for {agent_hri}. Path: '{verified_facts_path}'"; logger.error(error_msg); return {"error_message": error_msg}
    elif not research_plan: err = f"Missing 'research_plan' in state for {agent_hri}."; logger.error(err); return {"error_message": err}
    else:
        logger.info(f"NODE: run_content_synthesis - Loading input from {verified_facts_path}")
        verified_facts_data = await local_storage_utils.load_local_artifact(verified_facts_path, is_json=True)
        if verified_facts_data is None: error_msg = f"Failed to load 'verified_facts' from {verified_facts_path}"; logger.error(error_msg); return {"error_message": error_msg}
        if not verified_facts_data or not verified_facts_data.get("verified_facts"): logger.warning(f"Loaded 'verified_facts' from {verified_facts_path} is empty or missing facts. Proceeding with empty facts for synthesis."); verified_facts_data = {"verified_facts": []}
    input_payload = { "verified_facts": verified_facts_data, "research_plan": research_plan }
    if config and hasattr(config, 'content_synthesis'):
        input_payload["config"] = convert_to_dict(config.content_synthesis); logger.info(f"Added content synthesis configuration to payload: {input_payload['config']}")
    try:
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        draft_article_content = result_artifacts.get("draft_article"); bibliography_data = result_artifacts.get("bibliography")
        if draft_article_content is None or draft_article_content.strip() == "": draft_article_content = "# Placeholder Article\n\n*Note: Content Synthesis Agent did not return a draft article.*\n"; logger.warning(f"No draft_article received from {agent_hri}, using placeholder content.")
        if bibliography_data is None or not isinstance(bibliography_data, dict): bibliography_data = {"sources": []}; logger.warning(f"No bibliography received from {agent_hri}, using empty default.")
        elif "sources" not in bibliography_data: bibliography_data["sources"] = []; logger.warning(f"'sources' key missing in bibliography from {agent_hri}, adding empty list.")
        sources = bibliography_data.get("sources", []);
        if not isinstance(sources, list): sources = []; bibliography_data["sources"] = sources; logger.warning(f"'sources' in bibliography was not a list, replaced with empty list.")
        for i, source in enumerate(sources):
            if not isinstance(source, dict): sources[i] = {"title": "Unknown source", "url": ""}
        artifact_base_path = config.orchestration.artifact_base_path if config and hasattr(config, 'orchestration') else None
        artifact_type_draft = "draft_article"; artifact_type_bib = "bibliography"
        logger.info(f"Saving draft_article artifact with {len(draft_article_content)} characters")
        file_path_draft = await local_storage_utils.save_local_artifact(draft_article_content, project_id, CONTENT_SYNTHESIS_NODE, f"{artifact_type_draft}.md", is_json=False, base_path=artifact_base_path)
        logger.info(f"Saving bibliography artifact with {len(bibliography_data.get('sources', []))} sources")
        file_path_bib = await local_storage_utils.save_local_artifact(bibliography_data, project_id, CONTENT_SYNTHESIS_NODE, f"{artifact_type_bib}.json", is_json=True, base_path=artifact_base_path)
        if not file_path_draft: return {"error_message": f"Failed to save '{artifact_type_draft}' artifact."}
        if not file_path_bib: return {"error_message": f"Failed to save '{artifact_type_bib}' artifact."}
        local_artifact_references[artifact_type_draft] = file_path_draft; local_artifact_references[artifact_type_bib] = file_path_bib
        logger.info(f"NODE: run_content_synthesis completed via A2A. Saved artifacts locally.")
        return { "local_artifact_references": local_artifact_references, "current_step": CONTENT_SYNTHESIS_NODE, "error_message": None }
    except Exception as e:
        logger.exception(f"NODE: run_content_synthesis failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def run_editor(state: ResearchState, a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> Dict[str, Any]:
    """ Node for the Editor Agent using A2A. """
    agent_hri = AGENT_HRIS[5]
    project_id = state.get("project_id", "unknown_proj")
    logger.info(f"NODE: run_editor (Project: {project_id}) - Preparing A2A call.")
    logger.debug(f"Editor Node processing project_id: {project_id}")
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
        logger.error("A2AClientWrapper instance was not provided to the node.")
        return {"error_message": "Internal orchestrator configuration error: A2A wrapper missing."}
    local_artifact_references = state.get("local_artifact_references", {})
    draft_article_path = local_artifact_references.get("draft_article")
    if not draft_article_path or not Path(draft_article_path).is_file():
        error_msg = f"Missing or invalid 'draft_article' path for {agent_hri}. Path: '{draft_article_path}'"; logger.error(error_msg)
        draft_article_content = ("# Placeholder Article\n\n*Note: Could not load draft article for editing.*\n")
    else:
        logger.info(f"NODE: run_editor - Loading input from {draft_article_path}")
        draft_article_content = await local_storage_utils.load_local_artifact(draft_article_path, is_json=False)
        if draft_article_content is None: logger.warning(f"Failed to load 'draft_article' from {draft_article_path}, using placeholder"); draft_article_content = "# Placeholder Article\n\n*Note: Failed to load draft article content.*\n"
        elif not draft_article_content.strip(): logger.warning(f"Loaded 'draft_article' from {draft_article_path} is empty. Proceeding with empty input for editor.")
    input_payload = {"draft_article": draft_article_content}
    if config and hasattr(config, 'editor'):
        input_payload["config"] = convert_to_dict(config.editor); logger.info(f"Added editor configuration to payload: {input_payload['config']}")
    try:
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        edited_article_content = result_artifacts.get("edited_article"); edit_suggestions_data = result_artifacts.get("edit_suggestions")
        if not edited_article_content or not isinstance(edited_article_content, str) or edited_article_content.strip() == "": logger.warning(f"Empty or invalid edited_article from {agent_hri}, using draft with notice"); edited_article_content = draft_article_content + "\n\n*[Editor Processing Note: No additional edits were made to this draft.]*"
        if edit_suggestions_data is None or not isinstance(edit_suggestions_data, dict): logger.warning(f"Invalid edit_suggestions from {agent_hri}, creating default structure"); edit_suggestions_data = {"suggestions": [{"type": "note", "message": "No edit suggestions were generated."}]}
        elif "suggestions" not in edit_suggestions_data: edit_suggestions_data["suggestions"] = [{"type": "note", "message": "No structured suggestions were generated."}]
        elif not isinstance(edit_suggestions_data["suggestions"], list): edit_suggestions_data["suggestions"] = [{"type": "note", "message": "Suggestions data was not in the expected format."}]
        artifact_base_path = config.orchestration.artifact_base_path if config and hasattr(config, 'orchestration') else None
        artifact_type_edited = "edited_article"; artifact_type_suggestions = "edit_suggestions"
        logger.info(f"Saving edited_article artifact with {len(edited_article_content)} characters")
        file_path_edited = await local_storage_utils.save_local_artifact(edited_article_content, project_id, EDITOR_NODE, f"{artifact_type_edited}.md", is_json=False, base_path=artifact_base_path)
        logger.info(f"Saving edit_suggestions artifact with {len(edit_suggestions_data.get('suggestions', []))} suggestions")
        file_path_suggestions = await local_storage_utils.save_local_artifact(edit_suggestions_data, project_id, EDITOR_NODE, f"{artifact_type_suggestions}.json", is_json=True, base_path=artifact_base_path)
        if not file_path_edited: return {"error_message": f"Failed to save '{artifact_type_edited}' artifact."}
        if not file_path_suggestions: return {"error_message": f"Failed to save '{artifact_type_suggestions}' artifact."}
        local_artifact_references[artifact_type_edited] = file_path_edited; local_artifact_references[artifact_type_suggestions] = file_path_suggestions
        logger.info(f"NODE: run_editor completed via A2A. Saved artifacts locally.")
        return { "local_artifact_references": local_artifact_references, "final_article_local_path": file_path_edited, "current_step": EDITOR_NODE, "error_message": None }
    except Exception as e:
        logger.exception(f"NODE: run_editor failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def run_visualization(state: ResearchState, a2a_wrapper: A2AClientWrapper, config: Optional[ResearchPipelineConfig] = None) -> Dict[str, Any]:
    """ Node for the Visualization Agent using A2A. """
    agent_hri = AGENT_HRIS[6]
    project_id = state.get("project_id", "unknown_proj")
    logger.info(f"NODE: run_visualization (Project: {project_id}) - Preparing A2A call.")
    logger.debug(f"Visualization Node processing project_id: {project_id}")
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
        logger.error("A2AClientWrapper instance was not provided to the node.")
        return {"error_message": "Internal orchestrator configuration error: A2A wrapper missing."}
    local_artifact_references = state.get("local_artifact_references", {})
    verified_facts_path = local_artifact_references.get("verified_facts")
    if not verified_facts_path or not Path(verified_facts_path).is_file():
        error_msg = f"Missing or invalid 'verified_facts' path for {agent_hri}. Path: '{verified_facts_path}'"; logger.error(error_msg); return {"error_message": error_msg}
    logger.info(f"NODE: run_visualization - Loading input from {verified_facts_path}")
    verified_facts_data = await local_storage_utils.load_local_artifact(verified_facts_path, is_json=True)
    if verified_facts_data is None: error_msg = f"Failed to load 'verified_facts' from {verified_facts_path}"; logger.error(error_msg); return {"error_message": error_msg}
    if not verified_facts_data or not verified_facts_data.get("verified_facts"): logger.warning(f"Loaded 'verified_facts' from {verified_facts_path} is empty or missing facts. Proceeding with empty input for visualization."); verified_facts_data = {"verified_facts": []}
    input_payload = {"verified_facts": verified_facts_data}
    if config and hasattr(config, 'visualization'):
        input_payload["config"] = convert_to_dict(config.visualization); logger.info(f"Added visualization configuration to payload: {input_payload['config']}")
    try:
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        viz_metadata = result_artifacts.get("viz_metadata")
        if viz_metadata is None: viz_metadata = { "visualizations": [], "message": "No visualizations could be generated.", "generated_at": project_id }; logger.warning(f"Agent {agent_hri} did not return 'viz_metadata' artifact. Created placeholder.")
        if "visualizations" not in viz_metadata: viz_metadata["visualizations"] = []; logger.warning(f"'visualizations' key missing in viz_metadata from {agent_hri}, adding empty list.")
        artifact_base_path = config.orchestration.artifact_base_path if config and hasattr(config, 'orchestration') else None
        artifact_type = "viz_metadata"
        logger.info(f"Saving viz_metadata artifact with {len(viz_metadata.get('visualizations', []))} visualizations")
        file_path = await local_storage_utils.save_local_artifact(viz_metadata, project_id, VISUALIZATION_NODE, f"{artifact_type}.json", is_json=True, base_path=artifact_base_path)
        if not file_path: return {"error_message": f"Failed to save '{artifact_type}' artifact."}
        local_artifact_references[artifact_type] = file_path
        logger.info(f"NODE: run_visualization completed via A2A. Saved artifact locally: {file_path}")
        return { "local_artifact_references": local_artifact_references, "final_visualization_local_path": file_path, "current_step": VISUALIZATION_NODE, "error_message": None }
    except Exception as e:
        logger.exception(f"NODE: run_visualization failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def handle_pipeline_error(state: ResearchState, config: Optional[Union[Dict[str, Any], ResearchPipelineConfig]] = None) -> Dict[str, Any]:
    """ Node to handle pipeline errors. """
    error = state.get("error_message", "Unknown error"); last_step = state.get("current_step", "Unknown step"); project_id = state.get("project_id", "unknown_proj")
    logger.error(f"PIPELINE FAILED (Project: {project_id}) at step '{last_step}'. Error: {error}")
    config_obj = ensure_config_object(config)
    artifact_base_path = None
    if config_obj and hasattr(config_obj, 'orchestration') and hasattr(config_obj.orchestration, 'artifact_base_path'):
        artifact_base_path = config_obj.orchestration.artifact_base_path; logger.info(f"Pipeline was using configuration with artifact base path: {artifact_base_path}")
    if artifact_base_path is None: logger.info("No artifact base path found in configuration")
    return {"error_message": f"Pipeline failed at step: {last_step}. Reason: {error}"}

logger.info("Node functions updated to use configuration parameters.")
