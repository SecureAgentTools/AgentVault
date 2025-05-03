import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional, List

# Import AgentVault client and models
try:
    from agentvault import AgentVaultClient, KeyManager
    from agentvault.models import Message, TextPart, Artifact, AgentCard, TaskState # Added TaskState
    # --- MODIFIED: Import exceptions explicitly ---
    from agentvault.exceptions import AgentVaultError, A2AError, AgentCardFetchError, ConfigurationError
    import httpx # Import httpx to catch its specific exceptions
    # --- END MODIFIED ---
    _AGENTVAULT_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).critical("Failed to import core 'agentvault' library. Orchestrator cannot function.")
    # Define placeholders to allow script loading but prevent execution
    class AgentVaultClient: pass # type: ignore
    class KeyManager: pass # type: ignore
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class AgentCard: pass # type: ignore
    class TaskState: SUBMITTED="SUBMITTED"; WORKING="WORKING"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELED="CANCELED" # type: ignore
    class AgentVaultError(Exception): pass # type: ignore
    class A2AError(AgentVaultError): pass # type: ignore
    class AgentCardFetchError(AgentVaultError): pass # type: ignore
    class ConfigurationError(AgentVaultError): pass # type: ignore
    class httpx: ConnectError = ConnectionError # Placeholder # type: ignore
    _AGENTVAULT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Agent IDs as defined in the plan
AGENT_IDS = [
    "topic-research-agent",
    "content-crawler-agent",
    "information-extraction-agent",
    "fact-verification-agent",
    "content-synthesis-agent",
    "editor-agent",
    "visualization-agent"
]

