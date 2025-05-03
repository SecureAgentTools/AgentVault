import asyncio
import json
import logging
import uuid
import traceback # Keep for detailed error logging
# --- ADDED: Import urllib.parse ---
import urllib.parse
# --- END ADDED ---
from typing import Dict, Any, Optional, List

# Import AgentVault client and models
try:
    from agentvault import AgentVaultClient, KeyManager
    from agentvault.models import Message, TextPart, Artifact, AgentCard, TaskState
    from agentvault.exceptions import (
        AgentVaultError, A2AError, A2AConnectionError, A2AAuthenticationError,
        A2ARemoteAgentError, A2ATimeoutError, A2AMessageError, KeyManagementError,
        AgentCardFetchError, ConfigurationError
    )
    import httpx
    _AGENTVAULT_AVAILABLE = True
except ImportError as e:
    logging.basicConfig(level=logging.CRITICAL)
    logging.getLogger(__name__).critical(f"Failed to import core 'agentvault' library: {e}. Orchestrator cannot function.")
    traceback.print_exc()
    # Define placeholders... (placeholders remain the same as previous correct version)
    class AgentVaultClient: pass # type: ignore
    class KeyManager: pass # type: ignore
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class AgentCard: pass # type: ignore
    class TaskState: SUBMITTED="SUBMITTED"; WORKING="WORKING"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELED="CANCELED" # type: ignore
    class AgentVaultError(Exception): pass # type: ignore
    class A2AError(AgentVaultError): pass # type: ignore
    class A2AConnectionError(A2AError): pass # type: ignore
    class A2AAuthenticationError(A2AError): pass # type: ignore
    class A2ARemoteAgentError(A2AError): pass # type: ignore
    class A2ATimeoutError(A2AConnectionError): pass # type: ignore
    class A2AMessageError(A2AError): pass # type: ignore
    class KeyManagementError(AgentVaultError): pass # type: ignore
    class AgentCardFetchError(AgentVaultError): pass # type: ignore
    class ConfigurationError(AgentVaultError): pass # type: ignore
    class httpx: ConnectError = ConnectionError; ReadTimeout = TimeoutError # Placeholder # type: ignore
    _AGENTVAULT_AVAILABLE = False


logger = logging.getLogger(__name__)

# Use correct HRIs from agent cards
AGENT_HRIS = [
    "local-poc/topic-research",
    "local-poc/content-crawler",
    "local-poc/information-extraction",
    "local-poc/fact-verification",
    "local-poc/content-synthesis",
    "local-poc/editor",
    "local-poc/visualization"
]

