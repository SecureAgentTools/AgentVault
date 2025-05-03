import subprocess
import logging
import asyncio
import shlex # For potentially safer argument handling if needed later

# Import constants from security module
from .security import TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# --- MCP Response Formatting Helpers ---
# These functions create the dictionary structure expected in the 'result' field
# of the final JSON-RPC response.

def create_mcp_success_response(stdout: str, stderr: str) -> dict:
    """Formats a standard MCP success result for code execution."""
    logger.debug(f"Formatting success response. Stdout len: {len(stdout)}, Stderr len: {len(stderr)}")
    return {
        "content": [
            {
                "type": "code_output", # MCP standard type for code output
                "stdout": stdout,
                "stderr": stderr
            }
        ]
        # isError: false is implied
    }

def create_mcp_tool_error_response(error_message: str) -> dict:
    """Formats a standard MCP tool execution error result."""
    logger.error(f"Formatting tool error response: {error_message}")
    return {
        "isError": True, # This flag indicates a tool-level error
        "content": [
            {
                "type": "text", # MCP standard type for error messages
                "text": error_message
            }
        ]
    }

# --- Tool Implementation ---

async def run_python_code(code: str) -> dict:
    """
    Executes the given Python code string securely using subprocess.run
    in a separate thread and returns a dictionary suitable for the MCP
    JSON-RPC 'result' field.
    """
    if not isinstance(code, str):
        return create_mcp_tool_error_response("Invalid input: 'code' parameter must be a string.")

    logger.info(f"Executing Python code (length: {len(code)} bytes) with timeout {TIMEOUT_SECONDS}s")
    logger.debug(f"Code to execute:\n---\n{code[:500]}{'...' if len(code) > 500 else ''}\n---")

    try:
        # Use asyncio.to_thread to run the blocking subprocess call
        # in a separate thread pool, preventing it from blocking the main
        # FastAPI/Uvicorn event loop.
        process = await asyncio.to_thread(
            subprocess.run,
            # Command: execute python interpreter (-c reads code from string)
            ['python', '-c', code],
            # Capture stdout and stderr streams
            capture_output=True,
            # Decode output as text (UTF-8 recommended, handle errors)
            encoding='utf-8', errors='surrogateescape',
            # Set timeout for execution
            timeout=TIMEOUT_SECONDS,
            # Do not raise exception on non-zero exit code, handle manually
            check=False,
            # Security: Consider adding resource limits here if possible/needed,
            # though container-level limits are generally preferred.
            # Security: Ensure this runs as the non-root user defined in Dockerfile.
        )

        stdout = process.stdout or ""
        stderr = process.stderr or ""

        logger.info(f"Code execution finished. Return code: {process.returncode}")
        logger.debug(f"STDOUT:\n{stdout}")
        logger.debug(f"STDERR:\n{stderr}")

        # Decide how to handle non-zero return codes.
        # Option 1: Always return success, include stderr for user to see errors.
        # Option 2: Treat non-zero return code as a tool error.
        # Let's choose Option 1 for now, as stderr often contains useful debugging info
        # even if the script technically "failed" with a non-zero exit.
        # We already log a warning in this case.
        if process.returncode != 0:
            logger.warning(f"Code execution finished with non-zero return code ({process.returncode}). Stderr included in response.")
            # Fall through to return success response including stderr

        # Successful execution (return code 0 or non-zero handled as success)
        return create_mcp_success_response(stdout, stderr)

    except subprocess.TimeoutExpired:
        # Specific error for timeout
        return create_mcp_tool_error_response(f"Execution timed out after {TIMEOUT_SECONDS} seconds.")
    except FileNotFoundError:
        # This critical error means 'python' wasn't found in the container's PATH.
        logger.critical("Python interpreter not found for subprocess execution. Check Dockerfile and PATH.", exc_info=True)
        # Return a tool error indicating internal server misconfiguration
        return create_mcp_tool_error_response("Internal configuration error: Python interpreter not found.")
    except OSError as os_err:
        # Catch other OS-level errors during process creation/execution
        logger.error(f"OS error during subprocess execution: {os_err}", exc_info=True)
        return create_mcp_tool_error_response(f"OS error during execution: {os_err}")
    except Exception as e:
        # Catch any other unexpected errors during subprocess handling
        logger.exception("Unexpected error during code execution subprocess.")
        # Return a generic tool error
        return create_mcp_tool_error_response(f"An unexpected server error occurred during code execution: {str(e)}")

logger.info("Code runner tool function defined.")
