import logging
import asyncio
import json
import os
import datetime
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
import uuid

import httpx
from fastapi import BackgroundTasks # Keep this import

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import (
    BriefingInput, BriefingOutput, DynamicsDataPayload, ExternalDataPayload, AccountAnalysisPayload
)

# --- Direct Import of Core Models ---
from agentvault.models import (
    Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent # Import specific event types
)

# --- TaskStateEnum assignment ---
TaskStateEnum = TaskState

logger = logging.getLogger(__name__)
AGENT_ID = "local-poc/account-briefing-generator"

# --- LLM Configuration ---
LLM_API_URL = os.environ.get("LLM_API_URL")
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "default-model")

llm_config_valid = bool(LLM_API_URL)
if not llm_config_valid:
    logger.error("LLM_API_URL environment variable not set.")

# --- Helper function for SSE Formatting ---
def _agent_format_sse_event_bytes(event: A2AEvent) -> Optional[bytes]:
    """Helper within the agent to format an A2AEvent into SSE message bytes."""
    event_type: Optional[str] = None
    if isinstance(event, TaskStatusUpdateEvent): event_type = "task_status"
    elif isinstance(event, TaskMessageEvent): event_type = "task_message"
    elif isinstance(event, TaskArtifactUpdateEvent): event_type = "task_artifact"

    if event_type is None:
        logging.getLogger(__name__).warning(f"Cannot format unknown event type: {type(event)}")
        return None
    try:
        if hasattr(event, 'model_dump_json'):
             json_data = event.model_dump_json(by_alias=True)
        elif hasattr(event, 'dict'):
             json_data = json.dumps(event.dict(by_alias=True))
        elif isinstance(event, dict):
             json_data = json.dumps(event)
        else:
             json_data = json.dumps(str(event))
        sse_message = f"event: {event_type}\ndata: {json_data}\n\n"
        return sse_message.encode("utf-8")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to serialize or format SSE event (type: {event_type}): {e}", exc_info=True)
        return None
# --- End Helper ---

