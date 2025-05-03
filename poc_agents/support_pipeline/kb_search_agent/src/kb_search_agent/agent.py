import logging
import asyncio
import json
import os
import random
from typing import Dict, Any, Union, Optional, List
from pathlib import Path

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

# Import models from this agent's models.py (REQ-SUP-KBS-004, 005, 006)
from .models import KnowledgeBaseArticle, KBSearchInput, KBSearchResultsArtifactContent

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in kb_search_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/support-kb-search" # REQ-SUP-KBS-002

# Load the mock KB data from the JSON file
def load_mock_kb_data():
    try:
        kb_data_path = Path('/app/src/kb_search_agent/mock_kb_data.json')
        # If running locally (not in container)
        if not kb_data_path.exists():
            kb_data_path = Path(__file__).parent.parent.parent.parent / 'mock_kb_data.json'
        
        if kb_data_path.exists():
            with open(kb_data_path, 'r') as file:
                return json.load(file)
        else:
            logger.warning(f"Could not find mock KB data at {kb_data_path}. Using fallback data.")
            return FALLBACK_KB
    except Exception as e:
        logger.error(f"Error loading mock KB data: {e}. Using fallback data.")
        return FALLBACK_KB

# Fallback KB Data (in case JSON file can't be loaded)
FALLBACK_KB = {
    "Billing": [
        {"article_id": "kb-bill-01", "title": "How to View Your Invoice", "summary": "Log in to your account portal and navigate to the Billing section..."},
        {"article_id": "kb-bill-02", "title": "Update Payment Method", "summary": "Go to Account Settings > Payment Methods to add or update your card..."},
        {"article_id": "kb-bill-03", "title": "Understanding Charges", "summary": "Your monthly charge includes the base plan fee plus any add-ons..."}
    ],
    "Technical": [
        {"article_id": "kb-tech-01", "title": "Troubleshooting Widget Pro Connection", "summary": "Ensure your Widget Pro is connected to Wi-Fi and restart the device..."},
        {"article_id": "kb-tech-02", "title": "Resetting Your Password", "summary": "Click the 'Forgot Password' link on the login page..."},
        {"article_id": "kb-tech-03", "title": "Common Error Codes", "summary": "Error E-101 means..., Error E-205 means..."}
    ],
    "Sales": [
        {"article_id": "kb-sale-01", "title": "Feature Comparison: Basic vs Pro", "summary": "The Pro plan includes advanced analytics, priority support..."},
        {"article_id": "kb-sale-02", "title": "Requesting a Demo", "summary": "Fill out the demo request form on our website..."}
    ],
    "General Inquiry": [
        {"article_id": "kb-gen-01", "title": "Contacting Support", "summary": "You can reach support via chat, email, or phone during business hours..."},
        {"article_id": "kb-gen-02", "title": "Terms of Service", "summary": "Please review our terms of service located at..."}
    ]
}

# Load the mock KB data
MOCK_KB = load_mock_kb_data()

class KnowledgeBaseSearchAgent(ResearchAgent): # REQ-SUP-KBS-001
    """
    Searches a mock knowledge base for relevant articles based on category.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Knowledge Base Search Agent"})
        self.logger.info("Knowledge Base Search Agent initialized with mock implementation")

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Searches mock KB based on category. REQ-SUP-KBS-007.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing KB search request.")
        kb_results_list: List[KnowledgeBaseArticle] = []
        final_state = TaskState.FAILED
        error_message = "Failed to search knowledge base."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # Validate input using Pydantic model (REQ-SUP-KBS-004)
            try:
                input_data = KBSearchInput.model_validate(content)
            except Exception as val_err: # Catch Pydantic validation errors
                raise AgentProcessingError(f"Invalid input data: {val_err}")

            category = input_data.category
            keywords = input_data.keywords # Optional
            limit = input_data.limit
            self.logger.info(f"Task {task_id}: Searching KB for category='{category}', keywords={keywords}, limit={limit}")

            # --- Mock Search Logic (REQ-SUP-KBS-007) ---
            await asyncio.sleep(0.2) # Simulate search time

            # Get articles for the category, default to General if category unknown
            mock_articles_raw = MOCK_KB.get(category, MOCK_KB.get("General Inquiry", []))
            
            # Log the available categories and the chosen one
            available_categories = list(MOCK_KB.keys())
            self.logger.info(f"Task {task_id}: Available KB categories: {available_categories}")
            self.logger.info(f"Task {task_id}: Selected category '{category}' with {len(mock_articles_raw)} articles")

            # Convert raw mock data to Pydantic models and assign scores
            for article_data in mock_articles_raw:
                # Simple relevance: higher if keywords match summary (mock)
                score = 0.6 # Base score
                if keywords:
                    summary_lower = article_data.get("summary", "").lower()
                    if any(kw.lower() in summary_lower for kw in keywords):
                        score += 0.25
                score = min(round(score + random.uniform(-0.05, 0.05), 2), 1.0) # Add jitter

                kb_results_list.append(KnowledgeBaseArticle(
                    article_id=article_data.get("article_id", f"kb-unknown-{random.randint(100,999)}"),
                    title=article_data.get("title", "Unknown Article"),
                    summary=article_data.get("summary", "No summary available."),
                    relevance_score=score
                ))

            # Sort by relevance (descending) and limit results
            kb_results_list.sort(key=lambda x: x.relevance_score or 0.0, reverse=True)
            kb_results_list = kb_results_list[:limit]
            # --- End Mock Logic ---

            if _MODELS_AVAILABLE:
                # Wrap in artifact content model (REQ-SUP-KBS-006)
                artifact_content = KBSearchResultsArtifactContent(kb_results=kb_results_list).model_dump(mode='json')
                kb_artifact = Artifact(
                    id=f"{task_id}-kb",
                    type="kb_results", # Matches orchestrator expectation
                    content=artifact_content,
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, kb_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")

            completion_message = f"KB search complete for category '{category}'. Found {len(kb_results_list)} relevant articles."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error during KB search: {e}")
            error_message = f"Unexpected error during KB search: {e}"

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
        """Close any resources (none needed for mock)."""
        await super().close()
        logger.info("Knowledge Base Search Agent mock implementation closed.")
