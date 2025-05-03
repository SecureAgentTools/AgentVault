import logging
import asyncio
import json
import os
import random
from typing import Dict, Any, Union, Optional
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

# Import models from this agent's models.py (REQ-SUP-HIS-004, 005, 006)
from .models import CustomerHistorySummary, CustomerHistoryInput, CustomerHistoryArtifactContent

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in customer_history_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/support-customer-history" # REQ-SUP-HIS-002

# Load the mock customer data from the JSON file
def load_mock_customer_data():
    try:
        customer_data_path = Path('/app/src/customer_history_agent/mock_customer_data.json')
        # If running locally (not in container)
        if not customer_data_path.exists():
            customer_data_path = Path(__file__).parent.parent.parent.parent / 'mock_customer_data.json'
        
        if customer_data_path.exists():
            with open(customer_data_path, 'r') as file:
                return json.load(file)
        else:
            logger.warning(f"Could not find mock customer data at {customer_data_path}. Using fallback data.")
            return {}
    except Exception as e:
        logger.error(f"Error loading mock customer data: {e}. Using fallback data.")
        return {}

# Load the mock customer data
MOCK_CUSTOMER_DATA = load_mock_customer_data()

class CustomerHistoryAgent(ResearchAgent): # REQ-SUP-HIS-001
    """
    Retrieves mock customer history and status summary.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Customer History Agent"})
        self.logger.info("Customer History Agent initialized with mock implementation")

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Generates mock customer history based on identifier. REQ-SUP-HIS-007.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing customer history request.")
        history_result: Optional[CustomerHistorySummary] = None
        final_state = TaskState.FAILED
        error_message = "Failed to retrieve customer history."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # Validate input using Pydantic model (REQ-SUP-HIS-004)
            try:
                input_data = CustomerHistoryInput.model_validate(content)
            except Exception as val_err: # Catch Pydantic validation errors
                raise AgentProcessingError(f"Invalid input data: {val_err}")

            customer_id = input_data.customer_identifier
            self.logger.info(f"Task {task_id}: Retrieving mock history for customer '{customer_id}'.")

            # --- Mock History Logic (REQ-SUP-HIS-007) ---
            await asyncio.sleep(0.15) # Simulate lookup time

            self.logger.info(f"Task {task_id}: Looking up customer '{customer_id}' in mock data")
            self.logger.info(f"Task {task_id}: Available customer records: {list(MOCK_CUSTOMER_DATA.keys())}")
            
            # Use the mock data if it exists for this customer
            if customer_id in MOCK_CUSTOMER_DATA:
                customer_record = MOCK_CUSTOMER_DATA[customer_id]
                self.logger.info(f"Task {task_id}: Found customer record: {customer_record}")
                
                status = customer_record.get("status", "Standard")
                summary = customer_record.get("recent_interaction_summary", "No recent interactions recorded.")
                open_tickets = customer_record.get("open_tickets", 0)
            else:
                # Fallback to generated mock data if customer not found
                self.logger.info(f"Task {task_id}: Customer '{customer_id}' not found in mock data. Using fallback logic.")
                status = "Standard"
                summary = "No recent significant interactions."
                open_tickets = random.choice([0, 1])

                if customer_id.endswith("1") or "vip" in customer_id.lower():
                    status = "VIP"
                    summary = "Recent large purchase resolved successfully."
                    open_tickets = 0
                elif customer_id.endswith("2"):
                    status = "Standard"
                    summary = "Contacted support last month regarding billing."
                    open_tickets = 1
                elif "new" in customer_id.lower():
                     status = "New"
                     summary = "First interaction."
                     open_tickets = 0 # Usually 0 for new
                elif customer_id.endswith("9"):
                     status = "Churn Risk"
                     summary = "Multiple technical issues reported recently."
                     open_tickets = 2

            history_result = CustomerHistorySummary(
                customer_identifier=customer_id,
                status=status,
                recent_interaction_summary=summary,
                open_tickets=open_tickets
            )
            # --- End Mock Logic ---

            if _MODELS_AVAILABLE and history_result:
                # Wrap in artifact content model (REQ-SUP-HIS-006)
                artifact_content = CustomerHistoryArtifactContent(customer_history=history_result).model_dump(mode='json')
                history_artifact = Artifact(
                    id=f"{task_id}-history",
                    type="customer_history", # Matches orchestrator expectation
                    content=artifact_content,
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, history_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available or history lookup failed.")

            completion_message = f"Retrieved mock history for customer '{customer_id}'. Status: {status}."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error retrieving customer history: {e}")
            error_message = f"Unexpected error retrieving history: {e}"

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
        logger.info("Customer History Agent mock implementation closed.")
