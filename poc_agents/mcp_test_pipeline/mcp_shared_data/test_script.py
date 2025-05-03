# Simple Python script for MCP code execution testing

import sys
import datetime
import os

print(f"MCP Test Script Execution Started at: {datetime.datetime.now()}")
print(f"Python Version: {sys.version}")
print(f"Current Working Directory: {os.getcwd()}")

# Example: Read an environment variable (if set in the code runner container)
# test_env_var = os.environ.get("TEST_ENV_VAR", "Not Set")
# print(f"TEST_ENV_VAR: {test_env_var}")

# Example: Simple calculation
result = 10 + 20 * 2
print(f"Calculation Result: {result}")

# Example: Print to stderr
print("This is a simulated error message on stderr.", file=sys.stderr)

print("MCP Test Script Execution Finished.")

# Example: Return a value (depends on how the MCP server captures output)
# If the server captures the last expression, this would be it.
# Otherwise, stdout/stderr is usually captured.
# {"final_result": result}
