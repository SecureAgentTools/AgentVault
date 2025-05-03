import logging
import asyncio
import json
import os
import csv
from typing import Dict, Any, Union, Optional, List, AsyncGenerator # Added AsyncGenerator
from pathlib import Path
import uuid # Added uuid

import asyncpg

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError # Added TaskNotFoundError

# Import models from this agent's models.py
from .models import ExtractInput, ExtractOutput, RawDataArtifact

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent # Added Task, A2AEvent
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found. Using placeholders.")
    # Define placeholders on separate lines (CORRECTED)
    class Message: pass
    class TextPart: pass
    class Artifact: pass
    class DataPart: pass
    class TaskState: # Define TaskState placeholder
        SUBMITTED = "SUBMITTED"; WORKING = "WORKING"; INPUT_REQUIRED = "INPUT_REQUIRED"
        COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELED = "CANCELED"
    class Task: pass # Define Task placeholder
    class A2AEvent: pass # Define A2AEvent placeholder
    _MODELS_AVAILABLE = False # type: ignore

# Use the imported or placeholder TaskState consistently
TaskStateEnum = TaskState if _MODELS_AVAILABLE else SdkTaskState

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/etl-data-extractor"

# --- Database Configuration ---
DB_HOST = os.environ.get("DATABASE_HOST", "etl-db")
DB_PORT = os.environ.get("DATABASE_PORT", 5432)
DB_USER = os.environ.get("DATABASE_USER")
DB_PASSWORD = os.environ.get("DATABASE_PASSWORD")
DB_NAME = os.environ.get("DATABASE_NAME")

db_config_valid = all([DB_USER, DB_PASSWORD, DB_NAME])
if not db_config_valid:
    logger.error("DB connection details missing (DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME).")

class DataExtractorAgent(BaseA2AAgent):
    """Extracts data from CSV, stores raw artifact in DB."""
    def __init__(self):
        super().__init__(agent_metadata={"name": "Data Extractor Agent"})
        self.db_pool: Optional[asyncpg.Pool] = None
        self.db_config_valid = db_config_valid # Use module-level check
        self.task_store: Optional[Any] = None
        logger.info(f"Data Extractor Agent initialized. DB Config Valid: {self.db_config_valid}")

    async def _get_db_pool(self) -> asyncpg.Pool:
        if not self.db_config_valid: raise ConfigurationError("DB not configured.")
        if self.db_pool is None:
            logger.info(f"Creating DB pool for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
            try:
                self.db_pool = await asyncpg.create_pool(
                    user=DB_USER, password=DB_PASSWORD, database=DB_NAME,
                    host=DB_HOST, port=DB_PORT, min_size=1, max_size=5
                )
                logger.info("DB pool created.")
            except Exception as e: logger.exception(f"Failed to create DB pool: {e}"); raise ConfigurationError(f"DB connection failed: {e}") from e
        return self.db_pool # type: ignore

    async def _insert_artifact(self, run_id: str, step_name: str, artifact_type: str, data: List[Dict[str, Any]]) -> int:
        pool = await self._get_db_pool(); serialized_data = json.dumps(data)
        async with pool.acquire() as conn:
            try:
                result = await conn.fetchrow("INSERT INTO pipeline_artifacts (run_id, step_name, artifact_type, artifact_data) VALUES ($1, $2, $3, $4::jsonb) RETURNING id", run_id, step_name, artifact_type, serialized_data)
                if result and 'id' in result: artifact_db_id = result['id']; logger.info(f"Inserted artifact '{artifact_type}' run '{run_id}'. DB ID: {artifact_db_id}"); return artifact_db_id
                else: raise AgentProcessingError("Failed to retrieve DB ID after insert.")
            except Exception as e: logger.exception(f"DB error inserting artifact '{artifact_type}' run '{run_id}': {e}"); raise AgentProcessingError(f"DB error inserting artifact: {e}") from e

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: asyncio.Task = None) -> str:
        if task_id: raise AgentProcessingError(f"Extractor agent does not support continuing task {task_id}")
        new_task_id = f"etl-extract-{uuid.uuid4().hex[:8]}"
        logger.info(f"Task {new_task_id}: Received extraction request.")
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
        artifact_db_id: Optional[int] = None; rows_extracted = 0
        final_state = TaskStateEnum.FAILED; error_message = "Failed extraction."; completion_message = error_message
        try:
            if not self.db_config_valid: raise ConfigurationError("DB not configured.")
            try: input_data = ExtractInput.model_validate(content)
            except Exception as val_err: raise AgentProcessingError(f"Invalid input: {val_err}")
            source_path = Path(input_data.source_path); run_id = input_data.run_id
            logger.info(f"Task {task_id}: Extracting from '{source_path}' run '{run_id}'.")
            if not source_path.is_file(): raise AgentProcessingError(f"Source file not found: {source_path}")
            extracted_data: List[Dict[str, Any]] = []
            try:
                with open(source_path, mode='r', encoding='utf-8-sig') as csvfile:
                    reader = csv.DictReader(csvfile); extracted_data = [dict(row) for row in reader]
                rows_extracted = len(extracted_data)
                logger.info(f"Task {task_id}: Read {rows_extracted} rows from {source_path}.")
            except Exception as e: raise AgentProcessingError(f"Error reading CSV: {e}") from e
            artifact_db_id = await self._insert_artifact(run_id, "extract_data", "raw_data", extracted_data)
            output_data = ExtractOutput(artifact_db_id=artifact_db_id, rows_extracted=rows_extracted)
            completion_message = f"Extracted {rows_extracted} rows from '{source_path.name}'. DB ID: {artifact_db_id}."
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

    async def handle_task_get(self, task_id: str) -> Task: # Corrected type hint usage
        if not self.task_store: raise ConfigurationError("Task store missing.")
        context = await self.task_store.get_task(task_id)
        if context is None: raise TaskNotFoundError(task_id=task_id)
        if _MODELS_AVAILABLE:
            messages = await self.task_store.get_messages(task_id) or []; artifacts = await self.task_store.get_artifacts(task_id) or []
            # Ensure Task is the imported one or the placeholder
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
        logger.info("Data Extractor Agent closed.")
