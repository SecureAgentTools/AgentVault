import logging
from typing import TypedDict, List, Optional, Dict, Any

# Import the specific data models if needed (e.g., for code execution result)
from .models import CodeExecutionResult

# Import config and wrapper types for state typing
try:
    from .config import McpTestPipelineConfig
    # Use the actual wrapper class from the shared location
    from dynamics_orchestrator.a2a_client_wrapper import A2AClientWrapper
except ImportError:
    # Placeholders if run in isolation
    class McpTestPipelineConfig: pass # type: ignore
    class A2AClientWrapper: pass # type: ignore

logger = logging.getLogger(__name__)

# REQ-MCPTEST-ORCH-002
class McpTestState(TypedDict):
    """State for the MCP Test pipeline."""
    # Inputs & Config
    pipeline_config: McpTestPipelineConfig
    a2a_wrapper: A2AClientWrapper
    project_id: str
    input_file_path: Optional[str] # e.g., /data/my_script.py
    input_python_code: Optional[str] # e.g., "print('hello')"

    # Tracking
    current_step: Optional[str]
    error_message: Optional[str]

    # Intermediate Results
    read_file_content: Optional[str]
    code_execution_output: Optional[CodeExecutionResult] # Store structured output
    write_file_result: Optional[Dict[str, Any]] # Store proxy output for write

logger.info("McpTestState TypedDict defined.")
