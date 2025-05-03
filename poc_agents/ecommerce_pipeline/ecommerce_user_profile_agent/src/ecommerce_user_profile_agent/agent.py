import logging
import asyncio
import json
import os
import datetime
from typing import Dict, Any, Union, Optional

# Import base class and SDK components relative to the expected execution context
# Assuming base_agent.py is copied to the root level in the Docker image
try:
    from base_agent import ResearchAgent # Import from potentially copied base agent
except ImportError:
    # Fallback if base_agent isn't directly available (e.g., running locally without copy)
    try:
         # Try importing relative to the monorepo structure if running locally
         from ...research_pipeline.base_agent import ResearchAgent
    except ImportError:
        # Last resort: Define a placeholder if absolutely necessary
        logging.getLogger(__name__).critical("Could not import BaseA2AAgent. Agent will not function.")
        class ResearchAgent: # type: ignore
             def __init__(self, *args, **kwargs): pass
             async def process_task(self, task_id, content): pass
             task_store = None # type: ignore

from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError

# Import models from this agent's models.py
from .models import UserProfile, UserPreferences, UserProfileArtifactContent

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in user_profile_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/ecommerce-user-profile"

class UserProfileAgent(ResearchAgent):
    """
    Provides user profile data for e-commerce recommendations.
    Mock implementation for testing.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "User Profile Agent"})
        # Mock implementation doesn't need database connection
        self.logger.info("User Profile Agent initialized with mock implementation")

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Creates a mock user profile based on user_id from the input content.
        This is a mock implementation that doesn't use a database.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing user profile request.")
        user_profile_data = None
        final_state = TaskState.FAILED
        error_message = "Failed to retrieve user profile."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            user_id = content.get("user_id")
            if not user_id or not isinstance(user_id, str):
                raise AgentProcessingError("Missing or invalid 'user_id' in input content.")

            self.logger.info(f"Task {task_id}: Creating mock profile for user_id '{user_id}'.")            
            
            # --- Mock Profile Data ---
            mock_categories = ["electronics", "books", "clothing"]
            mock_brands = ["brand-a", "brand-b", "brand-c"]
            mock_purchase_history = [f"product-{i}" for i in range(1, 6)]
            mock_browsing_history = [f"product-{i}" for i in range(10, 20)]
            
            # Create mock user profile
            user_profile_data = UserProfile(
                user_id=user_id,
                purchase_history=mock_purchase_history,
                browsing_history=mock_browsing_history,
                preferences=UserPreferences(
                    categories=mock_categories,
                    brands=mock_brands
                ),
                last_active=datetime.datetime.now()
            )

            if _MODELS_AVAILABLE:
                artifact_content = UserProfileArtifactContent(user_profile=user_profile_data).model_dump(mode='json')
                profile_artifact = Artifact(
                    id=f"{task_id}-profile", type="user_profile",
                    content=artifact_content, # Store the dict content
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, profile_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")

            completion_message = f"Successfully created mock profile for user '{user_id}'."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error: {e}")
            error_message = f"Unexpected error retrieving profile: {e}"

        finally:
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else:
                 logger.info(f"Task {task_id}: {completion_message}")

            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            self.logger.info(f"Task {task_id}: EXITING process_task. Final State: {final_state}")

    async def close(self):
        """Close any resources."""
        await super().close()
        logger.info("User Profile Agent mock implementation closed.")
