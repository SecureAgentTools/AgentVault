# Configuring the Qwen3-8B LLM for the SecOps Pipeline

This guide provides detailed instructions for configuring the Qwen3-8B large language model to work with the SecOps pipeline.

## Overview

The SecOps pipeline integrates directly with Qwen3-8B through an OpenAI-compatible API endpoint. This allows the pipeline to leverage the model's reasoning capabilities for security alert analysis, severity assessment, and response determination.

## Prerequisites

- Qwen3-8B model running on a server that provides an OpenAI-compatible API
- Accessible endpoint at http://localhost:1234 (or configured alternative)
- Support for chat completions API format

## API Requirements

The API should conform to the OpenAI chat completions specification:

- Endpoint: `/v1/chat/completions`
- Request format:
  ```json
  {
    "model": "qwen3-8b",
    "messages": [
      {"role": "system", "content": "System prompt..."},
      {"role": "user", "content": "User message..."}
    ],
    "temperature": 0.7,
    "max_tokens": 1024
  }
  ```
- Response format:
  ```json
  {
    "choices": [
      {
        "message": {
          "role": "assistant",
          "content": "Response from LLM..."
        }
      }
    ]
  }
  ```

## Configuration Parameters

The SecOps pipeline uses the following environment variables to configure the LLM connection:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_URL` | Base URL for the LLM API | `http://host.docker.internal:1234/v1` |
| `LLM_MODEL_NAME` | Model identifier to use in API calls | `qwen3-8b` |
| `LLM_TIMEOUT_SECONDS` | Timeout for LLM API requests in seconds | `120` |
| `RUNNING_IN_DOCKER` | Whether the application is running in Docker | `true` |

These variables can be set in the `docker-compose.secops.yml` file or passed as environment variables.

## Testing the Configuration

You can test the LLM configuration using `curl`:

```bash
curl -X POST http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role": "user", "content": "Say hello!"}],
    "temperature": 0.7
  }'
```

If the API is configured correctly, you should receive a response with the LLM's greeting.

## Qwen3-8B Specific Features

### /no_think Directive

The Qwen3-8B model supports a `/no_think` directive that can be appended to user messages to request concise responses without detailed reasoning steps. The SecOps pipeline code includes support for this feature, which can be enabled or disabled in the LLM client.

Example usage in the code:
```python
# If use_no_think is enabled, append it to the last user message
if options.use_no_think and "qwen" in self.model_name.lower():
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            messages[i].content += " /no_think"
            break
```

## Fallback Mechanisms

The SecOps pipeline includes robust fallback mechanisms in case the LLM is unavailable or returns errors:

1. If the LLM API is unavailable, the pipeline will use mock responses to continue functioning
2. If the LLM returns an error or invalid response, the pipeline falls back to pre-defined responses
3. Connection issues are handled gracefully with multiple retry attempts and timeouts

This ensures the security pipeline remains operational even during LLM service disruptions.

## Modifying LLM Prompts

The LLM prompts used for security analysis can be found in the `llm_client.py` file. The main prompts are:

1. **Investigation Prompt**: Used to analyze alerts and determine severity
2. **Response Determination Prompt**: Used to decide on appropriate response actions

To modify these prompts:

1. Locate the relevant functions in `llm_client.py` (`analyze_alert` and `determine_response_action`)
2. Update the prompt construction in these functions
3. Ensure the expected response format is maintained

## Advanced Configuration

### Adjusting Model Parameters

You can adjust model parameters like temperature, max tokens, and top_p by modifying the `LLMOptions` class in the LLM client:

```python
options = LLMOptions(
    temperature=0.3,  # Lower temperature for more deterministic responses
    max_tokens=1024,  # Adjust based on response complexity
    use_no_think=use_no_think  # Enable/disable no_think directive
)
```

### Multiple LLM Support

The current implementation primarily supports Qwen3-8B, but can be extended to support other models by modifying the LLM client. The important requirements are:

1. The model should support an OpenAI-compatible API
2. The responses should be parseable as JSON
3. The model should be capable of security analysis reasoning

To add support for additional models, modify the client code to handle model-specific features and adjust prompts as needed.
