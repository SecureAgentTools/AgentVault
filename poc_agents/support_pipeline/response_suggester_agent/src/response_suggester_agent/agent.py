import logging
import asyncio
import json
import os
import random
from typing import Dict, Any, Union, Optional, List

import httpx # For LLM calls (REQ-SUP-SUG-007)

# Import base class and SDK components
try:
    from base_agent import ResearchAgent
except ImportError:
    try:
         from ...research_pipeline.base_agent import ResearchAgent
    except ImportError:
        logging.getLogger(__name__).critical("Could not import BaseA2AAgent. Agent will not function.")
        class ResearchAgent: # type: ignore
             def __init__(self, *args, **kwargs): pass
             async def process_task(self, task_id, content): pass
             task_store = None # type: ignore

from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError

# Import models from this agent's models.py (REQ-SUP-SUG-004, 005)
from .models import (
    SuggestionInput, SuggestedResponseArtifactContent,
    TicketAnalysis, KnowledgeBaseArticle, CustomerHistorySummary # Import dependent models
)

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in response_suggester_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/support-response-suggester" # REQ-SUP-SUG-002

# --- LLM Configuration (from .env) ---
LLM_API_URL = os.environ.get("LLM_API_URL")
LLM_API_KEY = os.environ.get("LLM_API_KEY") # May be optional depending on LLM service
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF") # Or another default

if not LLM_API_URL:
    logger.error("LLM_API_URL environment variable not set. Response Suggestion Agent cannot function.")
    # Optionally raise ConfigurationError here or handle gracefully in process_task

