import logging
import asyncio
import json
import traceback
import os
import re
import httpx
from typing import Dict, Any, Union, List, Optional, Tuple
import datetime
import random # Keep random only for fallback confidence if LLM fails

# Import base class and SDK components
from base_agent import ResearchAgent
from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in fact_verification_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState # Use state from base if possible
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "fact-verification-agent"

# --- LLM Configuration ---
LLM_API_URL = os.getenv("LLM_API_URL", "http://localhost:1234/v1") # Default to localhost if not set
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio") # Default if not set
LLM_MODEL = os.getenv("LLM_MODEL", "local-model") # Default if not set
ENABLE_LLM = os.getenv("ENABLE_LLM", "true").lower() in ("true", "1", "yes")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1")) # Low temp for factual assessment
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "512")) # Limit response size
LLM_REQUEST_TIMEOUT = 60.0

class FactVerificationAgent(ResearchAgent):
    """
    Cross-references extracted facts, verifies details, and assigns confidence scores using an LLM.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Fact Verification Agent"})
        # --- ADDED: Initialize httpx client ---
        self.http_client = httpx.AsyncClient(timeout=LLM_REQUEST_TIMEOUT + 5.0)
        if ENABLE_LLM and (not LLM_API_URL or not LLM_MODEL):
             logger.warning("LLM is enabled but API URL or Model Name is missing. Verification will use fallback.")
        elif not ENABLE_LLM:
             logger.warning("LLM verification is disabled. Agent will use placeholder logic.")
        # --- END ADDED ---

    # --- ADDED: LLM Call Helper ---
    async def call_llm(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Calls the configured LLM API."""
        if not ENABLE_LLM or not LLM_API_URL or not LLM_MODEL:
            return None # Cannot call LLM if disabled or not configured

        try:
            self.logger.debug(f"Calling LLM API: {LLM_API_URL}")
            payload = {
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS
                # Removed response_format as it's causing errors
            }
            headers = {"Content-Type": "application/json"}
            if LLM_API_KEY and LLM_API_KEY != "not-needed": # Handle LM Studio default
                headers["Authorization"] = f"Bearer {LLM_API_KEY}"

            response = await self.http_client.post(
                f"{LLM_API_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers
            )

            if response.status_code == 200:
                response_data = response.json()
                content = response_data.get("choices", [{}])[0].get("message", {}).get("content")
                if content:
                    self.logger.debug(f"LLM response received: {content[:100]}...")
                    return content.strip()
                else:
                    self.logger.warning(f"LLM response missing content: {response_data}")
            else:
                self.logger.error(f"LLM API error: {response.status_code} - {response.text[:200]}")

        except httpx.RequestError as e:
            self.logger.error(f"Network error calling LLM API: {e}")
        except Exception as e:
            self.logger.exception(f"Unexpected error calling LLM: {e}")

        return None
    # --- END ADDED ---

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Processes extracted facts to verify them and assign confidence using an LLM.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Processing fact verification request for task {task_id}")

        verified_facts = []
        verification_issues = []
        final_state = TaskState.FAILED # Default to failed
        error_message = "Fact verification failed." # Default error

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            extracted_info_dict: Dict[str, Any] = content.get("extracted_information", {})
            if isinstance(extracted_info_dict, dict) and "extracted_facts" in extracted_info_dict:
                extracted_facts = extracted_info_dict.get("extracted_facts", [])
            else: extracted_facts = [] # Default to empty if structure is wrong

            if not extracted_facts:
                self.logger.warning(f"Task {task_id}: No 'extracted_facts' found. Completing with empty results.")
                completion_message = "No facts provided for verification."
                final_state = TaskState.COMPLETED # Task completed, just no work done
                error_message = None # No error in this case
            else:
                self.logger.info(f"Task {task_id}: Verifying {len(extracted_facts)} extracted facts/quotes.")

                system_prompt = """You are a meticulous fact-checker AI. Analyze the provided 'fact_text' and its 'source_url'.
Based *only* on the text provided and general knowledge about source credibility (e.g., is the domain reputable like .gov, .edu, major news org vs. unknown blog?), assess the fact.
DO NOT access the internet or the source URL.
Determine a verification status ('verified', 'uncertain', 'contradicted' - use 'uncertain' if unsure or lacking context), a confidence score (0.0 to 1.0), and provide brief verification notes explaining your reasoning.
Output ONLY a valid JSON object with the keys: "verification_status", "confidence_score", "verification_notes". Example:
{"verification_status": "verified", "confidence_score": 0.85, "verification_notes": "Statement aligns with common knowledge and source domain appears credible."}"""

                for i, fact in enumerate(extracted_facts):
                    if not isinstance(fact, dict):
                        self.logger.warning(f"Skipping invalid fact entry (not a dict): {fact}")
                        continue

                    fact_text = fact.get('text', '').strip()
                    source_url = fact.get('source_url', 'unknown_source')
                    fact_id = fact.get("id", f"unknown-{i}")

                    if not fact_text:
                        self.logger.warning(f"Skipping fact with empty text (ID: {fact_id})")
                        continue

                    user_prompt = f"""Fact to verify:
Fact Text: "{fact_text}"
Source URL: "{source_url}"

Please provide your assessment in the required JSON format."""

                    llm_response_str = await self.call_llm(system_prompt, user_prompt)

                    status = "uncertain"
                    confidence = 0.5
                    notes = "LLM verification failed or disabled."
                    issue = None

                    if llm_response_str:
                        try:
                            # Attempt to parse potentially messy JSON
                            match = re.search(r'\{.*\}', llm_response_str, re.DOTALL)
                            if match:
                                json_str = match.group(0)
                                llm_data = json.loads(json_str)
                                status = llm_data.get("verification_status", "uncertain")
                                confidence = float(llm_data.get("confidence_score", 0.5))
                                notes = llm_data.get("verification_notes", "No notes from LLM.")
                                self.logger.debug(f"LLM verification for fact {fact_id}: Status={status}, Score={confidence}")
                                if status == "contradicted":
                                     issue = { "fact_id": fact_id, "issue_type": "llm_contradiction", "details": notes }
                            else:
                                logger.warning(f"Could not extract JSON from LLM response for fact {fact_id}: {llm_response_str[:100]}...")
                                notes = "LLM response format error."
                        except (json.JSONDecodeError, ValueError, TypeError) as e:
                            logger.warning(f"Error parsing LLM verification response for fact {fact_id}: {e}. Response: {llm_response_str[:100]}...")
                            notes = f"LLM response parsing error: {e}"
                        except Exception as e:
                            logger.error(f"Unexpected error processing LLM response for fact {fact_id}: {e}")
                            notes = f"Unexpected error processing LLM response."
                    else:
                         # Fallback if LLM call failed or disabled - use basic checks
                         if source_url == "internal-placeholder" or source_url == "unknown_source":
                             confidence = 0.3
                             notes = "Fact source unknown or placeholder."
                             status = "uncertain"
                         elif len(fact_text) < 30:
                             confidence = 0.4
                             notes = "Fact text is very short."
                             status = "uncertain"
                         else:
                             confidence = 0.6 # Default confidence for fallback
                             notes = "Basic verification passed (LLM fallback)."
                             status = "verified" # Tentatively verified

                    verified_fact_data = {
                        **fact, # Keep original fact data
                        "verification_status": status,
                        "confidence_score": round(confidence, 3),
                        "verification_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "verification_notes": notes
                    }
                    verified_facts.append(verified_fact_data)
                    if issue:
                        verification_issues.append(issue)

                completion_message = f"Verified {len(extracted_facts)} facts/quotes. Found {len(verification_issues)} potential issues."
                final_state = TaskState.COMPLETED # Mark as completed if loop finishes
                error_message = None # Clear default error if successful

        except Exception as e:
            self.logger.exception(f"Error processing fact verification for task {task_id}: {e}")
            error_message = f"Failed to process fact verification: {e}"
            final_state = TaskState.FAILED
            completion_message = error_message # Use error as completion message

        finally:
            # --- MODIFIED: Always notify artifacts before setting final state ---
            if _MODELS_AVAILABLE:
                try:
                    logger.info(f"Task {task_id}: Notifying verification artifacts (Verified: {len(verified_facts)}, Issues: {len(verification_issues)}).")
                    # Verified Facts Artifact
                    verified_facts_artifact = Artifact(
                        id=f"{task_id}-verified_facts", type="verified_facts",
                        content={"verified_facts": verified_facts}, media_type="application/json"
                    )
                    await self.task_store.notify_artifact_event(task_id, verified_facts_artifact)

                    # Verification Report Artifact
                    report_artifact = Artifact(
                        id=f"{task_id}-verification_report", type="verification_report",
                        content={"issues_found": verification_issues}, media_type="application/json"
                    )
                    await self.task_store.notify_artifact_event(task_id, report_artifact)
                except Exception as notify_err:
                    logger.error(f"Task {task_id}: CRITICAL - Failed to notify verification artifacts: {notify_err}")
                    final_state = TaskState.FAILED
                    error_message = error_message or f"Failed to notify artifacts: {notify_err}"
                    completion_message = error_message
            else:
                logger.warning("Task {task_id}: Cannot notify artifacts: Core models not available.")
            # --- END MODIFIED ---

            # Notify completion/error message
            if _MODELS_AVAILABLE:
                 try:
                     response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                     await self.task_store.notify_message_event(task_id, response_msg)
                 except Exception as notify_err:
                      logger.error(f"Task {task_id}: Failed to notify final message: {notify_err}")
            else:
                 logger.info(f"Task {task_id}: Final message: {completion_message}")

            # Set final state
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            self.logger.info(f"Task {task_id}: EXITING process_task for FactVerificationAgent. Final State: {final_state}")

    # --- ADDED: Close method for httpx client ---
    async def close(self):
        """Close the httpx client when the agent shuts down."""
        await self.http_client.aclose()
        await super().close() # Call base class close if needed
        logger.info("Closed internal httpx client for FactVerificationAgent.")
    # --- END ADDED ---


# FastAPI app setup
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from agentvault_server_sdk import create_a2a_router
import os

# Create agent instance
agent = FactVerificationAgent()

# Create FastAPI app
app = FastAPI(title="FactVerificationAgent")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include A2A router with BackgroundTasks dependency
router = create_a2a_router(
    agent=agent,
    task_store=agent.task_store, # Pass the agent's store
    dependencies=[Depends(lambda: BackgroundTasks())] # Add dependency here
)
app.include_router(router, prefix="/a2a")


# Serve agent card
@app.get("/agent-card.json")
async def get_agent_card():
    card_path = os.getenv("AGENT_CARD_PATH", "/app/agent-card.json")
    try:
        with open(card_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read agent card from {card_path}: {e}")
        # Fallback - try to read from mounted location
        try:
            with open("/app/agent-card.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e2:
            logger.error(f"Failed to read fallback agent card: {e2}")
            return {"error": "Agent card not found"}

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
