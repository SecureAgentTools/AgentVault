#!/usr/bin/env python
print("SCRIPT STARTING...") # Correct indentation (no leading spaces)

"""
Direct agent loader that bypasses the registry completely.
This loads agent cards from local files and handles tasks correctly.
"""

import httpx
import json
import logging
import uuid
import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
import traceback # For detailed error logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import core AgentVault modules
try:
    from agentvault import AgentVaultClient, KeyManager
    from agentvault.models import Message, TextPart, DataPart, Artifact, AgentCard, TaskState
    from agentvault.exceptions import (
        AgentVaultError, A2AError, A2AConnectionError, A2AAuthenticationError,
        A2ARemoteAgentError, A2ATimeoutError, A2AMessageError, KeyManagementError,
        AgentCardFetchError, ConfigurationError
    )
    _AGENTVAULT_AVAILABLE = True
except ImportError as e:
    # Log critical error even before full logging setup might be complete
    print(f"CRITICAL: Failed to import core 'agentvault' library: {e}. Orchestrator cannot function.", file=sys.stderr)
    logger.critical(f"Failed to import core 'agentvault' library: {e}. Orchestrator cannot function.")
    _AGENTVAULT_AVAILABLE = False
    sys.exit(1) # Exit immediately if core library fails

# Define custom exception for agent processing errors
class AgentProcessingError(Exception):
    """Raised when an error occurs during agent task processing."""
    pass

# Agent HRIs list
AGENT_HRIS = [
    "local-poc/topic-research",
    "local-poc/content-crawler",
    "local-poc/information-extraction",
    "local-poc/fact-verification",
    "local-poc/content-synthesis",
    "local-poc/editor",
    "local-poc/visualization"
]