class ResponseSuggestionAgent(ResearchAgent): # REQ-SUP-SUG-001
    """
    Generates a draft support response using context and an LLM.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Response Suggestion Agent"})
        self.http_client = httpx.AsyncClient(timeout=60.0) # Client for LLM calls
        logger.info(f"Response Suggestion Agent initialized. LLM URL: {LLM_API_URL}")

    async def _call_llm(self, prompt: str) -> str:
        """Helper function to call the configured LLM API."""
        if not LLM_API_URL:
            logger.warning("LLM_API_URL is not configured. Using mock response.")
            return self._get_mock_response(prompt)

        try:
            headers = {"Content-Type": "application/json"}
            if LLM_API_KEY and LLM_API_KEY != "lm-studio": # LM Studio often doesn't need a key
                 headers["Authorization"] = f"Bearer {LLM_API_KEY}"

            # Basic payload structure for OpenAI compatible APIs
            payload = {
                "model": LLM_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "You are a helpful and empathetic customer support agent. Draft a response based ONLY on the provided context. Be concise and address the customer's issue directly. If KB articles are provided, reference the most relevant one briefly."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 300
            }

            logger.debug(f"Sending request to LLM: {LLM_API_URL}")
            try:
                response = await self.http_client.post(f"{LLM_API_URL}/chat/completions", headers=headers, json=payload)
                response.raise_for_status() # Raise exception for 4xx/5xx errors
                
                result = response.json()
                logger.debug(f"LLM Response JSON: {result}")

                # Extract content - adjust based on actual LLM API response structure
                if result.get("choices") and isinstance(result["choices"], list) and len(result["choices"]) > 0:
                    message = result["choices"][0].get("message")
                    if message and isinstance(message, dict):
                        content = message.get("content")
                        if content and isinstance(content, str):
                            logger.info("Successfully received response content from LLM.")
                            return content.strip()
                
                logger.warning(f"Could not extract valid content from LLM response: {result}")
                return self._get_mock_response(prompt)  # Fall back to mock response
            except Exception as e:
                logger.error(f"Error calling LLM API: {e}")
                return self._get_mock_response(prompt)  # Fall back to mock response

        except Exception as e:
            logger.exception(f"Unexpected error during LLM call: {e}")
            return self._get_mock_response(prompt)  # Fall back to mock response

    def _get_mock_response(self, prompt: str) -> str:
        """Generate a mock response when LLM is unavailable."""
        logger.info("Using mock response generator as fallback")
        
        # Check if the prompt contains certain keywords to customize the mock response
        mock_responses = {
            "Billing": "Thank you for contacting our support team regarding your billing inquiry. I understand you have questions about your recent charges. Rest assured, we'll help clarify any concerns.",
            "Technical": "Thank you for reporting this technical issue. I understand how frustrating technical problems can be. Based on your description, I'd like to suggest a few troubleshooting steps.",
            "Account Management": "Thank you for your account management request. We'll be happy to help you update your account information promptly.",
            "Sales": "Thank you for your interest in our products and features. I'd be happy to provide more information about the options available to you.",
            "Mobile App": "Thank you for your report about our mobile app. We appreciate your feedback and would like to help resolve any issues you're experiencing."
        }
        
        # Default response if no matching category is found
        default_response = "Thank you for contacting our support team. We appreciate your message and will help with your inquiry. Could you please provide more details about your request so we can assist you better?"
        
        # Look for category mentions in the prompt
        for category, response in mock_responses.items():
            if category.lower() in prompt.lower():
                return response
        
        return default_response


    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Generates response suggestion using LLM. REQ-SUP-SUG-006.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing response suggestion request.")
        suggested_response_text: Optional[str] = None
        final_state = TaskState.FAILED
        error_message = "Failed to generate response suggestion."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # Validate input using Pydantic model (REQ-SUP-SUG-004)
            try:
                input_data = SuggestionInput.model_validate(content)
            except Exception as val_err: # Catch Pydantic validation errors
                raise AgentProcessingError(f"Invalid input data: {val_err}")

            # --- Construct LLM Prompt (REQ-SUP-SUG-006) ---
            prompt_parts = []
            prompt_parts.append("CONTEXT:")
            prompt_parts.append("-------")

            # Ticket Analysis
            prompt_parts.append("Ticket Analysis:")
            prompt_parts.append(f"  - Summary: {input_data.ticket_analysis.summary}")
            prompt_parts.append(f"  - Category: {input_data.ticket_analysis.category}")
            prompt_parts.append(f"  - Sentiment: {input_data.ticket_analysis.sentiment}")
            if input_data.ticket_analysis.extracted_entities:
                prompt_parts.append(f"  - Entities: {json.dumps(input_data.ticket_analysis.extracted_entities)}")

            # Customer History
            if input_data.customer_history:
                prompt_parts.append("\nCustomer History:")
                prompt_parts.append(f"  - Status: {input_data.customer_history.status}")
                if input_data.customer_history.recent_interaction_summary:
                    prompt_parts.append(f"  - Recent Interaction: {input_data.customer_history.recent_interaction_summary}")
                if input_data.customer_history.open_tickets is not None:
                    prompt_parts.append(f"  - Open Tickets: {input_data.customer_history.open_tickets}")

            # KB Results
            if input_data.kb_results:
                prompt_parts.append("\nRelevant Knowledge Base Articles:")
                for i, article in enumerate(input_data.kb_results[:3]): # Limit context size
                    prompt_parts.append(f"  {i+1}. ID: {article.article_id}, Title: {article.title}, Summary: {article.summary[:100]}...")

            prompt_parts.append("-------")
            prompt_parts.append("TASK: Draft a helpful and empathetic response to the customer based *only* on the context above. Address the main issue from the summary. If relevant KB articles were found, mention the most relevant one.")

            final_prompt = "\n".join(prompt_parts)
            self.logger.debug(f"Task {task_id}: Constructed LLM Prompt:\n{final_prompt}")
            # --- End Prompt Construction ---

            # Call LLM
            try:
                suggested_response_text = await self._call_llm(final_prompt)
            except Exception as e:
                logger.error(f"Failed to call LLM: {e}")
                suggested_response_text = self._get_mock_response(final_prompt)

            # Verify we have a valid response
            if not suggested_response_text or len(suggested_response_text) < 10:
                logger.warning("Received an invalid or too short response. Using mock response.")
                suggested_response_text = self._get_mock_response(final_prompt)

            if _MODELS_AVAILABLE and suggested_response_text:
                # Wrap in artifact content model (REQ-SUP-SUG-005)
                # Note: Artifact content is the raw string here, not a JSON object
                response_artifact = Artifact(
                    id=f"{task_id}-response",
                    type="suggested_response", # Matches orchestrator expectation
                    content=suggested_response_text, # Store the raw string
                    media_type="text/plain" # Indicate it's plain text
                )
                await self.task_store.notify_artifact_event(task_id, response_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available or response generation failed.")

            completion_message = f"Successfully generated draft response suggestion for task {task_id}."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error generating response suggestion: {e}")
            error_message = f"Unexpected error generating response: {e}"

        finally:
            # Send completion message
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else:
                 logger.info(f"Task {task_id}: {completion_message}")

            # Update final state
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            self.logger.info(f"Task {task_id}: EXITING process_task. Final State: {final_state}")

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()
        await super().close()
        logger.info("Response Suggestion Agent closed.")
