import logging
import asyncio
import json
import os
from typing import Dict, Any, Union, Optional, List, AsyncGenerator
import uuid

import asyncpg

# Import base class and SDK components
from agentvault_server_sdk.agent import BaseA2AAgent
from agentvault_server_sdk.state import TaskState as SdkTaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError, TaskNotFoundError

# Import models from this agent's models.py
from .models import LoadInput, LoadOutput, ValidationReport, LoadConfirmation, LoadConfirmationArtifact

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart, TaskState, Task, A2AEvent
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found. Using placeholders.")
    # Define placeholders on separate lines (CORRECTED - FINAL ATTEMPT)
    class Message:
        pass
    class TextPart:
        pass
    class Artifact:
        pass
    class DataPart:
        pass
    class TaskState:
        SUBMITTED = "SUBMITTED"; WORKING = "WORKING"; INPUT_REQUIRED = "INPUT_REQUIRED"
        COMPLETED = "COMPLETED"; FAILED = "FAILED"; CANCELED = "CANCELED"
    class Task:
        pass
    class A2AEvent:
        pass
    _MODELS_AVAILABLE = False # type: ignore

TaskStateEnum = TaskState if _MODELS_AVAILABLE else SdkTaskState

logger = logging.getLogger(__name__)
AGENT_ID = "local-poc/etl-data-loader"
DB_HOST = os.environ.get("DATABASE_HOST", "etl-db"); DB_PORT = os.environ.get("DATABASE_PORT", 5432)
DB_USER = os.environ.get("DATABASE_USER"); DB_PASSWORD = os.environ.get("DATABASE_PASSWORD"); DB_NAME = os.environ.get("DATABASE_NAME")
db_config_valid = all([DB_USER, DB_PASSWORD, DB_NAME])
if not db_config_valid: logger.error("DB connection details missing.")
MOCK_TARGET_TABLE = "loaded_data_target"
MOCK_TARGET_SCHEMA = f"""CREATE TABLE IF NOT EXISTS {MOCK_TARGET_TABLE} (load_id SERIAL PRIMARY KEY, run_id VARCHAR(64) NOT NULL, original_item_id VARCHAR(255), item_name TEXT, item_type VARCHAR(100), price NUMERIC(10, 2), loaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP);"""

