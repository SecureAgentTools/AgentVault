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
    logging.getLogger(__name__).warning("Core agentvault models not found in content_synthesis_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState # Use state from base if possible
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "content-synthesis-agent"

class ContentSynthesisAgent(ResearchAgent):
    """
    Generates a draft article structure and writes content using verified facts.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Content Synthesis Agent"})

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Processes verified facts and research plan/subtopics to generate a draft article.
        Expects 'content' to be a dictionary containing 'verified_facts' artifact content
        and potentially 'research_plan' or 'info_by_subtopic' artifact content.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Processing content synthesis request for task {task_id}")

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # --- MODIFIED: Access facts nested within 'verified_facts' artifact content ---
            verified_facts_artifact_content: Dict[str, Any] = content.get("verified_facts", {})
            verified_facts: List[Dict[str, Any]] = verified_facts_artifact_content.get("verified_facts", [])
            # --- END MODIFIED ---

            # Access other inputs directly by their artifact type key
            info_by_subtopic: Dict[str, Any] = content.get("info_by_subtopic", {})
            research_plan: Dict[str, Any] = content.get("research_plan", {}) # Get plan if passed

            if not verified_facts:
                # Allow proceeding without facts, maybe just generate structure?
                self.logger.warning(f"Task {task_id}: No 'verified_facts' provided in input. Attempting structure generation only.")
                # If facts are strictly required, uncomment the line below:
                # raise AgentProcessingError("Missing 'verified_facts' list within the 'verified_facts' input artifact content.")

            subtopics = research_plan.get("subtopics", list(info_by_subtopic.keys()))
            main_topic = research_plan.get("main_topic", "Research Topic")

            self.logger.info(f"Task {task_id}: Synthesizing content for topic '{main_topic}' with {len(verified_facts)} verified facts and {len(subtopics)} subtopics.")

            # --- Placeholder Logic ---
            draft_content_md = f"# Draft Article: {main_topic}\n\n"
            draft_content_md += "## Introduction\n\nThis is an introductory paragraph placeholder.\n\n"

            bibliography = {}
            fact_counter = 0

            for i, subtopic in enumerate(subtopics):
                draft_content_md += f"## {subtopic}\n\n"
                draft_content_md += f"This section discusses {subtopic}. (Placeholder text)\n\n"

                relevant_facts = [f for f in verified_facts if subtopic in f.get("text", "")]
                if not relevant_facts and verified_facts:
                    relevant_facts = verified_facts[fact_counter : fact_counter + 2]
                    fact_counter = (fact_counter + 2) % len(verified_facts) if verified_facts else 0

                for fact in relevant_facts:
                    fact_text = fact.get('text', 'Missing fact text.')
                    source_url = fact.get('source_url', 'No source')
                    confidence = fact.get('confidence_score', 'N/A')
                    citation_id = f"ref-{i}-{fact.get('id', random.randint(100,999))}"

                    draft_content_md += f"According to sources, {fact_text} [^{citation_id}]. (Confidence: {confidence})\n"
                    bibliography[citation_id] = {
                        "source_url": source_url,
                        "retrieved": fact.get("verification_timestamp", "N/A")
                    }

                draft_content_md += "\n"

            draft_content_md += "## Conclusion\n\nThis is a concluding paragraph placeholder.\n\n"

            draft_content_md += "## References\n\n"
            for ref_id, ref_data in bibliography.items():
                draft_content_md += f"[^{ref_id}]: {ref_data['source_url']} (Retrieved: {ref_data['retrieved']})\n"

            await asyncio.sleep(3)
            # --- End Placeholder Logic ---

            # Notify artifacts
            if _MODELS_AVAILABLE:
                # Draft Article Artifact
                draft_artifact = Artifact(
                    id=f"{task_id}-draft_article", type="draft_article",
                    content=draft_content_md, media_type="text/markdown"
                )
                await self.task_store.notify_artifact_event(task_id, draft_artifact)

                # Bibliography Artifact
                bib_artifact = Artifact(
                    id=f"{task_id}-bibliography", type="bibliography",
                    content=bibliography, media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, bib_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")


            # Notify completion message
            completion_message = f"Generated draft article ({len(draft_content_md)} chars) with {len(bibliography)} references."
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else:
                 logger.info(completion_message)

            await self.task_store.update_task_state(task_id, TaskState.COMPLETED)
            self.logger.info(f"Successfully processed content synthesis for task {task_id}")

        except Exception as e:
            self.logger.exception(f"Error processing content synthesis for task {task_id}: {e}")
            error_message = f"Failed to process content synthesis: {e}"
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
agent = ContentSynthesisAgent()

# Create FastAPI app
app = FastAPI(title="ContentSynthesisAgent")

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
