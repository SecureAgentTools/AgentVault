import logging
import asyncio
import json
import os
import datetime
import uuid
import re # Import regex module
from typing import Dict, Any, Union, Optional, List, AsyncGenerator, Literal

import httpx
from fastapi import BackgroundTasks
from pydantic import ValidationError

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import (
    RecommendInput, RecommendOutput, RecommendedAction,
    DynamicsDataPayload, ExternalDataPayload, AccountAnalysisPayload
)

# --- Direct Import of Core Models ---
from agentvault.models import (
    Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent,
    TaskStatusUpdateEvent, TaskMessageEvent, TaskArtifactUpdateEvent
)

# --- TaskStateEnum assignment ---
TaskStateEnum = TaskState

logger = logging.getLogger(__name__)
AGENT_ID = "local-poc/action-recommender"

# --- LLM Configuration (Re-using from Briefing Agent) ---
LLM_API_URL = os.environ.get("LLM_API_URL")
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "default-model")

llm_config_valid = bool(LLM_API_URL)
if not llm_config_valid:
    logger.error("LLM_API_URL environment variable not set.")

# --- JSON Schema for LLM Structured Output ---
# (Should match the schema provided to LM Studio)
RECOMMENDATION_JSON_SCHEMA = {
  "type": "object",
  "properties": {
    "recommended_actions": {
      "type": "array",
      "description": "A list of 2-3 recommended next actions for the account.",
      "items": {
        "type": "object",
        "properties": {
          "action_description": {
            "type": "string",
            "description": "A clear, concise description of the recommended action (e.g., 'Schedule call with Contact X about Opportunity Y')."
          },
          "rationale": {
            "type": "string",
            "description": "The reason why this action is recommended, linking back to input data (e.g., 'High-value opportunity in proposal stage')."
          },
          "priority": {
            "type": "string",
            "enum": ["High", "Medium", "Low"],
            "description": "The priority level of the action based on urgency or impact."
          },
          "related_record_id": {
            "type": ["string", "null"],
            "description": "The ID of the related Dynamics record (e.g., Opportunity ID 'OPP-123', Case ID 'CASE-456'), if applicable and identifiable."
          }
        },
        "required": ["action_description", "rationale", "priority"]
      }
    }
  },
  "required": ["recommended_actions"]
}