class DirectAgentOrchestrator:
    """
    Orchestrator that loads agent cards directly from files and runs the pipeline.
    """
    def __init__(self, registry_url: Optional[str] = None):
        if not _AGENTVAULT_AVAILABLE:
            raise ImportError("AgentVault library is required but not available.")

        self.registry_url = registry_url or "http://localhost:8000"
        self.client = AgentVaultClient()
        self.key_manager = KeyManager()
        self.agent_cards: Dict[str, AgentCard] = {}
        self.task_results: Dict[str, Any] = {}
        logger.info(f"DirectAgentOrchestrator initialized. Registry: {self.registry_url}")

    async def initialize(self):
        """
        Load agent cards directly from local files instead of from the registry.
        """
        logger.info("Initializing orchestrator: Loading agent cards directly from files...")
        self.agent_cards = {}
        discovered_count = 0

        base_dir = Path("agent_cards")
        if not base_dir.exists() or not base_dir.is_dir():
            raise ConfigurationError(f"Agent cards directory not found: {base_dir}")

        for agent_hri in AGENT_HRIS:
            logger.info(f"Loading agent card for: {agent_hri}")

            # Convert hri path component to directory name (local-poc/topic-research → topic_research)
            agent_type = agent_hri.split('/')[-1].replace('-', '_')
            agent_dir = base_dir / agent_type
            card_path = agent_dir / "agent-card.json"

            if not card_path.exists():
                logger.error(f"Agent card file not found: {card_path}")
                continue

            try:
                with open(card_path, 'r', encoding='utf-8') as f:
                    card_data = json.load(f)

                # Validate the card data
                agent_card = AgentCard.model_validate(card_data)
                self.agent_cards[agent_hri] = agent_card
                logger.info(f"Successfully loaded card for agent: {agent_hri} at {agent_card.url}")
                discovered_count += 1
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse agent card JSON from {card_path}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error loading agent card from {card_path}: {e}")
                continue

        if len(self.agent_cards) != len(AGENT_HRIS):
            missing = set(AGENT_HRIS) - set(self.agent_cards.keys())
            logger.error(f"Failed to load all required agents. Missing: {missing}")
            raise ConfigurationError(f"Could not load all pipeline agents. Missing: {missing}")

        logger.info(f"DirectAgentOrchestrator initialization complete. Loaded {discovered_count} required agents.")

    async def _run_agent_task(self, agent_hri: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Helper to run a task on a specific agent (using HRI) and wait for completion."""
        if agent_hri not in self.agent_cards:
            raise ConfigurationError(f"Agent card for '{agent_hri}' not loaded. Run initialize() first.")

        agent_card = self.agent_cards[agent_hri] # Use the original loaded AgentCard object
        logger.info(f"Running task on agent: {agent_hri} ({agent_card.name})")

        try:
            # For content-synthesis, reduce payload size if it's too large
            if agent_hri == "local-poc/content-synthesis":
                logger.info(f"Preparing special handling for content-synthesis agent with optimized input")
                # Reduce the size of verified_facts if present and too large
                if "verified_facts" in input_data and isinstance(input_data["verified_facts"], dict) and "verified_facts" in input_data["verified_facts"]:
                    verified_facts = input_data["verified_facts"]["verified_facts"]
                    if isinstance(verified_facts, list) and len(verified_facts) > 100:
                        logger.warning(f"Large verified_facts payload detected ({len(verified_facts)} items). Trimming to top 100 items.")
                        # Sort by confidence and relevance scores if available
                        try:
                            verified_facts.sort(key=lambda x: x.get("confidence_score", 0) * x.get("relevance_score", 0), reverse=True)
                            input_data["verified_facts"]["verified_facts"] = verified_facts[:100]
                            logger.info(f"Trimmed verified_facts to top 100 items by confidence*relevance score")
                        except Exception as sort_err:
                            logger.warning(f"Error while trying to sort and trim verified_facts: {sort_err}")
                
                # Try to optimize raw_content too if present
                if "raw_content" in input_data and isinstance(input_data["raw_content"], list) and len(input_data["raw_content"]) > 20:
                    logger.warning(f"Large raw_content payload detected ({len(input_data['raw_content'])} items). Trimming to 20 items.")
                    input_data["raw_content"] = input_data["raw_content"][:20]
                
            # Send input_data as a DataPart
            initial_message = Message(role="user", parts=[DataPart(content=input_data)])
        except Exception as e:
            logger.error(f"Failed to create initial message for agent {agent_hri}: {e}")
            raise AgentProcessingError(f"Cannot create initial message for {agent_hri}") from e

        # Check if agent is reachable before initiating task
        try:
            url_str = str(agent_card.url)
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Use a GET health check to the /health endpoint instead of tasks/get with a non-existent ID
                try:
                    # Get the base URL by removing the endpoint part
                    base_url = url_str.rsplit('/a2a', 1)[0]
                    health_url = f"{base_url}/health"
                    logger.info(f"Checking agent health at {health_url}")
                    response = await client.get(
                        health_url,
                        follow_redirects=True
                    )
                    if response.status_code < 500:
                        logger.info(f"Agent {agent_hri} at {url_str} is accessible (status: {response.status_code})")
                    else:
                        logger.error(f"Agent {agent_hri} at {url_str} returned server error: {response.status_code}")
                        raise AgentProcessingError(f"Agent {agent_hri} returned server error: {response.status_code}")
                except httpx.RequestError as e:
                    logger.error(f"Connection error to agent {agent_hri}: {e}")
                    raise AgentProcessingError(f"Cannot connect to agent {agent_hri} at {url_str}: {e}")
        except Exception as e:
            logger.error(f"Error checking agent {agent_hri} availability: {e}")
            raise AgentProcessingError(f"Error checking availability of agent {agent_hri}: {e}")

        # For content-synthesis agent, let's log the input size to debug payload issues
        if agent_hri == "local-poc/content-synthesis":
            try:
                payload_str = json.dumps(input_data)
                payload_size_kb = len(payload_str) / 1024
                logger.info(f"Content synthesis input payload size: {payload_size_kb:.2f} KB")
                if payload_size_kb > 5000:  # 5MB warning threshold
                    logger.warning(f"Very large payload detected: {payload_size_kb:.2f} KB. This may cause performance issues.")
            except Exception as size_err:
                logger.error(f"Error calculating payload size: {size_err}")
                
        # Initiate the task on the agent
        try:
            # Pass original agent_card directly
            task_id = await self.client.initiate_task(agent_card, initial_message, self.key_manager)
            logger.info(f"Task {task_id} initiated on agent {agent_hri}.")
        except Exception as e:
            logger.error(f"Failed to initiate task on agent {agent_hri}: {e}")
            logger.error(traceback.format_exc())
            raise AgentProcessingError(f"Failed to initiate task on {agent_hri}: {e}")

        # Track state and artifacts
        task_artifacts: Dict[str, Artifact] = {}
        final_message: Optional[str] = None

        # Correctly listen for SSE events using known client methods
        try:
            # Try different event streaming methods
            event_method = getattr(self.client, "receive_events", None)
            if not event_method:
                event_method = getattr(self.client, "subscribe_to_events", None)
            if not event_method:
                event_method = getattr(self.client, "receive_task_events", None)
                
            # HANDLE EVENT STREAMING OR POLLING
            if event_method:  # If we have an event streaming method
                # Use event streaming
                logger.info(f"Using event streaming for agent {agent_hri}")
                final_state = TaskState.SUBMITTED  # Initialize with default
                async for event in event_method(agent_card, task_id, self.key_manager):
                    logger.debug(f"Received event for task {task_id} ({agent_hri}): {event.event_type}")
                    if event.event_type == "task_status":
                        final_state = event.data.state
                        logger.info(f"Task {task_id} ({agent_hri}) status update: {final_state}")
                        if final_state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
                            logger.info(f"Task {task_id} ({agent_hri}) reached terminal state: {final_state}")
                            if final_state == TaskState.FAILED and hasattr(event.data, 'message') and event.data.message:
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
            else:  # No event streaming method available, use polling
                # Special handling for content-synthesis agent
                if agent_hri == "local-poc/content-synthesis":
                    logger.warning(f"No streaming event method found for content synthesis agent. Using special polling.")
                    # Initialize status variables
                    status = await self.client.get_task_status(agent_card, task_id, self.key_manager)
                    current_state = status.state
                    final_state = current_state
                    logger.info(f"Content synthesis task {task_id} initial state: {current_state}")

                    # Give the content synthesis agent even more time
                    max_retries = 180  # 3 minutes at 15s polling interval = 45 minutes total timeout
                    retry_count = 0
                    terminal_states = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]
                    
                    # Special polling loop for content synthesis with longer wait times
                    while current_state not in terminal_states:
                        # Use longer wait times for this resource-intensive agent
                        wait_time = min(15 + (retry_count // 5), 30)  # Start at 15s, max 30s
                        logger.info(f"Content synthesis agent task {task_id}: Waiting {wait_time}s for processing (poll {retry_count}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        retry_count += 1
                        if retry_count > max_retries:
                            logger.error(f"Content synthesis polling timeout for task {task_id}")
                            raise AgentProcessingError(f"Polling timeout for content synthesis task")
                        
                        try:
                            # Add explicit timeout for the API call itself
                            async with httpx.AsyncClient(timeout=30.0) as client:
                                # Construct the correct JSON-RPC request manually for robustness
                                response = await client.post(
                                    url_str,
                                    json={
                                        "jsonrpc": "2.0",
                                        "method": "tasks/get",
                                        "id": str(uuid.uuid4()),
                                        "params": {"id": task_id}
                                    },
                                    headers={"Content-Type": "application/json"}
                                )
                                if response.status_code == 200:
                                    try:
                                        result = response.json()
                                        if "result" in result and "state" in result["result"]:
                                            state_value = result["result"]["state"]
                                            # Convert string to enum if needed
                                            if isinstance(state_value, str) and hasattr(TaskState, state_value):
                                                current_state = getattr(TaskState, state_value)
                                            else:
                                                current_state = state_value
                                            # Update final state
                                            final_state = current_state
                                            logger.info(f"Content synthesis task {task_id} status update: {current_state}")
                                        
                                            # Extract artifacts if completed
                                            if current_state == TaskState.COMPLETED and "artifacts" in result["result"]:
                                                for artifact_data in result["result"]["artifacts"]:
                                                    logger.info(f"Found artifact in response: {artifact_data.get('id')}")
                                                    try:
                                                        # Create artifact object
                                                        artifact = Artifact.model_validate(artifact_data)
                                                        task_artifacts[artifact.id] = artifact
                                                        logger.info(f"Extracted artifact '{artifact.id}' (type: {artifact.type}) directly from status response")
                                                    except Exception as artifact_err:
                                                        logger.error(f"Error parsing artifact: {artifact_err}")
                                        else:
                                            logger.warning(f"Unexpected response format: {result}")
                                    except Exception as json_err:
                                        logger.error(f"Error parsing JSON response: {json_err}")
                                else:
                                    logger.error(f"Error status: {response.status_code}, {response.text}")
                        except Exception as req_err:
                            logger.error(f"Error during custom polling request: {req_err}")
                            # Don't fail the task for a single polling error
                            continue
                        
                        if current_state in terminal_states:
                            break
                else:  # Standard polling for other agents
                    logger.warning(f"No streaming event method found in client for {agent_hri}. Using standard polling.")
                    # Polling logic - Initialize status and state variables
                    logger.debug(f"Initial status check for task {task_id}")
                    # Make sure we're using consistent JSON-RPC parameter format 
                    status = await self.client.get_task_status(agent_card, task_id, self.key_manager)
                    current_state = status.state
                    # Initialize final_state with current state instead of default SUBMITTED
                    final_state = current_state  
                    logger.info(f"Task {task_id} ({agent_hri}) status: {current_state}")
                    
                    max_retries = 120  # Increased from 60 to 120 for slower systems
                    retry_count = 0
                    terminal_states = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]
                    
                    # Polling loop with exponential backoff
                    while current_state not in terminal_states:
                        # Gradually increase polling delay to reduce load on the system
                        wait_time = min(5 + (retry_count // 10), 15) # Start at 5s, max 15s
                        await asyncio.sleep(wait_time)
                        retry_count += 1
                        if retry_count > max_retries:
                            logger.error(f"Polling timeout for task {task_id} on agent {agent_hri}")
                            raise AgentProcessingError(f"Polling timeout for task on {agent_hri}")
                        
                        logger.debug(f"Sending task status request for {task_id} with params: id={task_id}")
                        # Explicitly use task_id as the ID parameter name in the JSON-RPC request
                        status = await self.client.get_task_status(agent_card, task_id, self.key_manager)
                        current_state = status.state
                        # Always update final_state when we get a new state
                        final_state = current_state
                        logger.info(f"Task {task_id} ({agent_hri}) status update: {current_state}")
                        
                        if current_state in terminal_states:
                            # Safely access potential message attribute
                            final_message = getattr(status, 'message', None) or getattr(status, 'status_message', '')
                            break

                    # Re-fetch status after polling loop to ensure we have the latest state
                    try:
                        logger.debug(f"Re-fetching final status for task {task_id}")
                        # Make sure we're using correct parameter ID structure
                        status = await self.client.get_task_status(agent_card, task_id, self.key_manager)
                        final_state = status.state
                        logger.debug(f"Re-fetched final state after polling loop: {final_state}")
                    except Exception as e:
                        logger.error(f"Error re-fetching final status after polling: {e}")
                    
                    # Debug logging to verify state
                    logger.debug(f"Before final check - final_state: {final_state!r}, type: {type(final_state).__name__}")

                    if final_state == TaskState.COMPLETED:
                        logger.info(f"Polling detected completion for task {task_id}. Extracting results from final status object.")
                        # Extract messages from the final status object
                        if status.messages:
                            for msg in status.messages:
                                if msg.role == "assistant" and msg.parts:
                                    final_message = msg.parts[0].content # Capture last assistant message
                        else:
                            logger.warning(f"No messages found in final status object for task {task_id}")

                        # Extract artifacts from the final status object
                        if status.artifacts:
                            for artifact in status.artifacts:
                                task_artifacts[artifact.id] = artifact
                                logger.info(f"Extracted artifact '{artifact.id}' (type: {artifact.type}) from final status of task {task_id} ({agent_hri})")
                        else:
                             logger.warning(f"No artifacts found in final status object for task {task_id}")
        except A2AError as e:
            logger.error(f"A2A Error processing task {task_id} on agent {agent_hri}: {e}")
            raise AgentProcessingError(f"Error communicating with {agent_hri}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error processing task {task_id} on agent {agent_hri}: {e}")
            raise AgentProcessingError(f"Unexpected error with {agent_hri}: {e}")

        # Check final state and return results
        if final_state != TaskState.COMPLETED:
            error_msg = f"Task {task_id} on agent {agent_hri} did not complete successfully. Final state: {final_state}."
            if final_message:
                error_msg += f" Message: {final_message}"
            logger.error(error_msg)
            raise AgentProcessingError(error_msg)

        logger.info(f"Task {task_id} ({agent_hri}) completed. Returning {len(task_artifacts)} artifacts.")
        # Construct result_data from task_artifacts
        result_data = {artifact.type: artifact.content for artifact in task_artifacts.values() if artifact.content}
        return result_data

    async def run_pipeline(self, topic: str, config: Optional[Dict[str, Any]] = None, checkpoint_after_each_step: bool = True):
        """
        Executes the complete research pipeline for a given topic.
        """
        pipeline_failed = False
        project_id = "unknown"
        try:
            if not self.agent_cards:
                await self.initialize()

            if not config:
                config = {}

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

            # Create checkpoint directory if it doesn't exist
            checkpoint_dir = Path("pipeline_checkpoints")
            if checkpoint_after_each_step and not checkpoint_dir.exists():
                checkpoint_dir.mkdir(exist_ok=True)
                
            for step_num, (agent_hri, expected_outputs) in enumerate(pipeline_steps):
                # Add retries for each agent step
                max_step_retries = 2
                step_retry = 0
                
                # Create path to potential checkpoint file
                checkpoint_file = checkpoint_dir / f"{project_id}_step_{step_num}.json" if checkpoint_after_each_step else None
                
                # Try to load from checkpoint first if available
                if checkpoint_after_each_step and checkpoint_file.exists():
                    try:
                        with open(checkpoint_file, 'r', encoding='utf-8') as f:
                            step_result = json.load(f)
                        logger.info(f"--- Pipeline Step {step_num + 1}: Resuming from checkpoint for '{agent_hri}' ---")
                        success = True
                    except Exception as e:
                        logger.warning(f"Failed to load checkpoint for step {step_num + 1}, will run agent: {e}")
                        success = False
                else:
                    success = False
                    
                # If no checkpoint or loading failed, run the agent
                if not success:
                    logger.info(f"--- Pipeline Step {step_num + 1}: Running Agent '{agent_hri}' ---")
                    while step_retry <= max_step_retries:
                        try:
                            step_result = await self._run_agent_task(agent_hri, current_input)
                            success = True
                            break  # Success, exit retry loop
                        except Exception as e:
                            step_retry += 1
                            if step_retry > max_step_retries:
                                logger.error(f"Failed to run step {step_num + 1} after {max_step_retries + 1} attempts")
                                raise  # Re-raise to exit pipeline
                            logger.warning(f"Step {step_num + 1} attempt {step_retry} failed: {e}. Retrying...")
                            await asyncio.sleep(10 * step_retry)  # Increasing backoff
                
                logger.info(f"--- Step {step_num + 1} ({agent_hri}) completed. ---")
                
                # Save checkpoint after successful step
                if checkpoint_after_each_step and success:
                    try:
                        with open(checkpoint_file, 'w', encoding='utf-8') as f:
                            json.dump(step_result, f, indent=2, ensure_ascii=False)
                        logger.info(f"Checkpoint saved for step {step_num + 1}")
                    except Exception as e:
                        logger.warning(f"Failed to save checkpoint for step {step_num + 1}: {e}")

                self.task_results[agent_hri] = step_result
                current_input = {**current_input, **step_result}

                for output_key in expected_outputs:
                    if output_key not in step_result:
                        logger.warning(f"Expected output '{output_key}' not found in result from agent '{agent_hri}'.")
                        
                # Add a pause between steps to let system resources recover
                if step_num < len(pipeline_steps) - 1:  # If not the last step
                    logger.info(f"Pausing for 3 seconds before next step to manage system resources...")
                    await asyncio.sleep(3)

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
                "error": f"Unexpected error: {str(e)}",
                "partial_results": self.task_results
            }
        finally:
            if hasattr(self, 'client') and self.client and not pipeline_failed:
                await self.client.close()
                logger.info("Orchestrator client closed.")
            elif pipeline_failed:
                logger.warning("Pipeline failed, client might not be closed cleanly or might already be closed.")

async def main():
    """Run the research pipeline with direct agent loading."""
    orchestrator = None
    max_retries = 3 # Increased from 0 to 3 for more resilience
    retry_count = 0

    while retry_count <= max_retries:
        try:
            # Create a fresh orchestrator for each attempt
            orchestrator = DirectAgentOrchestrator(registry_url="http://localhost:8000")

            # Initialize the orchestrator
            await orchestrator.initialize()

            # Use the new topic and config
            topic_to_research = "The Convergence of AI, IoT, and Edge Computing for Future Smart City Infrastructure"
            pipeline_config = {
                "depth": "comprehensive",
                "focus_areas": [
                    "Real-time Traffic Management",
                    "Predictive Grid Maintenance",
                    "Edge-Based Public Safety Analytics",
                    "Data Privacy Challenges in Integrated Systems"
                ]
            }

            logger.info(f"Running pipeline for topic: {topic_to_research}")
            final_result = await orchestrator.run_pipeline(topic_to_research, pipeline_config, checkpoint_after_each_step=True)

            print("\n--- Pipeline Final Result ---")
            print(json.dumps(final_result, indent=2, ensure_ascii=False))

            # If we got here without errors, break out of retry loop
            break

        except ConfigurationError as e:
            print(f"\n--- Orchestrator Configuration Error ---")
            print(f"Error: {e}")
            final_result = {"status": "FAILED", "error": f"ConfigurationError: {e}"}
            print(json.dumps(final_result, indent=2, ensure_ascii=False))
            break  # Configuration errors are fatal, don't retry

        except Exception as e:
            retry_count += 1
            error_trace = traceback.format_exc()
            logger.error(f"Error (attempt {retry_count}/{max_retries+1}): {e}\n{error_trace}")

            if retry_count <= max_retries:
                backoff_time = min(5 * (2 ** retry_count), 60) # Exponential backoff with 60s max
                logger.info(f"Retrying in {backoff_time} seconds (attempt {retry_count}/{max_retries+1})...")
                await asyncio.sleep(backoff_time)
            else:
                print(f"\n--- An Unexpected Error Occurred (after {max_retries+1} attempts) ---")
                print(f"Error: {e}")
                final_result = {"status": "FAILED", "error": f"UnexpectedError: {str(e)}"}
                print(json.dumps(final_result, indent=2, ensure_ascii=False))
        finally:
            # Clean up the orchestrator if it was created
            if orchestrator and hasattr(orchestrator, 'client'):
                try:
                    await orchestrator.client.close()
                except:
                    pass

if __name__ == "__main__":
    # Check _AGENTVAULT_AVAILABLE
    if not _AGENTVAULT_AVAILABLE:
        print("CRITICAL: AgentVault library failed to import. Cannot run.", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main())