class ResearchPipelineOrchestrator:
    """
    Orchestrates the multi-agent content research and generation pipeline.
    """
    def __init__(self, registry_url: Optional[str] = None, key_manager: Optional[KeyManager] = None):
        if not _AGENTVAULT_AVAILABLE:
            raise ImportError("AgentVault library is required but not available.")

        # Use provided registry URL or default (adjust default as needed)
        self.registry_url = registry_url or "http://localhost:8000" # Default registry
        self.client = AgentVaultClient() # Client for A2A calls
        self.key_manager = key_manager or KeyManager() # Use provided or default KeyManager
        self.agent_cards: Dict[str, AgentCard] = {} # Cache for agent cards
        self.task_results: Dict[str, Any] = {} # Store results/artifacts from each step
        logger.info(f"ResearchPipelineOrchestrator initialized. Registry: {self.registry_url}")

    async def initialize(self):
        """
        Discover and cache Agent Cards for all pipeline agents from the registry.
        Handles connection errors gracefully for each agent lookup.
        """
        logger.info("Initializing orchestrator: Discovering pipeline agents...")
        self.agent_cards = {} # Clear cache on re-initialization
        discovered_count = 0
        # --- MODIFIED: Use the client's context manager OUTSIDE the loop ---
        async with self.client._http_client as http_client:
            for agent_id in AGENT_IDS:
                logger.debug(f"Discovering agent: {agent_id}")
                try:
                    # Assuming registry client is part of AgentVaultClient or needs separate init
                    # For now, construct lookup URL manually (adjust based on actual registry API)
                    lookup_url = f"{self.registry_url.rstrip('/')}/api/v1/agent-cards/id/{agent_id}"
                    logger.debug(f"Attempting direct lookup via URL: {lookup_url}")

                    # Use the http_client obtained from the context manager
                    response = await http_client.get(lookup_url, follow_redirects=True)
                    response.raise_for_status() # Check for HTTP errors
                    card_full_data = response.json()
                    # --- MODIFIED: Handle potential missing 'card_data' key ---
                    card_data_dict = card_full_data.get("card_data") if isinstance(card_full_data, dict) else None
                    if not card_data_dict:
                         raise AgentCardFetchError(f"Registry response for {agent_id} missing 'card_data' or is not a dictionary. Response: {card_full_data!r}")
                    # --- END MODIFIED ---
                    # Parse the nested card data
                    agent_card = AgentCard.model_validate(card_data_dict)
                    self.agent_cards[agent_id] = agent_card
                    logger.info(f"Successfully discovered and cached card for agent: {agent_id} at {agent_card.url}")
                    discovered_count += 1
                # --- MODIFIED: Catch specific connection error ---
                except httpx.ConnectError as e:
                    logger.error(f"Connection error discovering agent '{agent_id}' at registry {self.registry_url}: {e}")
                # --- END MODIFIED ---
                except AgentCardFetchError as e:
                    logger.error(f"Failed to fetch agent card for '{agent_id}' from registry: {e}")
                except AgentVaultError as e:
                    logger.error(f"AgentVault error discovering agent '{agent_id}': {e}")
                except Exception as e:
                    logger.exception(f"Unexpected error discovering agent '{agent_id}': {e}")
        # --- END MODIFIED ---

        if len(self.agent_cards) != len(AGENT_IDS):
            missing = set(AGENT_IDS) - set(self.agent_cards.keys())
            logger.error(f"Failed to discover all required agents. Missing: {missing}")
            # --- MODIFIED: Use imported ConfigurationError ---
            raise ConfigurationError(f"Could not discover all pipeline agents. Missing: {missing}")
            # --- END MODIFIED ---
        logger.info(f"Orchestrator initialization complete. Discovered {discovered_count} agents.")

    async def _run_agent_task(self, agent_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to run a task on a specific agent and wait for completion."""
        if agent_id not in self.agent_cards:
            raise ConfigurationError(f"Agent card for '{agent_id}' not loaded. Run initialize() first.")

        agent_card = self.agent_cards[agent_id]
        logger.info(f"Running task on agent: {agent_id} ({agent_card.name})")

        # Prepare message (assuming input_data is the primary content)
        # Convert dict to JSON string if agent expects text part primarily
        try:
            # --- MODIFIED: Ensure complex objects are handled by Pydantic/JSON ---
            # Let Pydantic handle serialization within initiate_task if possible,
            # otherwise, explicitly dump complex parts.
            # For this POC, we assume agents expect a JSON string in the first part.
            input_content_str = json.dumps(input_data)
            initial_message = Message(role="user", parts=[TextPart(content=input_content_str)])
            # --- END MODIFIED ---
        except Exception as e:
            logger.error(f"Failed to serialize input data for agent {agent_id}: {e}")
            raise AgentProcessingError(f"Cannot serialize input for {agent_id}") from e

        task_id = await self.client.initiate_task(agent_card, initial_message, self.key_manager)
        logger.info(f"Task {task_id} initiated on agent {agent_id}.")

        # Wait for completion and gather artifacts/messages
        final_state = TaskState.SUBMITTED
        task_artifacts: Dict[str, Artifact] = {}
        final_message: Optional[str] = None

        try:
            # --- MODIFIED: Use receive_events for richer event data ---
            async for event in self.client.receive_events(agent_card, task_id, self.key_manager):
                logger.debug(f"Orchestrator received event for task {task_id} ({agent_id}): {event.event_type}")
                if event.event_type == "task_status":
                    final_state = event.data.state # Assuming event.data is TaskStatusUpdateEvent model
                    logger.info(f"Task {task_id} ({agent_id}) status update: {final_state}")
                    if final_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
                        logger.info(f"Task {task_id} ({agent_id}) reached terminal state: {final_state}")
                        if final_state == TaskState.FAILED and event.data.message:
                             final_message = event.data.message # Capture failure message
                        break
                elif event.event_type == "task_message":
                     message_data = event.data # Assuming event.data is TaskMessageEvent model
                     if message_data.message.role == "assistant" and message_data.message.parts:
                         # Capture the last assistant message content
                         final_message = message_data.message.parts[0].content
                elif event.event_type == "task_artifact":
                     artifact_data = event.data # Assuming event.data is TaskArtifactEvent model
                     task_artifacts[artifact_data.artifact.id] = artifact_data.artifact
                     logger.info(f"Received artifact '{artifact_data.artifact.id}' (type: {artifact_data.artifact.type}) from task {task_id} ({agent_id})")
            # --- END MODIFIED ---

        except A2AError as e:
            logger.error(f"A2A Error processing task {task_id} on agent {agent_id}: {e}")
            raise AgentProcessingError(f"Error communicating with {agent_id}: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error processing task {task_id} on agent {agent_id}")
            raise AgentProcessingError(f"Unexpected error with {agent_id}: {e}") from e

        if final_state != TaskState.COMPLETED:
            error_msg = f"Task {task_id} on agent {agent_id} did not complete successfully. Final state: {final_state}."
            if final_message: error_msg += f" Message: {final_message}"
            logger.error(error_msg)
            raise AgentProcessingError(error_msg)

        logger.info(f"Task {task_id} ({agent_id}) completed. Returning {len(task_artifacts)} artifacts.")
        # Return collected artifacts (or potentially the final message)
        # For this POC, we'll return the content of the artifacts directly
        # In a real scenario, you might return artifact IDs/URLs or specific content.
        result_data = {artifact.type: artifact.content for artifact in task_artifacts.values() if artifact.content}
        return result_data


    async def run_pipeline(self, topic: str, config: Optional[Dict[str, Any]] = None):
        """
        Executes the complete research pipeline for a given topic.
        """
        pipeline_failed = False # Flag to indicate failure
        try:
            if not self.agent_cards:
                await self.initialize() # Ensure agents are discovered

            if not config: config = {}
            self.task_results = {} # Reset results for this run
            project_id = str(uuid.uuid4()) # Unique ID for this pipeline run
            logger.info(f"Starting research pipeline run (Project ID: {project_id}) for topic: '{topic}'")

            current_input = {"topic": topic, **config}

            pipeline_steps = [
                ("topic-research-agent", ["research_plan", "search_queries"]),
                ("content-crawler-agent", ["raw_content"]), # Ignoring embeddings for now
                ("information-extraction-agent", ["extracted_information", "info_by_subtopic"]),
                ("fact-verification-agent", ["verified_facts", "verification_report"]),
                ("content-synthesis-agent", ["draft_article", "bibliography"]),
                ("editor-agent", ["edited_article", "edit_suggestions"]),
                ("visualization-agent", ["viz_metadata"]), # Assuming viz artifacts are handled separately
            ]

            for step_num, (agent_id, expected_outputs) in enumerate(pipeline_steps):
                logger.info(f"--- Pipeline Step {step_num + 1}: Running Agent '{agent_id}' ---")
                step_result = await self._run_agent_task(agent_id, current_input)
                logger.info(f"--- Step {step_num + 1} ({agent_id}) completed. ---")

                # Store results and prepare input for the next step
                self.task_results[agent_id] = step_result
                current_input = {**current_input, **step_result} # Merge results for next input

                # Basic check if expected outputs were produced (based on keys)
                for output_key in expected_outputs:
                    if output_key not in step_result:
                        logger.warning(f"Expected output '{output_key}' not found in result from agent '{agent_id}'.")

            logger.info(f"Research pipeline run (Project ID: {project_id}) completed successfully.")
            # Return the final combined results (or specific final artifacts)
            final_output = {
                "project_id": project_id,
                "topic": topic,
                "status": "COMPLETED", # Added status
                "final_article": current_input.get("edited_article", "N/A"),
                "all_step_results": self.task_results # Include intermediate results if needed
            }
            return final_output

        except (AgentProcessingError, ConfigurationError, AgentVaultError) as e:
            logger.error(f"Pipeline failed during execution (Project ID: {project_id}): {e}")
            pipeline_failed = True
            # Return partial results or error status
            return {
                "project_id": project_id if 'project_id' in locals() else 'unknown',
                "topic": topic,
                "status": "FAILED",
                "error": str(e),
                "partial_results": self.task_results
            }
        except Exception as e:
            logger.exception(f"Unexpected error during pipeline execution (Project ID: {project_id if 'project_id' in locals() else 'unknown'})")
            pipeline_failed = True
            return {
                "project_id": project_id if 'project_id' in locals() else 'unknown',
                "topic": topic,
                "status": "FAILED",
                "error": f"Unexpected error: {type(e).__name__}",
                "partial_results": self.task_results
            }
        finally:
            # --- MODIFIED: Close client only if it was successfully initialized ---
            if hasattr(self, 'client') and self.client and not pipeline_failed:
                 await self.client.close()
                 logger.info("Orchestrator client closed.")
            elif pipeline_failed:
                 logger.warning("Pipeline failed, client might not be closed cleanly or might already be closed.")
            # --- END MODIFIED ---

# Example Usage (if run directly)
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Assuming registry is running locally and agents are registered or discoverable via direct lookup
    orchestrator = ResearchPipelineOrchestrator(registry_url="http://localhost:8000")
    final_result = {}
    try:
        # Initialize (discover agents) - This might fail if registry isn't running
        await orchestrator.initialize()

        # Run the pipeline
        topic_to_research = "Impact of AI on Healthcare"
        pipeline_config = {"depth": "comprehensive", "focus_areas": ["ethics", "diagnosis"]}
        final_result = await orchestrator.run_pipeline(topic_to_research, pipeline_config)

    # --- MODIFIED: Catch imported ConfigurationError ---
    except ConfigurationError as e:
        print(f"\n--- Orchestrator Configuration Error ---")
        print(f"Error: {e}")
        final_result = {"status": "FAILED", "error": f"ConfigurationError: {e}"}
    # --- END MODIFIED ---
    except httpx.ConnectError as e:
         print(f"\n--- Orchestrator Connection Error ---")
         print(f"Error: Could not connect to registry at {orchestrator.registry_url}. Is it running?")
         print(f"Details: {e}")
         final_result = {"status": "FAILED", "error": f"ConnectError: {e}"}
    except Exception as e:
        print(f"\n--- An Unexpected Error Occurred ---")
        print(f"Error: {e}")
        print(traceback.format_exc()) # Print full traceback for unexpected errors
        final_result = {"status": "FAILED", "error": f"UnexpectedError: {e}"}

    print("\n--- Pipeline Final Result ---")
    # Use ensure_ascii=False for potentially non-ASCII characters in LLM output
    print(json.dumps(final_result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    # Check if library is available before running example
    if not _AGENTVAULT_AVAILABLE:
        print("Error: AgentVault library not found. Cannot run orchestrator example.")
    else:
        asyncio.run(main())
