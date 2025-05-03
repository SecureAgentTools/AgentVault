import logging
import asyncio
import json
import os
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
from pathlib import Path
import uuid

import asyncpg
import httpx

# LLM Integration
LLM_API_URL = os.environ.get("LLM_API_URL", "http://host.docker.internal:1234/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "lm-studio")

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import TransformInput, TransformOutput, TransformedData, TransformedDataArtifact

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found. Using placeholders.")
    # Define placeholders on separate lines (CORRECTED AGAIN)
    class Message: pass
    class TextPart: pass
    class Artifact: pass
    class DataPart: pass
    class TaskState:
        SUBMITTED = "SUBMITTED"; WORKING = "WORKING"; INPUT_REQUIRED = "INPUT_REQUIRED"
        COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELED = "CANCELED"
    class Task: pass
    class A2AEvent: pass
    _MODELS_AVAILABLE = False # type: ignore

TaskStateEnum = TaskState if _MODELS_AVAILABLE else SdkTaskState

logger = logging.getLogger(__name__)
AGENT_ID = "local-poc/etl-data-transformer"
DB_HOST = os.environ.get("DATABASE_HOST", "etl-db"); DB_PORT = os.environ.get("DATABASE_PORT", 5432)
DB_USER = os.environ.get("DATABASE_USER"); DB_PASSWORD = os.environ.get("DATABASE_PASSWORD"); DB_NAME = os.environ.get("DATABASE_NAME")
db_config_valid = all([DB_USER, DB_PASSWORD, DB_NAME])
if not db_config_valid: logger.error("DB connection details missing.")

class DataTransformerAgent(BaseA2AAgent):
    def __init__(self):
        super().__init__(agent_metadata={"name": "Data Transformer Agent"})
        self.db_pool: Optional[asyncpg.Pool] = None
        self.db_config_valid = db_config_valid
        self.task_store: Optional[Any] = None
        logger.info(f"Data Transformer Agent initialized. DB Config Valid: {self.db_config_valid}")
        
    async def call_llm(self, prompt: str, system_prompt: str = None) -> str:
        """Call the LLM API with the given prompt."""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LLM_API_KEY}"
            }
            
            payload = {
                "model": "openhermes" if "openhermes" in LLM_API_URL else "llama3",
                "messages": []
            }
            
            if system_prompt:
                payload["messages"].append({"role": "system", "content": system_prompt})
                
            payload["messages"].append({"role": "user", "content": prompt})
            
            logger.info(f"Calling LLM API at: {LLM_API_URL}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{LLM_API_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120.0
                )
                
                if response.status_code != 200:
                    logger.error(f"LLM API error: {response.status_code} - {response.text}")
                    return f"Error: {response.status_code}"
                    
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "No response")
                
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return f"Error: {str(e)}"

    async def _get_db_pool(self) -> asyncpg.Pool:
        if not self.db_config_valid: raise ConfigurationError("DB not configured.")
        if self.db_pool is None:
            logger.info(f"Creating DB pool for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
            try:
                self.db_pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASSWORD, database=DB_NAME, host=DB_HOST, port=DB_PORT, min_size=1, max_size=5)
                logger.info("DB pool created.")
            except Exception as e: logger.exception(f"Failed to create DB pool: {e}"); raise ConfigurationError(f"DB connection failed: {e}") from e
        return self.db_pool # type: ignore

    async def _fetch_list_artifact_data(self, artifact_db_id: int) -> List[Dict[str, Any]]:
        pool = await self._get_db_pool()
        async with pool.acquire() as connection:
            try:
                record = await connection.fetchrow("SELECT artifact_data FROM pipeline_artifacts WHERE id = $1", artifact_db_id)
                if not record: raise AgentProcessingError(f"Artifact ID {artifact_db_id} not found.")
                raw_db_data = record['artifact_data']
                if isinstance(raw_db_data, str):
                    try: data = json.loads(raw_db_data)
                    except json.JSONDecodeError as json_err: raise AgentProcessingError(f"Failed to parse JSON string from DB for artifact ID {artifact_db_id}: {json_err}") from json_err
                elif isinstance(raw_db_data, (list, dict)): data = raw_db_data
                else: raise AgentProcessingError(f"Unexpected data type ({type(raw_db_data).__name__}) fetched from DB for artifact ID {artifact_db_id}.")
                if not isinstance(data, list): raise AgentProcessingError(f"Deserialized artifact data ID {artifact_db_id} is not a list (type: {type(data).__name__}).")
                logger.info(f"Fetched and parsed list artifact data ID {artifact_db_id}. Rows: {len(data)}")
                return data
            except AgentProcessingError: raise
            except Exception as e: logger.exception(f"DB error fetching/parsing artifact ID {artifact_db_id}: {e}"); raise AgentProcessingError(f"DB error fetching/parsing artifact: {e}") from e

    async def _insert_artifact(self, run_id: str, step_name: str, artifact_type: str, data: List[Dict[str, Any]]) -> int:
        pool = await self._get_db_pool(); serialized_data = json.dumps(data)
        async with pool.acquire() as conn:
            try:
                result = await conn.fetchrow("INSERT INTO pipeline_artifacts (run_id, step_name, artifact_type, artifact_data) VALUES ($1, $2, $3, $4::jsonb) RETURNING id", run_id, step_name, artifact_type, serialized_data)
                if result and 'id' in result: artifact_db_id = result['id']; logger.info(f"Inserted artifact '{artifact_type}' run '{run_id}'. DB ID: {artifact_db_id}"); return artifact_db_id
                else: raise AgentProcessingError("Failed to retrieve DB ID after insert.")
            except Exception as e: logger.exception(f"DB error inserting artifact '{artifact_type}' run '{run_id}': {e}"); raise AgentProcessingError(f"DB error inserting artifact: {e}") from e

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: asyncio.Task = None) -> str:
        if task_id: raise AgentProcessingError(f"Transformer agent does not support continuing task {task_id}")
        new_task_id = f"etl-transform-{uuid.uuid4().hex[:8]}"
        logger.info(f"Task {new_task_id}: Received transformation request.")
        if not self.task_store: raise ConfigurationError("Task store not initialized.")
        await self.task_store.create_task(new_task_id)
        input_content = None
        if _MODELS_AVAILABLE and message.parts:
            for part in message.parts:
                if isinstance(part, DataPart): input_content = part.content; break
        if not isinstance(input_content, dict):
             await self.task_store.update_task_state(new_task_id, TaskStateEnum.FAILED, "Invalid input: Expected DataPart dict.")
             raise AgentProcessingError("Invalid input: Expected DataPart dict.")
        if background_tasks: background_tasks.add_task(self.process_task, new_task_id, input_content) # type: ignore
        else: asyncio.create_task(self.process_task(new_task_id, input_content))
        return new_task_id

    async def process_task(self, task_id: str, content: Dict[str, Any]):
        if not self.task_store: logger.error(f"Task {task_id}: Task store missing."); return
        await self.task_store.update_task_state(task_id, TaskStateEnum.WORKING)
        logger.info(f"Task {task_id}: Background processing started.")
        artifact_db_id: Optional[int] = None; rows_transformed = 0
        final_state = TaskStateEnum.FAILED; error_message = "Failed transformation."; completion_message = error_message
        try:
            if not self.db_config_valid: raise ConfigurationError("DB not configured.")
            try: input_data = TransformInput.model_validate(content)
            except Exception as val_err: raise AgentProcessingError(f"Invalid input: {val_err}")
            raw_artifact_id = input_data.raw_data_artifact_id; run_id = input_data.run_id
            logger.info(f"Task {task_id}: Transforming artifact ID {raw_artifact_id} run '{run_id}'.")
            raw_data = await self._fetch_list_artifact_data(raw_artifact_id)
            # First, do basic transformations to prepare data
            basic_transformed_data: List[Dict[str, Any]] = []
            for row in raw_data:
                new_row = {"Item ID": row.get("ProductID"), "Item Name": row.get("ProductName"), "Type": row.get("Category"), "Price": row.get("UnitPrice")}
                try: price_str = new_row.get("Price"); new_row["Price"] = float(price_str) if price_str is not None else None
                except (ValueError, TypeError): logger.warning(f"Task {task_id}: Price conversion failed ID '{new_row.get('Item ID')}'. Setting None."); new_row["Price"] = None
                if new_row["Item ID"] is not None and new_row["Item Name"] is not None: basic_transformed_data.append(new_row)
                else: logger.warning(f"Task {task_id}: Skipping row missing ID/Name: {row}")

            # Use LLM to enhance the data with additional insights
            logger.info(f"Task {task_id}: Enhancing data with LLM")
            transformed_data_list = basic_transformed_data.copy()
            
            # Sample a few rows to send to the LLM
            sample_rows = basic_transformed_data[:5]  # Limit to first 5 for prompt size
            
            # Prepare system prompt
            system_prompt = (
                "You are an expert data transformer for e-commerce product data. "
                "Your task is to enhance product data with additional fields and insights."
            )
            
            # Build user prompt
            prompt = f"""
            I need to enrich the following product data with additional insights.
            Here are sample rows from my dataset:
            
            {json.dumps(sample_rows, indent=2)}
            
            For each product, please suggest:
            1. A 'Popularity' score (0-100)
            2. A 'Target Audience' field (who this product is best for)
            3. A 'Display Category' that might be more user-friendly than the existing Type
            
            Return your suggestions as JSON with these fields for each sample product ID.
            """
            
            # Call the LLM
            try:
                llm_response = await self.call_llm(prompt, system_prompt)
                logger.info(f"Task {task_id}: Received LLM response")
                
                # Try to extract JSON from the response
                try:
                    # Look for JSON in the response
                    json_start = llm_response.find('{')
                    json_end = llm_response.rfind('}') + 1
                    
                    if json_start >= 0 and json_end > json_start:
                        json_str = llm_response[json_start:json_end]
                        enhancements = json.loads(json_str)
                        
                        # Apply enhancements to the transformed data
                        for row in transformed_data_list:
                            item_id = row.get("Item ID")
                            if item_id in enhancements:
                                enhancement = enhancements[item_id]
                                row["Popularity"] = enhancement.get("Popularity", 50)
                                row["Target Audience"] = enhancement.get("Target Audience", "General")
                                row["Display Category"] = enhancement.get("Display Category", row.get("Type", "Misc"))
                        logger.info(f"Task {task_id}: Applied LLM enhancements to the data")
                except Exception as e:
                    logger.warning(f"Task {task_id}: Error parsing LLM response: {e}. Using basic transformations only.")
            except Exception as e:
                logger.warning(f"Task {task_id}: LLM enhancement failed: {e}. Using basic transformations only.")
            
            rows_transformed = len(transformed_data_list)
            logger.info(f"Task {task_id}: Transformed {rows_transformed} rows.")
            artifact_db_id = await self._insert_artifact(run_id, "transform_data", "transformed_data", transformed_data_list)
            output_data = TransformOutput(artifact_db_id=artifact_db_id, rows_transformed=rows_transformed)
            completion_message = f"Transformed {rows_transformed} rows. DB ID: {artifact_db_id}."
            final_state = TaskStateEnum.COMPLETED; error_message = None
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[DataPart(content=output_data.model_dump())])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else: logger.info(f"Task {task_id}: {completion_message} - Output: {output_data.model_dump()}")
        except AgentProcessingError as e: logger.error(f"Task {task_id}: Processing error: {e}"); error_message = str(e)
        except ConfigurationError as e: logger.error(f"Task {task_id}: Config error: {e}"); error_message = str(e)
        except Exception as e: logger.exception(f"Task {task_id}: Unexpected error: {e}"); error_message = f"Unexpected error: {e}"
        finally:
            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            logger.info(f"Task {task_id}: Background processing finished. State: {final_state}")

    async def handle_task_get(self, task_id: str) -> Task:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        if _MODELS_AVAILABLE:
            messages = await self.task_store.get_messages(task_id) or []; artifacts = await self.task_store.get_artifacts(task_id) or []
            return Task(id=task_id, state=context.current_state, createdAt=context.created_at, updatedAt=context.updated_at, messages=messages, artifacts=artifacts) # type: ignore
        else: raise NotImplementedError("Task model not available")

    async def handle_task_cancel(self, task_id: str) -> bool:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
        if context.current_state not in terminal:
            await self.task_store.update_task_state(task_id, TaskStateEnum.CANCELED, "Cancelled by request.")
            return True
        return False

    async def handle_subscribe_request(self, task_id: str) -> AsyncGenerator[A2AEvent, None]:
        if not self.task_store: raise ConfigurationError("Task store missing.")
        q = asyncio.Queue(); await self.task_store.add_listener(task_id, q)
        try:
            while True:
                event = await q.get(); yield event
                context = await self.task_store.get_task(task_id)
                terminal = [TaskStateEnum.COMPLETED, TaskStateEnum.FAILED, TaskStateEnum.CANCELED]
                if context and context.current_state in terminal: break
        except asyncio.CancelledError: logger.info(f"SSE cancelled task {task_id}")
        finally: await self.task_store.remove_listener(task_id, q)

    async def close(self):
        if self.db_pool: logger.info("Closing DB pool..."); await self.db_pool.close(); logger.info("DB pool closed.")
        logger.info("Data Transformer Agent closed.")