class BriefingGeneratorAgent(BaseA2AAgent):
    """Generates account briefings using LLM."""
    def __init__(self):
        super().__init__(agent_metadata={"name": "Account Briefing Generator Agent (LLM)"})
        self.http_client = httpx.AsyncClient(timeout=120.0)
        self.task_store: Optional[Any] = None
        self.logger = logger # Assign logger
        logger.info(f"Briefing Generator Agent initialized. LLM URL: {LLM_API_URL}")

    async def _call_llm(self, prompt: str) -> str:
        self.logger.info("=== ATTEMPTING TO CALL LLM ===")
        self.logger.info(f"LLM URL: {LLM_API_URL}")
        self.logger.info(f"LLM MODEL: {LLM_MODEL_NAME}")

        if not llm_config_valid:
            self.logger.error("LLM_API_URL not configured - FAILING!")
            raise ConfigurationError("LLM_API_URL not configured.")

        headers = {"Content-Type": "application/json"}
        if LLM_API_KEY and LLM_API_KEY.lower() not in ["none", "no_key", "lm-studio", "ollama"]:
             headers["Authorization"] = f"Bearer {LLM_API_KEY}"
        else:
            self.logger.info("Using LM Studio or Ollama configuration - no auth token needed")
        self.logger.info(f"Using headers: {headers}")

        payload = {
            "model": LLM_MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 500
        }
        self.logger.info(f"Payload (brief): {payload['model']}, prompt length: {len(prompt)}")

        try:
            self.logger.info(f"Sending request to LLM: {LLM_API_URL}")
            llm_endpoint = LLM_API_URL.rstrip('/') + "/chat/completions"
            self.logger.info(f"Full LLM endpoint URL: {llm_endpoint}")

            self.logger.info("Making HTTP request to LLM...")
            response = await self.http_client.post(llm_endpoint, headers=headers, json=payload, timeout=30.0)
            self.logger.info(f"Received response: status {response.status_code}")
            response.raise_for_status()

            result = response.json()
            self.logger.info(f"Parsed JSON response, keys: {list(result.keys())}")

            if result.get("choices") and isinstance(result["choices"], list) and len(result["choices"]) > 0:
                message = result["choices"][0].get("message")
                if message and isinstance(message, dict):
                    content = message.get("content")
                    if content and isinstance(content, str):
                        self.logger.info(f"LLM generated content: {len(content)} chars")
                        return content.strip()
            self.logger.warning(f"Could not extract valid content from LLM response: {result}")

            if "answer" in result: return result.get("answer", "ERROR: Unknown response format")
            if "response" in result: return result.get("response", "ERROR: Unknown response format")
            if "content" in result: return result.get("content", "ERROR: Unknown response format")

            return "ERROR: Could not extract valid response from LLM - please check if LM Studio is running"
        except httpx.RequestError as e:
            self.logger.error(f"Network error calling LLM API at {LLM_API_URL}: {e}", exc_info=True)
            return f"ERROR: Network error contacting LLM: {e} - please make sure LM Studio is running on host"
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error {e.response.status_code} from LLM API: {e.response.text}", exc_info=True)
            return f"ERROR: HTTP error {e.response.status_code} from LLM API"
        except Exception as e:
            self.logger.exception(f"Unexpected error during LLM call: {e}")
            return f"ERROR: Unexpected error calling LLM: {e}"

    def _format_briefing_prompt(self, dyn: DynamicsDataPayload, ext: ExternalDataPayload, analysis: AccountAnalysisPayload) -> str:
        prompt = "Generate a concise briefing for an Account Manager about the following account:\n\n## Account Information:\n"
        if dyn.account: prompt += f"- **Name:** {dyn.account.name}\n" + (f"- **Industry:** {dyn.account.industry}\n" if dyn.account.industry else "") + (f"- **Status:** {dyn.account.status}\n" if dyn.account.status else "") + (f"- **Website:** {dyn.account.website}\n" if dyn.account.website else "")
        else: prompt += "- No basic account details found.\n"
        if dyn.contacts: prompt += "\n## Key Contacts:\n"; prompt += "".join([f"- {c.name}" + (f" ({c.role})" if c.role else "") + "\n" for c in dyn.contacts[:2]])
        if dyn.opportunities: prompt += "\n## Recent Opportunities:\n"; prompt += "".join([f"- {o.name}: Stage={o.stage or 'N/A'}, Est. Revenue=${o.revenue or 'N/A'}\n" for o in dyn.opportunities[:3]])
        else: prompt += "\n## Recent Opportunities:\n- None found.\n"
        if dyn.cases: prompt += "\n## Open/Recent Cases:\n"; prompt += "".join([f"- {c.subject or 'N/A'}: Priority={c.priority or 'N/A'}, Status={c.status or 'N/A'}\n" for c in dyn.cases[:2]])
        else: prompt += "\n## Open/Recent Cases:\n- None found.\n"
        if ext.news or ext.intent_signals: prompt += "\n## External Signals:\n"; prompt += (f"- **Recent News:** {'; '.join(ext.news[:2])}\n" if ext.news else "") + (f"- **Intent Signals:** {'; '.join(ext.intent_signals[:3])}\n" if ext.intent_signals else "") + (f"- **Detected Tech:** {', '.join(ext.technologies)}\n" if ext.technologies else "")
        prompt += "\n## Account Health Analysis:\n"; prompt += f"- **Risk Level:** {analysis.risk_level}\n- **Opportunity Level:** {analysis.opportunity_level}\n- **Engagement Level:** {analysis.engagement_level}\n- **Summary:** {analysis.analysis_summary}\n"
        prompt += "\n## Suggested Next Steps (1-2 concise actions):\n- [LLM to suggest next steps based on the above context]"
        return prompt

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str:
        if task_id: raise AgentProcessingError(f"Briefing agent does not support continuing task {task_id}")
        new_task_id = f"d365-brief-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received briefing generation request.")
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        await self.task_store.create_task(new_task_id)
        input_content = None
        # Use direct import now
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart): input_content = part.content; break
        if not isinstance(input_content, dict):
             await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart dict.")
             raise AgentProcessingError("Invalid input: Expected DataPart dict.")

        # Give clients time to establish SSE connections before starting processing
        await asyncio.sleep(0.5)

        # Use asyncio.create_task for concurrency
        self.logger.info(f"Task {new_task_id}: Scheduling process_task via asyncio.create_task (Ignoring BackgroundTasks).")
        asyncio.create_task(self.process_task(new_task_id, input_content))
        return new_task_id

    async def process_task(self, task_id: str, content: Dict[str, Any]):
        if not self.task_store: self.logger.error(f"Task {task_id}: Task store missing."); return
        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started.")
        final_state = TaskStateEnum.FAILED; error_message = "Failed briefing generation."; completion_message = error_message; output_data = None
        try:
            if not llm_config_valid:
                self.logger.error(f"Task {task_id}: LLM not configured.")
                error_message = "LLM_API_URL not configured."
                raise ConfigurationError("LLM_API_URL not configured.") # Raise error to stop processing

            try:
                input_data = BriefingInput.model_validate(content)
                account_name = input_data.dynamics_data.account.name if input_data.dynamics_data.account else "Unknown Account"
                self.logger.info(f"Task {task_id}: Generating briefing for account '{account_name}'.")
            except Exception as val_err:
                self.logger.error(f"Task {task_id}: Invalid input: {val_err}")
                raise AgentProcessingError(f"Invalid input: {val_err}")

            self.logger.info(f"Task {task_id}: Formatting prompt...")
            prompt = self._format_briefing_prompt(input_data.dynamics_data, input_data.external_data, input_data.account_analysis)
            self.logger.info(f"Task {task_id}: Prompt formatted (length: {len(prompt)}). Calling LLM...")

            briefing_text = await self._call_llm(prompt)
            self.logger.info(f"Task {task_id}: LLM response received: {len(briefing_text)} chars")

            if "ERROR:" in briefing_text:
                self.logger.error(f"Task {task_id}: LLM call failed: {briefing_text}")
                error_message = briefing_text
                # Do not raise, let it reach finally block to set FAILED state
            else:
                output_data = BriefingOutput(account_briefing=briefing_text)
                completion_message = f"Generated briefing for account '{account_name}' ({len(briefing_text)} chars)"
                self.logger.info(f"Task {task_id}: {completion_message}")
                final_state = TaskStateEnum.COMPLETED # Set completed only if LLM call succeeded
                error_message = None # Clear error message on success

            # Use direct import now
            if output_data: # Only send message if LLM call was successful
                self.logger.info(f"Task {task_id}: Sending response via task store event")
                response_msg = Message(role="assistant", parts=[DataPart(content=output_data.model_dump())])
                await self.task_store.notify_message_event(task_id, response_msg)
                self.logger.info(f"Task {task_id}: Response message sent")
                # Add a short sleep AFTER sending message event
                await asyncio.sleep(0.1) # <<< ENSURE SLEEP HERE

        except AgentProcessingError as e:
            self.logger.error(f"Task {task_id}: Processing error: {e}")
            error_message = str(e)
            final_state = TaskStateEnum.FAILED
        except ConfigurationError as e:
            self.logger.error(f"Task {task_id}: Config error: {e}")
            error_message = str(e)
            final_state = TaskStateEnum.FAILED
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error: {e}")
            error_message = f"Unexpected error: {e}"
            final_state = TaskStateEnum.FAILED
        finally:
            self.logger.info(f"Task {task_id}: Setting final state to {final_state}, message: {error_message or 'None'}")
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            # Add a short sleep AFTER sending final state event
            await asyncio.sleep(0.1) # <<< ENSURE SLEEP HERE
            self.logger.info(f"Task {task_id}: Background processing finished. State: {final_state}")

    async def handle_task_get(self, task_id: str) -> Task:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        # Use direct import now
        messages = await self.task_store.get_messages(task_id) or []; artifacts = await self.task_store.get_artifacts(task_id) or []
        return Task(id=task_id, state=context.current_state, createdAt=context.created_at, updatedAt=context.updated_at, messages=messages, artifacts=artifacts) # type: ignore

    async def handle_task_cancel(self, task_id: str) -> bool:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        # Use direct import now (TaskStateEnum is TaskState)
        if context.current_state not in terminal:
            await self.task_store.update_task_state(task_id, TaskStateEnum.CANCELED, "Cancelled by request.")
            return True
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        self.logger.info(f"Task {task_id}: Entered handle_subscribe_request.")
        if not self.task_store: raise ConfigurationError("Task store missing.")

        # Create and register the queue
        q = asyncio.Queue()
        await self.task_store.add_listener(task_id, q)
        self.logger.info(f"Task {task_id}: Listener queue added.")

        # Get the current task state - may already have updates
        context = await self.task_store.get_task(task_id)
        if context:
            # If task already has a state, create and yield a status event
            self.logger.info(f"Task {task_id}: Current state is {context.current_state}")
            now = datetime.datetime.now(datetime.timezone.utc)
            # Only create event if SDK models are available
            status_event = TaskStatusUpdateEvent(taskId=task_id, state=context.current_state, timestamp=now)
            self.logger.info(f"Task {task_id}: Yielding initial state event.")
            try:
                yield status_event
                await asyncio.sleep(0.05)  # Ensure client has time to process
            except Exception as e:
                self.logger.error(f"Task {task_id}: Error yielding initial state: {e}")

        try:
            event_count = 0
            while True:
                try:
                    self.logger.debug(f"Task {task_id}: Waiting for event on queue...")
                    # Use a timeout to periodically check terminal state
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=2.0)
                        event_count += 1
                        self.logger.info(f"Task {task_id}: Retrieved event #{event_count} from queue: type={type(event).__name__}")
                    except asyncio.TimeoutError:
                        # No event received within timeout, check terminal state
                        context = await self.task_store.get_task(task_id)
                        if context and context.current_state in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]:
                            self.logger.info(f"Task {task_id}: Terminal state detected during wait timeout. Breaking.")
                            break
                        self.logger.debug(f"Task {task_id}: No event received in the last 2 seconds, continuing to wait...")
                        continue

                    # Simply yield the event directly
                    try:
                        self.logger.debug(f"Task {task_id}: Yielding event: {type(event).__name__}")
                        yield event
                        self.logger.debug(f"Task {task_id}: Yield successful.")
                        # Give control back to event loop
                        await asyncio.sleep(0.05)
                    except Exception as yield_err:
                        self.logger.error(f"Task {task_id}: Error during yield: {yield_err}", exc_info=True)
                        break  # Stop on yield error

                except Exception as loop_err:
                    self.logger.error(f"Task {task_id}: Error in main event processing loop: {loop_err}", exc_info=True)
                    break

                # Check for terminal state after processing event
                context = await self.task_store.get_task(task_id)
                terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                if context and context.current_state in terminal:
                    self.logger.info(f"Task {task_id}: Terminal state ({context.current_state}) detected after event processing. Breaking.")
                    break
        except asyncio.CancelledError:
            self.logger.info(f"Task {task_id}: SSE stream cancelled (client disconnected?).")
            raise  # Re-raise cancellation
        except Exception as loop_err:
            self.logger.error(f"Task {task_id}: Error in SSE generator outer loop: {loop_err}", exc_info=True)
        finally:
            self.logger.info(f"Task {task_id}: Removing SSE listener in finally block.")
            await self.task_store.remove_listener(task_id, q)
            self.logger.info(f"Task {task_id}: SSE listener removed. Total events yielded: {event_count}. Exiting handle_subscribe_request.")

    async def close(self):
        await self.http_client.aclose()
        self.logger.info("Briefing Generator Agent closed.")
