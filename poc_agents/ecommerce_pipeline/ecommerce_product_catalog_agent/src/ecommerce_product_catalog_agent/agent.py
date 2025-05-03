import logging
import asyncio
import json
import os
import random
from typing import Dict, Any, Union, Optional, List

import httpx # Assuming API interaction might be needed later

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
from .models import ProductDetail, ProductDetailsArtifactContent

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in product_catalog_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/ecommerce-product-catalog"

class ProductCatalogAgent(ResearchAgent):
    """
    Retrieves product details based on IDs or search terms.
    (Currently uses mock data).
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Product Catalog Agent"})
        # Placeholder for potential DB pool or API client
        # self._db_pool = None
        # self._api_client = httpx.AsyncClient(...)

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Fetches product details based on product_ids or search_term.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing product catalog request.")
        product_details_list = []
        final_state = TaskState.FAILED
        error_message = "Failed to retrieve product details."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            product_ids = content.get("product_ids")
            search_term = content.get("search_term")

            if not product_ids and not search_term:
                raise AgentProcessingError("Input must contain either 'product_ids' (list) or 'search_term' (string).")
            if product_ids and not isinstance(product_ids, list):
                 raise AgentProcessingError("'product_ids' must be a list of strings.")
            if search_term and not isinstance(search_term, str):
                 raise AgentProcessingError("'search_term' must be a string.")

            self.logger.info(f"Task {task_id}: Input - IDs={product_ids}, Term='{search_term}'")

            # --- Mock Logic ---
            await asyncio.sleep(0.5) # Simulate lookup time
            if product_ids:
                for pid in product_ids:
                    if not isinstance(pid, str): continue # Skip invalid IDs
                    product_details_list.append(ProductDetail(
                        product_id=pid,
                        name=f"Mock Product {pid}",
                        description=f"Description for mock product {pid}.",
                        price=round(random.uniform(10, 200), 2),
                        category=random.choice(["electronics", "books", "clothing", "home"]),
                        tags=[random.choice(["sale", "new", "popular"]), "mock"],
                        stock_level=random.randint(0, 100)
                    ))
            elif search_term:
                # Generate a few mock results based on search term
                for i in range(random.randint(1, 5)):
                     pid = f"search-{search_term[:5]}-{i}"
                     product_details_list.append(ProductDetail(
                        product_id=pid,
                        name=f"Mock Search Result {i+1} for '{search_term}'",
                        description=f"Found based on search for '{search_term}'.",
                        price=round(random.uniform(5, 50), 2),
                        category=random.choice(["search_related", "general"]),
                        tags=[search_term.lower(), "mock_search"],
                        stock_level=random.randint(0, 50)
                    ))
            # --- End Mock Logic ---

            if _MODELS_AVAILABLE:
                artifact_content = ProductDetailsArtifactContent(product_details=product_details_list).model_dump(mode='json')
                details_artifact = Artifact(
                    id=f"{task_id}-details", type="product_details",
                    content=artifact_content,
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, details_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")

            completion_message = f"Retrieved {len(product_details_list)} product details."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error: {e}")
            error_message = f"Unexpected error retrieving product details: {e}"

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
