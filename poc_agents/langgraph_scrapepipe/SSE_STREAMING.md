# SSE Streaming Implementation for AgentVault

This document explains the Server-Sent Events (SSE) streaming implementation in the AgentVault research pipeline, particularly focusing on handling local LLM environments with slower response times.

## Background

The AgentVault research pipeline uses Server-Sent Events (SSE) for real-time streaming of agent responses. When working with local LLMs, there can be timing issues where the SSE connection is established before the LLM has finished processing the task, resulting in "Task not found" errors.

## Implementation Details

Our implementation addresses this with the following strategies:

### 1. Initial Processing Delay

After task initiation, we add a deliberate delay to give the LLM time to process the task:

```python
# Add a delay before subscribing to events
logger.info(f"Waiting for LLM to process task {task_id}...")
await asyncio.sleep(10.0)  # 10 second delay for local LLM processing
```

This delay can be adjusted based on your local LLM's performance.

### 2. Task Status Verification

Before attempting SSE streaming, we verify that the task exists and has started processing:

```python
# Verify task exists with multiple attempts
max_verify_attempts = 3
verify_attempt = 0
task_verified = False

while not task_verified and verify_attempt < max_verify_attempts:
    try:
        verify_attempt += 1
        status = await self._get_task_status_with_retry(agent_card, task_id)
        logger.info(f"Verified task {task_id} exists with state: {status.state}")
        task_verified = True
    except Exception as verify_err:
        # Retry logic...
```

### 3. Robust SSE Subscription with Retries

We've implemented a robust SSE subscription method that specifically handles "Task not found" errors with retries:

```python
async def _try_sse_subscription(self, agent_card: AgentCard, task_id: str, key_manager: KeyManager, 
                           max_attempts: int = 3, retry_delay: float = 5.0) -> AsyncGenerator[A2AEvent, None]:
    """
    Try to subscribe to SSE events with retries for local LLM environments.
    """
    # Implementation with retries for "Task not found" errors
```

This method will retry the SSE subscription up to `max_attempts` times, with a delay of `retry_delay` seconds between attempts.

### 4. Fallback to Polling

If SSE streaming fails after multiple attempts, the system will fall back to polling:

```python
if goto_polling or not event_method:
    # Polling fallback implementation
```

## Configuration Parameters

Key parameters that can be adjusted:

1. **Initial processing delay**: Currently set to 10 seconds
2. **Verification attempts**: Currently set to 3 attempts
3. **SSE subscription attempts**: Currently set to 3 attempts
4. **Retry delay**: Currently set to 5 seconds between attempts

These parameters can be adjusted based on your specific local LLM performance characteristics.

## Testing

You can test the SSE streaming implementation with:

```bash
python test_sse_streaming.py
```

This will run a brief test pipeline and verify that SSE streaming works correctly.

## Troubleshooting

If you encounter issues with SSE streaming:

1. Increase the initial processing delay (for slower LLMs)
2. Increase the number of verification and subscription attempts
3. Increase the retry delay
4. Check Docker logs for "Task not found" errors
5. Check the console logs for "SSE stream connection successful" messages followed by "Processed 0 events" (indicates early disconnection)

## Production Considerations

The current implementation is optimized for local development with slower LLMs. In a production environment with faster LLMs:

1. You may be able to reduce the initial processing delay
2. You may need fewer verification and subscription attempts
3. Retry delays can be shorter

However, the robust implementation should work well in both environments.