class ResearchPipelineOrchestrator:
    """
    Orchestrates the multi-agent content research and generation pipeline.
    """
    def __init__(self, registry_url: Optional[str] = None, key_manager: Optional[KeyManager] = None):
        if not _AGENTVAULT_AVAILABLE:
            raise ImportError("AgentVault library is required but not available.")

        self.registry_url = registry_url or "http://localhost:8000"
        self.client = AgentVaultClient()
        self.key_manager = key_manager or KeyManager()
        self.agent_cards: Dict[str, AgentCard] = {}
        self.task_results: Dict[str, Any] = {}
        logger.info(f"ResearchPipelineOrchestrator initialized. Registry: {self.registry_url}")

    async def initialize(self):
        """
        Discover and cache Agent Cards for all pipeline agents using direct HRI lookup,
        URL-encoding the HRI in the path.
        """
        logger.info("Initializing orchestrator: Discovering pipeline agents via HRI lookup (URL Encoded)...")
        self.agent_cards = {}
        discovered_count = 0
        async with self.client._http_client as http_client:
            for agent_hri in AGENT_HRIS:
                logger.debug(f"Discovering agent: {agent_hri}")
                # --- MODIFIED: Use query parameter endpoint instead of path parameter ---
                # Still encode the HRI for the query parameter
                encoded_hri = urllib.parse.quote(agent_hri, safe='') # Encode '/' -> %2F
                # Use the new /by-hri endpoint with query parameter
                lookup_url = f"{self.registry_url.rstrip('/')}/api/v1/agent-cards/by-hri?hri={agent_hri}"
                logger.debug(f"Attempting lookup via query parameter URL: {lookup_url}")
                # --- END MODIFIED ---
                try:
                    response = await http_client.get(lookup_url, follow_redirects=True)
                    if response.status_code == 404:
                         logger.error(f"Agent card for HRI '{agent_hri}' not found in registry at {lookup_url}. Is the HRI correct and registered?")
                         continue
                    response.raise_for_status()
                    card_full_data = response.json()
                    card_data_dict = card_full_data.get("card_data") if isinstance(card_full_data, dict) else None
                    if not card_data_dict:
                         raise AgentCardFetchError(f"Registry response for {agent_hri} missing 'card_data' or is not a dictionary. Response: {card_full_data!r}", response_body=card_full_data)

                    agent_card = AgentCard.model_validate(card_data_dict)
                    self.agent_cards[agent_hri] = agent_card
                    logger.info(f"Successfully discovered and cached card for agent: {agent_hri} at {agent_card.url}")
                    discovered_count += 1
                except httpx.ReadTimeout as e: # Catch timeouts specifically
                    logger.error(f"Read timeout discovering agent '{agent_hri}' at {lookup_url}: {e}")
                    continue # Continue trying other agents on timeout
                except httpx.ConnectError as e:
                    logger.error(f"Connection error discovering agent '{agent_hri}' at registry {self.registry_url}: {e}")
                    raise ConfigurationError(f"Could not connect to registry at {self.registry_url}") from e
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error {e.response.status_code} discovering agent '{agent_hri}': {e.response.text}")
                    continue
                except AgentCardFetchError as e:
                    logger.error(f"Failed to fetch/parse agent card for '{agent_hri}' from registry: {e}")
                    continue
                except AgentVaultError as e:
                    logger.error(f"AgentVault error discovering agent '{agent_hri}': {e}")
                    continue
                except Exception as e:
                    logger.exception(f"Unexpected error discovering agent '{agent_hri}': {e}")
                    continue

        if len(self.agent_cards) != len(AGENT_HRIS):
            missing = set(AGENT_HRIS) - set(self.agent_cards.keys())
            logger.error(f"Failed to discover all required agents. Missing: {missing}")
            raise ConfigurationError(f"Could not discover all pipeline agents. Missing: {missing}")

        logger.info(f"Orchestrator initialization complete. Discovered {discovered_count} required agents.")

    # --- _run_agent_task and run_pipeline methods remain unchanged from the previous correct version ---
    # --- (They already use agent_hri as the key correctly) ---
    async def _run_agent_task(self, agent_hri: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to run a task on a specific agent (using HRI) and wait for completion."""
        if agent_hri not in self.agent_cards:
            raise ConfigurationError(f"Agent card for '{agent_hri}' not loaded. Run initialize() first.")

        agent_card = self.agent_cards[agent_hri]
        logger.info(f"Running task on agent: {agent_hri} ({agent_card.name})")

        try:
            input_content_str = json.dumps(input_data)
            initial_message = Message(role="user", parts=[TextPart(content=input_content_str)])
        except Exception as e:
            logger.error(f"Failed to serialize input data for agent {agent_hri}: {e}")
            raise AgentProcessingError(f"Cannot serialize input for {agent_hri}") from e

        task_id = await self.client.initiate_task(agent_card, initial_message, self.key_manager)
        logger.info(f"Task {task_id} initiated on agent {agent_hri}.")

        final_state = TaskState.SUBMITTED
        task_artifacts: Dict[str, Artifact] = {}
        final_message: Optional[str] = None

        try:
            async for event in self.client.receive_events(agent_card, task_id, self.key_manager):
                logger.debug(f"Orchestrator received event for task {task_id} ({agent_hri}): {event.event_type}")
                if event.event_type == "task_status":
                    final_state = event.data.state
                    logger.info(f"Task {task_id} ({agent_hri}) status update: {final_state}")
                    if final_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
                        logger.info(f"Task {task_id} ({agent_hri}) reached terminal state: {final_state}")
                        if final_state == TaskState.FAILED and event.data.message:
                             final_message = event.data.message
                        break
                elif event.event_type == "task_message":
                     message_data = event.data
                     if message_data.message.role == "assistant" and message_data.message.parts:
                         final_message = message_data.message.parts[0].content
                elif event.event_type == "task_artifact":
                     artifact_data = event.data
                     task_artifacts[artifact_data.artifact.id] = artifact_data.artifact
                     logger.info(f"Received artifact '{artifact_data.artifact.id}' (type: {artifact_data.artifact.type}) from task {task_id} ({agent_hri})")

        except A2AError as e:
            logger.error(f"A2A Error processing task {task_id} on agent {agent_hri}: {e}")
            raise AgentProcessingError(f"Error communicating with {agent_hri}: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error processing task {task_id} on agent {agent_hri}")
            raise AgentProcessingError(f"Unexpected error with {agent_hri}: {e}") from e

        if final_state != TaskState.COMPLETED:
            error_msg = f"Task {task_id} on agent {agent_hri} did not complete successfully. Final state: {final_state}."
            if final_message: error_msg += f" Message: {final_message}"
            logger.error(error_msg)
            raise AgentProcessingError(error_msg)

        logger.info(f"Task {task_id} ({agent_hri}) completed. Returning {len(task_artifacts)} artifacts.")
        result_data = {artifact.type: artifact.content for artifact in task_artifacts.values() if artifact.content}
        return result_data


    async def run_pipeline(self, topic: str, config: Optional[Dict[str, Any]] = None):
        """
        Executes the complete research pipeline for a given topic.
        """
        pipeline_failed = False
        project_id = "unknown"
        try:
            if not self.agent_cards:
                await self.initialize()

            if not config: config = {}
            self.task_results = {}
            project_id = str(uuid.uuid4())
            logger.info(f"Starting research pipeline run (Project ID: {project_id}) for topic: '{topic}'")

            current_input = {"topic": topic, **config}

            pipeline_steps = [
                (AGENT_HRIS[0], ["research_plan", "search_queries"]),
                (AGENT_HRIS[1], ["raw_content"]),
                (AGENT_HRIS[2], ["extracted_information", "info_by_subtopic"]),
                (AGENT_HRIS[3], ["verified_facts", "verification_report"]),
                (AGENT_HRIS[4], ["draft_article", "bibliography"]),
                (AGENT_HRIS[5], ["edited_article", "edit_suggestions"]),
                (AGENT_HRIS[6], ["viz_metadata"]),
            ]

            for step_num, (agent_hri, expected_outputs) in enumerate(pipeline_steps):
                logger.info(f"--- Pipeline Step {step_num + 1}: Running Agent '{agent_hri}' ---")
                step_result = await self._run_agent_task(agent_hri, current_input)
                logger.info(f"--- Step {step_num + 1} ({agent_hri}) completed. ---")

                self.task_results[agent_hri] = step_result
                current_input = {**current_input, **step_result}

                for output_key in expected_outputs:
                    if output_key not in step_result:
                        logger.warning(f"Expected output '{output_key}' not found in result from agent '{agent_hri}'.")

            logger.info(f"Research pipeline run (Project ID: {project_id}) completed successfully.")
            final_output = {
                "project_id": project_id,
                "topic": topic,
                "status": "COMPLETED",
                "final_article": current_input.get("edited_article", "N/A"),
                "all_step_results": self.task_results
            }
            return final_output

        except (AgentProcessingError, ConfigurationError, AgentVaultError) as e:
            logger.error(f"Pipeline failed during execution (Project ID: {project_id}): {e}")
            pipeline_failed = True
            return {
                "project_id": project_id,
                "topic": topic,
                "status": "FAILED",
                "error": str(e),
                "partial_results": self.task_results
            }
        except Exception as e:
            logger.exception(f"Unexpected error during pipeline execution (Project ID: {project_id})")
            pipeline_failed = True
            return {
                "project_id": project_id,
                "topic": topic,
                "status": "FAILED",
                "error": f"Unexpected error: {type(e).__name__}",
                "partial_results": self.task_results
            }
        finally:
            if hasattr(self, 'client') and self.client and not pipeline_failed:
                 await self.client.close()
                 logger.info("Orchestrator client closed.")
            elif pipeline_failed:
                 logger.warning("Pipeline failed, client might not be closed cleanly or might already be closed.")


# Example Usage (if run directly)
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    orchestrator = ResearchPipelineOrchestrator(registry_url="http://localhost:8000")
    final_result = {}
    try:
        await orchestrator.initialize() # Discover agents

        topic_to_research = "Impact of AI on Healthcare"
        pipeline_config = {"depth": "comprehensive", "focus_areas": ["ethics", "diagnosis"]}
        final_result = await orchestrator.run_pipeline(topic_to_research, pipeline_config)

    except ConfigurationError as e:
        print(f"\n--- Orchestrator Configuration Error ---")
        print(f"Error: {e}")
        final_result = {"status": "FAILED", "error": f"ConfigurationError: {e}"}
    except httpx.ConnectError as e:
         print(f"\n--- Orchestrator Connection Error ---")
         print(f"Error: Could not connect to registry at {orchestrator.registry_url}. Is it running?")
         print(f"Details: {e}")
         final_result = {"status": "FAILED", "error": f"ConnectError: {e}"}
    except Exception as e:
        print(f"\n--- An Unexpected Error Occurred ---")
        print(f"Error: {e}")
        print(traceback.format_exc())
        final_result = {"status": "FAILED", "error": f"UnexpectedError: {e}"}

    print("\n--- Pipeline Final Result ---")
    print(json.dumps(final_result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if not _AGENTVAULT_AVAILABLE:
        print("Error: AgentVault library not found. Cannot run orchestrator example.")
    else:
        asyncio.run(main())