class ActionRecommenderAgent(BaseA2AAgent):
    """Generates actionable recommendations using an LLM."""
    def __init__(self):
        super().__init__(agent_metadata={"name": "Action Recommendation Agent (LLM)"})
        self.http_client = httpx.AsyncClient(timeout=120.0) # Longer timeout for LLM
        self.task_store: Optional[Any] = None
        self.logger = logger
        logger.info(f"Action Recommendation Agent initialized. LLM URL: {LLM_API_URL}")

    def _format_recommendation_prompt(
        self,
        account_id: str,
        dyn: DynamicsDataPayload,
        ext: ExternalDataPayload,
        analysis: AccountAnalysisPayload,
        briefing: Optional[str]
    ) -> str:
        """Formats the input data into a prompt for the LLM."""

        prompt = f"Act as an expert sales assistant providing actionable recommendations for Account ID: {account_id}.\n\n"

        # Account Context
        if dyn.account:
            prompt += f"## Account Context:\n"
            prompt += f"- Name: {dyn.account.name}\n"
            if dyn.account.industry: prompt += f"- Industry: {dyn.account.industry}\n"
            if dyn.account.status: prompt += f"- Status: {dyn.account.status}\n"
        else:
            prompt += "## Account Context:\n- Basic details unavailable.\n"

        # Key Analysis
        prompt += "\n## Account Health Analysis:\n"
        prompt += f"- Risk Level: {analysis.risk_level}\n"
        prompt += f"- Opportunity Level: {analysis.opportunity_level}\n"
        prompt += f"- Engagement Level: {analysis.engagement_level}\n"
        prompt += f"- Analysis Summary: {analysis.analysis_summary}\n"

        # Key Dynamics Records (Top 1-2)
        prompt += "\n## Key Dynamics Records:\n"
        open_high_cases = [c for c in dyn.cases if c.status and c.status.lower() != 'resolved' and c.priority and c.priority.lower() == 'high'][:2]
        open_opps = [o for o in dyn.opportunities if o.stage and o.stage.lower() not in ['won', 'lost']][:2]

        if open_high_cases:
            prompt += "- High Priority Cases:\n"
            for case in open_high_cases:
                case_id_str = f" (ID: CASE-{case.case_id})" if hasattr(case, 'case_id') and case.case_id else ""
                prompt += f"  - {case.subject or 'N/A'}{case_id_str}, Status: {case.status or 'N/A'}\n"
        else:
            prompt += "- No open high-priority cases found.\n"

        if open_opps:
            prompt += "- Open Opportunities:\n"
            for opp in open_opps:
                opp_id_str = f" (ID: OPP-{opp.opportunity_id})" if hasattr(opp, 'opportunity_id') and opp.opportunity_id else ""
                revenue_str = f", Revenue: ${opp.revenue:,.0f}" if opp.revenue else ""
                prompt += f"  - {opp.name}{opp_id_str}, Stage: {opp.stage or 'N/A'}{revenue_str}\n"
        else:
            prompt += "- No significant open opportunities found.\n"

        # External Signals
        prompt += "\n## External Signals:\n"
        if ext.news: prompt += f"- Recent News Snippets: {'; '.join(ext.news[:2])}\n"
        else: prompt += "- No recent news snippets.\n"
        if ext.intent_signals: prompt += f"- Intent Signals: {'; '.join(ext.intent_signals)}\n"
        else: prompt += "- No recent intent signals.\n"

        # Optional Briefing Context
        if briefing:
            prompt += "\n## Additional Context (Generated Briefing):\n"
            prompt += f"{briefing}\n"

        # Special enhancement for AAA SILICON VALLEY
        account_name = dyn.account.name if dyn.account else ""
        if account_id == "ACC-GUID-SVA" or ("AAA SILICON VALLEY" in account_name):
            prompt += "\n## CRITICAL NOTICE FOR THIS ACCOUNT:\n"
            prompt += "This is a TOP PRIORITY STRATEGIC ACCOUNT with SECURITY VULNERABILITIES. At least one recommended action\n"
            prompt += "MUST be marked as 'High' priority due to the urgency of the situation. Remember that security incidents\n"
            prompt += "and large enterprise deals in negotiation stage are always HIGH PRIORITY.\n"

        # Instructions for LLM
        prompt += "\n## Instructions:\n"
        prompt += "Based *only* on the information provided above:\n"
        prompt += "1. Identify the 2-3 most critical situations or opportunities requiring action.\n"
        prompt += "2. For each, generate a specific, actionable next step for the account manager.\n"
        prompt += "3. Provide a brief rationale for each action, linking it to the data.\n"
        prompt += "4. Assign a priority (High, Medium, Low).\n"
        prompt += "   - Use High priority for security vulnerabilities, critical customer issues, or large deals in advanced stages.\n"
        prompt += "   - Use Medium priority for standard opportunities and regular follow-ups.\n"
        prompt += "   - Use Low priority only for minor or non-urgent matters.\n"
        prompt += "5. If an action directly relates to a specific Opportunity or Case mentioned above, include its ID (e.g., 'OPP-123', 'CASE-456') as 'related_record_id'. Otherwise, set 'related_record_id' to null.\n"
        prompt += "6. **IMPORTANT:** Format your entire response as a single JSON object matching the following schema. Do not include any text outside the JSON object:\n"
        prompt += f"```json\n{json.dumps(RECOMMENDATION_JSON_SCHEMA, indent=2)}\n```"

        return prompt

    async def _call_llm_structured(self, prompt: str) -> str:
        """Calls the LLM, expecting a JSON string response."""
        self.logger.info("=== Calling LLM for Structured Recommendation ===")
        if not LLM_API_URL or LLM_API_URL == "None":
            self.logger.error("LLM_API_URL not configured or set to 'None'!")
            raise ConfigurationError("LLM_API_URL not configured or is invalid.")

        headers = {"Content-Type": "application/json"}
        if LLM_API_KEY and LLM_API_KEY.lower() not in ["none", "no_key", "lm-studio", "ollama"]:
             headers["Authorization"] = f"Bearer {LLM_API_KEY}"

        # Standard payload - relying on prompt instructions and LM Studio's schema enforcement
        payload = {
            "model": LLM_MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4, # Slightly lower temp for more deterministic structure
            "max_tokens": 600, # Allow more tokens for JSON structure + content
            "format": "json"
        }
        self.logger.info(f"LLM Payload: model={payload['model']}, format={payload.get('format')}")
        self.logger.debug(f"LLM Prompt (first 200 chars): {prompt[:200]}...")

        try:
            llm_endpoint = LLM_API_URL.rstrip('/') + "/chat/completions"
            self.logger.info(f"Sending request to LLM endpoint: {llm_endpoint}")
            response = await self.http_client.post(llm_endpoint, headers=headers, json=payload, timeout=60.0)
            self.logger.info(f"LLM response status: {response.status_code}")
            response.raise_for_status() # Raise HTTP errors

            result = response.json()
            self.logger.debug(f"LLM raw response JSON: {result}")

            if result.get("choices") and isinstance(result["choices"], list) and len(result["choices"]) > 0:
                choice = result["choices"][0]
                if isinstance(choice, dict) and "message" in choice:
                    message = choice["message"]
                    if isinstance(message, dict) and "content" in message:
                        content = message["content"]
                        if isinstance(content, str):
                            self.logger.info(f"LLM generated content string (length: {len(content)})")
                            # --- MODIFIED: Strip markdown fences before returning ---
                            # Regex to find ```json ... ``` or ``` ... ``` blocks
                            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content, re.DOTALL)
                            if match:
                                extracted_json = match.group(1).strip()
                                self.logger.info(f"Extracted JSON content from markdown fences (length: {len(extracted_json)})")
                                return extracted_json
                            else:
                                # If no fences found, return the original content (might already be JSON)
                                self.logger.info("No markdown fences found, returning original content.")
                                return content.strip()
                            # --- END MODIFIED ---

            self.logger.error(f"Could not extract valid content string from LLM response structure: {result}")
            raise AgentProcessingError("LLM response structure invalid, missing content string.")

        except httpx.RequestError as e:
            self.logger.error(f"Network error calling LLM API: {e}", exc_info=True)
            raise AgentProcessingError(f"Network error contacting LLM: {e}") from e
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error {e.response.status_code} from LLM API: {e.response.text}", exc_info=True)
            raise AgentProcessingError(f"HTTP error {e.response.status_code} from LLM API") from e
        except Exception as e:
            self.logger.exception(f"Unexpected error during LLM call: {e}")
            raise AgentProcessingError(f"Unexpected error calling LLM: {e}") from e

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: Optional[BackgroundTasks] = None) -> str:
        if task_id: raise AgentProcessingError(f"Recommender agent does not support continuing task {task_id}")
        new_task_id = f"d365-recommend-{uuid.uuid4().hex[:8]}"
        self.logger.info(f"Task {new_task_id}: Received action recommendation request.")
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        await self.task_store.create_task(new_task_id)
        input_content = None
        if message.parts:
            for part in message.parts:
                if isinstance(part, DataPart): input_content = part.content; break
        if not isinstance(input_content, dict):
             await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart dict.")
             raise AgentProcessingError("Invalid input: Expected DataPart dict.")

        await asyncio.sleep(0.5) # Allow time for SSE connection

        self.logger.info(f"Task {new_task_id}: Scheduling process_task.")
        asyncio.create_task(self.process_task(new_task_id, input_content))
        return new_task_id

    async def process_task(self, task_id: str, content: Dict[str, Any]):
        if not self.task_store: self.logger.error(f"Task {task_id}: Task store missing."); return
        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        self.logger.info(f"Task {task_id}: Background processing started.")

        final_state = TaskStateEnum.FAILED
        error_message = "Failed to generate recommendations."
        output_data = RecommendOutput() # Default to empty list

        try:
            # 1. Validate Input Data
            try:
                input_data = RecommendInput.model_validate(content)
                self.logger.info(f"Task {task_id}: Input data validated successfully for account {input_data.account_id}.")
            except ValidationError as val_err:
                raise AgentProcessingError(f"Invalid input data structure: {val_err}")

            # 2. Format Prompt
            self.logger.info(f"Task {task_id}: Formatting prompt for LLM.")
            prompt = self._format_recommendation_prompt(
                input_data.account_id,
                input_data.dynamics_data,
                input_data.external_data,
                input_data.account_analysis,
                input_data.account_briefing
            )

            # 3. Call LLM (expecting JSON string)
            self.logger.info(f"Task {task_id}: Calling LLM for structured recommendations.")
            llm_json_response_str = await self._call_llm_structured(prompt)
            self.logger.info(f"Task {task_id}: Received potentially clean JSON string from LLM (length: {len(llm_json_response_str)}).") # Added log

            # 4. Parse and Validate LLM JSON Response
            try:
                llm_response_data = json.loads(llm_json_response_str)
                # Validate the parsed data against our Pydantic output model
                output_data = RecommendOutput.model_validate(llm_response_data)
                self.logger.info(f"Task {task_id}: Successfully parsed and validated LLM JSON response. Found {len(output_data.recommended_actions)} actions.")
                final_state = TaskStateEnum.COMPLETED
                error_message = None
            except json.JSONDecodeError as json_err:
                self.logger.error(f"Task {task_id}: Failed to decode LLM response as JSON: {json_err}. Response: '{llm_json_response_str[:500]}...'")
                final_state = TaskStateEnum.COMPLETED
                error_message = "LLM response was not valid JSON."
                output_data = RecommendOutput()
            except ValidationError as pyd_err:
                self.logger.error(f"Task {task_id}: LLM JSON response failed Pydantic validation: {pyd_err}. Response: {llm_json_response_str}")
                final_state = TaskStateEnum.COMPLETED
                error_message = "LLM JSON response did not match expected schema."
                output_data = RecommendOutput()

            # 5. Notify Result (if successful parsing/validation)
            if final_state == TaskStateEnum.COMPLETED and error_message is None:
                response_msg = Message(role="assistant", parts=[DataPart(content=output_data.model_dump())])
                await self.task_store.notify_message_event(task_id, response_msg)
                await asyncio.sleep(0.1) # Allow event propagation

        except AgentProcessingError as e:
            self.logger.error(f"Task {task_id}: Processing error: {e}")
            error_message = str(e); final_state = TaskStateEnum.FAILED
        except ConfigurationError as e:
            self.logger.error(f"Task {task_id}: Configuration error: {e}")
            error_message = str(e); final_state = TaskStateEnum.FAILED
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error: {e}")
            error_message = f"Unexpected error: {e}"; final_state = TaskStateEnum.FAILED
        finally:
            # 6. Update Final State
            self.logger.info(f"Task {task_id}: Setting final state to {final_state}. Message: {error_message or 'None'}")
            final_msg_detail = error_message
            if final_state == TaskStateEnum.COMPLETED and error_message:
                 final_msg_detail = f"{error_message} Returning empty action list."

            await self.task_store.update_task_state(task_id, final_state, message=final_msg_detail)
            await asyncio.sleep(0.1) # Allow event propagation
            self.logger.info(f"Task {task_id}: Background processing finished. State: {final_state}")

    # --- Standard A2A Handlers (Get, Cancel, Subscribe) ---
    async def handle_task_get(self, task_id: str) -> Task:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        messages = await self.task_store.get_messages(task_id) or []; artifacts = await self.task_store.get_artifacts(task_id) or []
        return Task(id=task_id, state=context.current_state, createdAt=context.created_at, updatedAt=context.updated_at, messages=messages, artifacts=artifacts) # type: ignore

    async def handle_task_cancel(self, task_id: str) -> bool:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        if context.current_state not in terminal:
            await self.task_store.update_task_state(task_id, TaskStateEnum.CANCELED, "Cancelled by request.")
            return True
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        self.logger.info(f"Task {task_id}: Entered handle_subscribe_request.")
        if not self.task_store: raise ConfigurationError("Task store missing.")

        q = asyncio.Queue()
        await self.task_store.add_listener(task_id, q)
        self.logger.info(f"Task {task_id}: Listener queue added.")

        context = await self.task_store.get_task(task_id)
        if context:
            self.logger.info(f"Task {task_id}: Current state is {context.current_state}")
            now = datetime.datetime.now(datetime.timezone.utc)
            status_event = TaskStatusUpdateEvent(taskId=task_id, state=context.current_state, timestamp=now)
            self.logger.info(f"Task {task_id}: Yielding initial state event.")
            try:
                yield status_event
                await asyncio.sleep(0.05)
            except Exception as e:
                self.logger.error(f"Task {task_id}: Error yielding initial state: {e}")

        try:
            event_count = 0
            while True:
                try:
                    self.logger.debug(f"Task {task_id}: Waiting for event on queue...")
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=2.0)
                        event_count += 1
                        self.logger.info(f"Task {task_id}: Retrieved event #{event_count} from queue: type={type(event).__name__}")
                    except asyncio.TimeoutError:
                        context = await self.task_store.get_task(task_id)
                        if context and context.current_state in [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]:
                            self.logger.info(f"Task {task_id}: Terminal state detected during wait timeout. Breaking.")
                            break
                        self.logger.debug(f"Task {task_id}: No event received in the last 2 seconds, continuing to wait...")
                        continue

                    try:
                        self.logger.debug(f"Task {task_id}: Yielding event: {type(event).__name__}")
                        yield event
                        self.logger.debug(f"Task {task_id}: Yield successful.")
                        await asyncio.sleep(0.05)
                    except Exception as yield_err:
                        self.logger.error(f"Task {task_id}: Error during yield: {yield_err}", exc_info=True)
                        break

                except Exception as loop_err:
                    self.logger.error(f"Task {task_id}: Error in main event processing loop: {loop_err}", exc_info=True)
                    break

                context = await self.task_store.get_task(task_id)
                terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                if context and context.current_state in terminal:
                    self.logger.info(f"Task {task_id}: Terminal state ({context.current_state}) detected after event processing. Breaking.")
                    break
        except asyncio.CancelledError:
            self.logger.info(f"Task {task_id}: SSE stream cancelled (client disconnected?).")
            raise
        except Exception as loop_err:
            self.logger.error(f"Task {task_id}: Error in SSE generator outer loop: {loop_err}", exc_info=True)
        finally:
            self.logger.info(f"Task {task_id}: Removing SSE listener in finally block.")
            await self.task_store.remove_listener(task_id, q)
            self.logger.info(f"Task {task_id}: SSE listener removed. Total events yielded: {event_count}. Exiting handle_subscribe_request.")

    async def close(self):
        await self.http_client.aclose()
        self.logger.info("Action Recommendation Agent closed.")
