import logging
import asyncio
import json
import os
import random
import re # For simple keyword matching
from typing import Dict, Any, Union, Optional

# Import base class and SDK components
try:
    # Assumes base_agent.py is copied to /app in Dockerfile
    from base_agent import ResearchAgent
except ImportError:
    try:
         # Fallback for local execution from monorepo root
         from ...research_pipeline.base_agent import ResearchAgent
    except ImportError:
        logging.getLogger(__name__).critical("Could not import BaseA2AAgent. Agent will not function.")
        class ResearchAgent: # type: ignore
             def __init__(self, *args, **kwargs): pass
             async def process_task(self, task_id, content): pass
             task_store = None # type: ignore

from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError

# Import models from this agent's models.py (REQ-SUP-ANA-004, 005, 006)
from .models import TicketAnalysis, TicketAnalysisInput, TicketAnalysisArtifactContent

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in ticket_analyzer_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/support-ticket-analyzer" # REQ-SUP-ANA-002

class TicketAnalyzerAgent(ResearchAgent): # REQ-SUP-ANA-001
    """
    Analyzes customer support tickets using mock logic for PoC.
    Determines category, sentiment, and extracts basic entities.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Ticket Analyzer Agent"})
        self.logger.info("Ticket Analyzer Agent initialized with mock implementation")

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Analyzes ticket text using simple mock rules. REQ-SUP-ANA-007.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing ticket analysis request.")
        analysis_result: Optional[TicketAnalysis] = None
        final_state = TaskState.FAILED
        error_message = "Failed to analyze ticket."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # Validate input using Pydantic model (REQ-SUP-ANA-004)
            try:
                input_data = TicketAnalysisInput.model_validate(content)
            except Exception as val_err: # Catch Pydantic validation errors
                raise AgentProcessingError(f"Invalid input data: {val_err}")

            ticket_text = input_data.ticket_text.lower() # Lowercase for keyword matching
            customer_id = input_data.customer_identifier
            self.logger.info(f"Task {task_id}: Analyzing ticket for customer '{customer_id}'.")
            self.logger.debug(f"Task {task_id}: Ticket Text: {ticket_text[:200]}...")

            # --- Mock Analysis Logic (REQ-SUP-ANA-007) ---
            await asyncio.sleep(0.3) # Simulate analysis time

            # Mock Summary
            summary = f"Summary for ticket from {customer_id}: {ticket_text[:50]}..."

            # Mock Category Classification
            category = "General Inquiry" # Default
            if any(word in ticket_text for word in ["invoice", "payment", "charge", "refund", "bill", "billing", "cost", "price", "upgrade", "plan"]):
                category = "Billing"
            elif any(word in ticket_text for word in ["error", "broken", "not working", "bug", "fail", "issue", "slow", "disconnecting", "error", "app", "widget", "push notification", "settings", "E-404"]):
                category = "Technical"
            elif any(word in ticket_text for word in ["buy", "purchase", "product", "feature", "upgrade", "discount", "pro", "plan", "standard", "export"]):
                category = "Sales"
            elif any(word in ticket_text for word in ["account", "email", "change", "update", "username"]):
                category = "Account Management"
            elif any(word in ticket_text for word in ["mobile", "app", "android", "ios", "push", "notification"]):
                category = "Mobile App"
            
            # Extract from subject line if available
            if "subject:" in ticket_text:
                subject_match = re.search(r'subject:\s*([^\n]+)', ticket_text, re.IGNORECASE)
                if subject_match:
                    subject = subject_match.group(1).lower()
                    # Refine category based on subject line
                    if any(word in subject for word in ["invoice", "payment", "charge", "refund", "bill", "billing", "cost", "price", "upgrade", "plan"]):
                        category = "Billing"
                    elif any(word in subject for word in ["error", "broken", "not working", "bug", "fail", "issue", "slow", "disconnecting", "error", "e-404"]):
                        category = "Technical"
                    elif any(word in subject for word in ["buy", "purchase", "product", "feature", "upgrade", "discount", "pro", "plan", "standard", "export"]):
                        category = "Sales"
                    elif any(word in subject for word in ["account", "email", "change", "update", "username"]):
                        category = "Account Management"
                    elif any(word in subject for word in ["mobile", "app", "android", "ios", "push", "notification"]):
                        category = "Mobile App"

            # Mock Sentiment Analysis
            sentiment = "Neutral" # Default
            if any(word in ticket_text for word in ["happy", "great", "love", "excellent", "thanks", "perfect"]):
                sentiment = "Positive"
            elif any(word in ticket_text for word in ["angry", "frustrated", "hate", "terrible", "worst", "cancel", "never"]):
                sentiment = "Negative"

            # Mock Entity Extraction
            entities = {"product_names": [], "order_ids": []}
            # Simple regex for potential order IDs (e.g., 5+ digits)
            order_ids = re.findall(r'\b\d{5,}\b', ticket_text)
            if order_ids: entities["order_ids"] = order_ids[:3] # Limit
            # Simple check for common product names (mock)
            if "widget pro" in ticket_text: entities["product_names"].append("Widget Pro")
            if "super hub" in ticket_text: entities["product_names"].append("Super Hub")
            if not entities["product_names"]: entities["product_names"].append("MockProduct") # Default if none found

            analysis_result = TicketAnalysis(
                summary=summary,
                category=category,
                sentiment=sentiment,
                extracted_entities=entities
            )
            # --- End Mock Logic ---

            if _MODELS_AVAILABLE and analysis_result:
                # Wrap in artifact content model (REQ-SUP-ANA-006)
                artifact_content = TicketAnalysisArtifactContent(ticket_analysis=analysis_result).model_dump(mode='json')
                analysis_artifact = Artifact(
                    id=f"{task_id}-analysis",
                    type="ticket_analysis", # Matches orchestrator expectation
                    content=artifact_content,
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, analysis_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available or analysis failed.")

            completion_message = f"Ticket analysis complete for customer '{customer_id}'. Category: {category}, Sentiment: {sentiment}."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error during ticket analysis: {e}")
            error_message = f"Unexpected error during analysis: {e}"

        finally:
            # Send completion message (even on failure)
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
        logger.info("Ticket Analyzer Agent mock implementation closed.")
