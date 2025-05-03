import logging
import asyncio
import json
import os
import random
from typing import Dict, Any, Union, Optional, List

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

# Import models from this agent's models.py
from .models import TrendingData, TrendingDataArtifactContent

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in trend_analysis_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/ecommerce-trend-analysis"

class TrendAnalysisAgent(ResearchAgent):
    """
    Identifies trending products or categories (currently uses mock data).
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Trend Analysis Agent"})
        # Placeholder for potential DB pool or API client for real data
        # self._db_pool = None
        # self._api_client = httpx.AsyncClient(...)

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Analyzes trends based on timeframe and optional category.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing trend analysis request.")
        trending_data_obj = None
        final_state = TaskState.FAILED
        error_message = "Failed to analyze trends."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            timeframe = content.get("timeframe", "7d") # Default to 7 days
            category = content.get("category")
            limit = content.get("limit", 10)

            self.logger.info(f"Task {task_id}: Analyzing trends for timeframe='{timeframe}', category='{category}', limit={limit}")

            # --- Mock Logic ---
            await asyncio.sleep(0.7) # Simulate analysis time

            # Generate mock trending data
            mock_products = [f"prod_trend_{i}" for i in range(random.randint(3, limit))]
            mock_categories = random.sample(["electronics", "books", "home", "fashion", "sports"], k=random.randint(1, 3))
            if category: # If category provided, ensure it's included
                if category not in mock_categories:
                    mock_categories.pop(0)
                    mock_categories.insert(0, category)

            trending_data_obj = TrendingData(
                timeframe=timeframe,
                trending_products=mock_products,
                trending_categories=mock_categories
            )
            # --- End Mock Logic ---

            if _MODELS_AVAILABLE:
                artifact_content = TrendingDataArtifactContent(trending_data=trending_data_obj).model_dump(mode='json')
                trend_artifact = Artifact(
                    id=f"{task_id}-trends", type="trending_data",
                    content=artifact_content,
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, trend_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")

            completion_message = f"Trend analysis complete for timeframe '{timeframe}'. Found {len(mock_products)} trending products and {len(mock_categories)} categories."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error: {e}")
            error_message = f"Unexpected error during trend analysis: {e}"

        finally:
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else:
                 logger.info(f"Task {task_id}: {completion_message}")

            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            self.logger.info(f"Task {task_id}: EXITING process_task. Final State: {final_state}")

    async def close(self):
        """Close any resources like DB pools or API clients."""
        # if self._db_pool: await self._db_pool.close()
        # if self._api_client: await self._api_client.aclose()
        await super().close()
