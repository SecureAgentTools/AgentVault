import logging
import asyncio
import json
# --- ADDED: Import List and random ---
from typing import Dict, Any, Union, List
import random
# --- END ADDED ---
import datetime # Added for timestamp

# Import base class and SDK components
from base_agent import ResearchAgent
from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in editor_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState # Use state from base if possible
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "editor-agent"

class EditorAgent(ResearchAgent):
    """
    Reviews draft content for grammar, style, flow, and citation formatting.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Editor Agent"})

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Processes a draft article (likely Markdown) to refine it.
        Expects 'content' to be a dictionary containing the 'draft_article' content (string),
        likely from the Content Synthesis Agent's output artifact.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Processing editing request for task {task_id}")

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # Expecting the draft article artifact structure
            draft_article_md: str = content.get("draft_article", "")

            if not draft_article_md:
                raise AgentProcessingError("Missing 'draft_article' string in input content.")

            self.logger.info(f"Task {task_id}: Editing draft article (length: {len(draft_article_md)} chars).")

            # --- SIMPLIFIED Placeholder Logic ---
            await asyncio.sleep(1.0) # Simulate editing time

            # Just pass the original article through and add a note
            edited_article_md = draft_article_md + "\n\n*Editor's Note: Placeholder edit - no changes applied.*\n"
            edit_suggestions = [{
                    "id": f"edit-{task_id}-0",
                    "type": "placeholder",
                    "original": "N/A",
                    "suggestion": "No edits applied by placeholder agent.",
                    "explanation": "This agent currently passes content through.",
                    "applied": False
                }]
            # --- End SIMPLIFIED Placeholder Logic ---

            # Notify artifacts
            if _MODELS_AVAILABLE:
                # Edited Article Artifact
                edited_article_artifact = Artifact(
                    id=f"{task_id}-edited_article", type="edited_article",
                    content=edited_article_md, media_type="text/markdown"
                )
                await self.task_store.notify_artifact_event(task_id, edited_article_artifact)

                # Edit Suggestions Artifact
                suggestions_artifact = Artifact(
                    id=f"{task_id}-edit_suggestions", type="edit_suggestions",
                    content={"suggestions": edit_suggestions}, media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, suggestions_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")


            # Notify completion message
            completion_message = f"Placeholder edit complete for draft article."
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else:
                 logger.info(completion_message)

            await self.task_store.update_task_state(task_id, TaskState.COMPLETED)
            self.logger.info(f"Successfully processed editing for task {task_id}")

        except Exception as e:
            self.logger.exception(f"Error processing editing for task {task_id}: {e}")
            error_message = f"Failed to process editing: {e}"
            await self.task_store.update_task_state(task_id, TaskState.FAILED, message=error_message)
            if _MODELS_AVAILABLE:
                 error_msg_obj = Message(role="assistant", parts=[TextPart(content=error_message)])
                 await self.task_store.notify_message_event(task_id, error_msg_obj)


# FastAPI app setup
from fastapi import FastAPI, Depends, BackgroundTasks # Added imports
from fastapi.middleware.cors import CORSMiddleware
from agentvault_server_sdk import create_a2a_router
import os

# Create agent instance
agent = EditorAgent()

# Create FastAPI app
app = FastAPI(title="EditorAgent")

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