class DataLoaderAgent(BaseA2AAgent):
    def __init__(self):
        super().__init__(agent_metadata={"name": "Data Loader Agent"})
        self.db_pool: Optional[asyncpg.Pool] = None
        self.db_config_valid = db_config_valid
        self.task_store: Optional[Any] = None
        logger.info(f"Data Loader Agent initialized. DB Config Valid: {self.db_config_valid}")

    async def _get_db_pool(self) -> asyncpg.Pool:
        if not self.db_config_valid: raise ConfigurationError("DB not configured.")
        if self.db_pool is None:
            logger.info(f"Creating DB pool for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
            try:
                self.db_pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASSWORD, database=DB_NAME, host=DB_HOST, port=DB_PORT, min_size=1, max_size=5)
                logger.info("DB pool created.")
                async with self.db_pool.acquire() as conn: await conn.execute(MOCK_TARGET_SCHEMA); logger.info(f"Ensured table '{MOCK_TARGET_TABLE}' exists.")
            except Exception as e: logger.exception(f"Failed to create DB pool/table: {e}"); raise ConfigurationError(f"DB setup failed: {e}") from e
        return self.db_pool # type: ignore

    async def _fetch_dict_artifact_data(self, artifact_db_id: int) -> Dict[str, Any]:
        pool = await self._get_db_pool()
        async with pool.acquire() as connection:
            try:
                record = await connection.fetchrow("SELECT artifact_data FROM pipeline_artifacts WHERE id = $1", artifact_db_id)
                if not record: raise AgentProcessingError(f"Artifact ID {artifact_db_id} not found.")
                raw_db_data = record['artifact_data']
                if isinstance(raw_db_data, str):
                    try: data = json.loads(raw_db_data)
                    except json.JSONDecodeError as json_err: raise AgentProcessingError(f"Failed to parse JSON string from DB for artifact ID {artifact_db_id}: {json_err}") from json_err
                elif isinstance(raw_db_data, dict): data = raw_db_data
                else: raise AgentProcessingError(f"Unexpected data type ({type(raw_db_data).__name__}) fetched from DB for artifact ID {artifact_db_id}.")
                if not isinstance(data, dict): raise AgentProcessingError(f"Deserialized artifact data ID {artifact_db_id} is not a dict (type: {type(data).__name__}).")
                logger.info(f"Fetched and parsed dict artifact data ID {artifact_db_id}.")
                return data
            except AgentProcessingError: raise
            except Exception as e: logger.exception(f"DB error fetching/parsing artifact ID {artifact_db_id}: {e}"); raise AgentProcessingError(f"DB error fetching/parsing artifact: {e}") from e

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
            except Exception as e: logger.exception(f"DB error fetching/parsing list artifact ID {artifact_db_id}: {e}"); raise AgentProcessingError(f"DB error fetching/parsing list artifact: {e}") from e

    async def _insert_artifact(self, run_id: str, step_name: str, artifact_type: str, confirmation: LoadConfirmation) -> int:
        pool = await self._get_db_pool(); confirmation_dict = confirmation.model_dump(mode='json'); serialized_data = json.dumps(confirmation_dict)
        async with pool.acquire() as conn:
            try:
                result = await conn.fetchrow("INSERT INTO pipeline_artifacts (run_id, step_name, artifact_type, artifact_data) VALUES ($1, $2, $3, $4::jsonb) RETURNING id", run_id, step_name, artifact_type, serialized_data)
                if result and 'id' in result: artifact_db_id = result['id']; logger.info(f"Inserted artifact '{artifact_type}' run '{run_id}'. DB ID: {artifact_db_id}"); return artifact_db_id
                else: raise AgentProcessingError("Failed to retrieve DB ID after insert.")
            except Exception as e: logger.exception(f"DB error inserting artifact '{artifact_type}' run '{run_id}': {e}"); raise AgentProcessingError(f"DB error inserting artifact: {e}") from e

    async def _mock_load_to_db(self, run_id: str, data_to_load: List[Dict[str, Any]]) -> int:
        pool = await self._get_db_pool(); rows_inserted = 0
        async with pool.acquire() as conn:
            insert_data = [(run_id, row.get("Item ID"), row.get("Item Name"), row.get("Type"), row.get("Price")) for row in data_to_load]
            try:
                await conn.execute(MOCK_TARGET_SCHEMA)
                await conn.executemany(f"INSERT INTO {MOCK_TARGET_TABLE} (run_id, original_item_id, item_name, item_type, price) VALUES ($1, $2, $3, $4, $5)", insert_data)
                rows_inserted = len(data_to_load)
                logger.info(f"Successfully processed {rows_inserted} rows for insertion into '{MOCK_TARGET_TABLE}' run '{run_id}'.")
            except asyncpg.PostgresError as pg_err: logger.exception(f"PostgresError inserting into mock target table run '{run_id}': {pg_err} (Detail: {pg_err.detail})"); rows_inserted = 0
            except Exception as e: logger.exception(f"Unexpected error inserting into mock target table run '{run_id}': {e}"); rows_inserted = 0
        return rows_inserted

    async def handle_task_send(self, task_id: Optional[str], message: Message, background_tasks: asyncio.Task = None) -> str:
        if task_id: raise AgentProcessingError(f"Loader agent does not support continuing task {task_id}")
        new_task_id = f"etl-load-{uuid.uuid4().hex[:8]}"
        logger.info(f"Task {new_task_id}: Received load request.")
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
        conf_id: Optional[int] = None; load_status = "Failed"; rows_processed = 0; rows_loaded = 0
        final_state = TaskStateEnum.FAILED; error_message = "Failed load."; completion_message = error_message
        try:
            if not self.db_config_valid: raise ConfigurationError("DB not configured.")
            try: input_data = LoadInput.model_validate(content)
            except Exception as val_err: raise AgentProcessingError(f"Invalid input: {val_err}")
            tf_id = input_data.transformed_data_artifact_id; val_id = input_data.validation_report_artifact_id; run_id = input_data.run_id
            logger.info(f"Task {task_id}: Loading data ID {tf_id} based on report ID {val_id} run '{run_id}'.")
            report_data = await self._fetch_dict_artifact_data(val_id)
            validation_report = ValidationReport.model_validate(report_data)
            tf_data = await self._fetch_list_artifact_data(tf_id)
            rows_processed = len(tf_data)
            if validation_report.status != "Success":
                load_status = "Aborted"; message = f"Load aborted. Validation status: {validation_report.status}. Invalid: {validation_report.invalid_rows}."; rows_loaded = 0; logger.warning(f"Task {task_id}: {message}")
            else:
                logger.info(f"Task {task_id}: Validation OK. Simulating load of {rows_processed} rows...")
                rows_loaded = await self._mock_load_to_db(run_id, tf_data)
                if rows_loaded == rows_processed: load_status = "Success"; message = f"Simulated load of {rows_loaded} rows."; logger.info(f"Task {task_id}: {message}")
                else: load_status = "Failed"; message = f"Mock load issue: Attempted {rows_processed}, inserted {rows_loaded}. Check agent logs for DB error details."; logger.error(f"Task {task_id}: {message}"); error_message = message
            confirmation = LoadConfirmation(status=load_status, message=message, rows_processed=rows_processed, rows_loaded=rows_loaded, target_table=MOCK_TARGET_TABLE if load_status == "Success" else None)
            conf_id = await self._insert_artifact(run_id, "load_data", "load_confirmation", confirmation)
            output_data = LoadOutput(artifact_db_id=conf_id, load_status=load_status, rows_processed=rows_processed, rows_loaded=rows_loaded)
            completion_message = f"Load finished. Status: {load_status}. Conf DB ID: {conf_id}."
            if load_status == "Success": final_state = TaskStateEnum.COMPLETED; error_message = None
            else: final_state = TaskStateEnum.FAILED; error_message = message if not error_message else error_message
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
        logger.info("Data Loader Agent closed.")
