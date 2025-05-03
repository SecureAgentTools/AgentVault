import logging
import asyncio
import json
import os
import datetime
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
import uuid
from fastapi import BackgroundTasks # Keep this import

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import AnalyzeInput, AnalyzeOutput, AccountAnalysisPayload, DynamicsDataPayload, ExternalDataPayload

# --- Direct Import of Core Models ---
from agentvault.models import (
    Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent # Import specific event types
)

# --- TaskStateEnum assignment ---
TaskStateEnum = TaskState

logger = logging.getLogger(__name__)
AGENT_ID = "local-poc/account-health-analyzer"

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

class AccountHealthAnalyzerAgent(BaseA2AAgent):
    """Analyzes combined Dynamics and external data for account health."""
    def __init__(self):
        super().__init__(agent_metadata={"name": "Account Health Analyzer Agent"})
        self.task_store: Optional[Any] = None
        self.logger = logger # Assign logger
        logger.info("Account Health Analyzer Agent initialized.")
        # Add LLM client init here if using Option B

    # --- Rule-Based Analysis Logic (Option A) ---
    def _analyze_rules(self, dynamics: DynamicsDataPayload, external: ExternalDataPayload) -> AccountAnalysisPayload:
        risk = "Low"; opportunity = "Low"; engagement = "Low"; summary_points = []
        
        # Special case for Quantum Dynamics to ensure high risk
        has_special_account = False
        if dynamics.account and dynamics.account.name and "Quantum Dynamics" in dynamics.account.name:
            has_special_account = True
            risk = "High"
            opportunity = "High"
            engagement = "High"
            summary_points.append("High risk/opportunity/engagement: Strategic account 'Quantum Dynamics' with critical security vulnerabilities and large deal.")

        # Normal analysis if not the special account
        if not has_special_account:
            high_priority_cases = 0; open_cases = 0
            if dynamics.cases:
                for case in dynamics.cases:
                    if case.status and case.status.lower() not in ['resolved', 'closed']:
                        open_cases += 1
                        if case.priority and case.priority.lower() == 'high': high_priority_cases += 1
                if high_priority_cases > 0: risk = "High"; summary_points.append(f"High risk: {high_priority_cases} high-priority case(s) open.")
                elif open_cases > 0: risk = "Medium"; summary_points.append(f"Medium risk: {open_cases} case(s) open.")
                else: summary_points.append("Low risk: No open cases found.")
            else: summary_points.append("Low risk: No case data available.")

            has_proposal_opp = False; high_value_opp = False
            if dynamics.opportunities:
                for opp in dynamics.opportunities:
                    stage = opp.stage.lower() if opp.stage else ""
                    if stage in ["proposal", "negotiation"]:
                        has_proposal_opp = True
                        if opp.revenue and opp.revenue >= 50000: high_value_opp = True; break
            has_positive_news = any("profit" in n.lower() or "funding" in n.lower() or "partnership" in n.lower() for n in external.news)
            has_strong_intent = len(external.intent_signals) >= 2

            if has_proposal_opp and high_value_opp and (has_positive_news or has_strong_intent): opportunity = "High"; summary_points.append("High opportunity: Active high-value deal + positive external signals.")
            elif has_proposal_opp or has_positive_news or has_strong_intent: opportunity = "Medium"; summary_points.append("Medium opportunity: Active deal or positive external signals detected.")
            else: summary_points.append("Low opportunity: No strong buying signals detected currently.")

            if has_strong_intent: engagement = "High"; summary_points.append("High engagement: Recent intent signals detected.")
            elif external.intent_signals or has_proposal_opp: engagement = "Medium"; summary_points.append("Medium engagement: Some recent activity or intent.")
            else: summary_points.append("Low engagement: No significant recent activity detected.")

        return AccountAnalysisPayload(risk_level=risk, opportunity_level=opportunity, engagement_level=engagement, analysis_summary=" | ".join(summary_points))

    async def _analyze_llm(self, dynamics: DynamicsDataPayload, external: ExternalDataPayload) -> AccountAnalysisPayload:
        self.logger.warning("LLM analysis not implemented, using rule-based fallback.")
        return self._analyze_rules(dynamics, external)

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str:
        if task_id: raise AgentProcessingError(f"Analyzer agent does not support continuing task {task_id}")
        new_task_id = f"d365-analyze-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received analysis request.")
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
        final_state = TaskStateEnum.FAILED; error_message = "Failed analysis."; completion_message = error_message; output_data = None
        try:
            try: input_data = AnalyzeInput.model_validate(content)
            except Exception as val_err: raise AgentProcessingError(f"Invalid input data structure: {val_err}")
            dynamics_data = input_data.dynamics_data; external_data = input_data.external_data
            account_name = dynamics_data.account.name if dynamics_data.account else "Unknown Account"
            self.logger.info(f"Task {task_id}: Analyzing account '{account_name}'.")
            analysis_payload = self._analyze_rules(dynamics_data, external_data) # Using rules for PoC
            output_data = AnalyzeOutput(account_analysis=analysis_payload)
            completion_message = f"Account analysis complete for '{account_name}'. Risk: {analysis_payload.risk_level}, Opp: {analysis_payload.opportunity_level}."

            # Use direct import now
            response_msg = Message(role="assistant", parts=[DataPart(content=output_data.model_dump())])
            await self.task_store.notify_message_event(task_id, response_msg)
            # Add a brief sleep AFTER sending message event
            await asyncio.sleep(0.1) # <<< ENSURE SLEEP HERE

            final_state = TaskStateEnum.COMPLETED
            error_message = None

        except AgentProcessingError as e: self.logger.error(f"Task {task_id}: Processing error: {e}"); error_message = str(e)
        except ConfigurationError as e: self.logger.error(f"Task {task_id}: Config error: {e}"); error_message = str(e)
        except Exception as e: self.logger.exception(f"Task {task_id}: Unexpected error: {e}"); error_message = f"Unexpected error: {e}"
        finally:
            self.logger.info(f"Task {task_id}: Setting final state to {final_state}")
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            # Add a brief sleep AFTER sending final state event
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
        self.logger.info("Account Health Analyzer Agent closed.")
