# Action Recommender Agent Fix Tools

This directory contains scripts to fix the issue with the Action Recommender Agent when using the Meta Llama 3 model.

## The Issue

The agent is currently configured to use `"response_format": { "type": "json_object" }` in its LLM API call, but your local Meta Llama 3 implementation returns:

```
HTTP error 400 from LLM API: {"error":"'response_format.type' must be 'json_schema'"}
```

## Test Results

Based on the testing with `direct_llama_test.py`, we discovered:

1. ✅ Basic request with no response format: **WORKS**
   - The model returns JSON naturally when prompted

2. ❌ Using `"response_format": {"type": "json_object"}`: **FAILS**
   - This is what's causing your 400 error

3. ✅ Using `"format": "json"`: **WORKS**
   - This alternative parameter works with your Llama implementation

## Fix Options

Based on the test results, we have two recommended fixes:

### Option 1: Remove response_format completely
This is the simplest fix - just rely on the prompt instructions to get JSON output.

```
python fix_agent.py
```

### Option 2: Use format:json parameter
This alternative approach also worked in testing:

```
python format_json_fix.py
```

## All Available Tools

1. **direct_llama_test.py**: Tests which parameters your Llama model accepts
   ```
   python direct_llama_test.py
   ```

2. **fix_agent.py**: Removes the response_format parameter completely
   ```
   python fix_agent.py
   ```

3. **format_json_fix.py**: Replaces response_format with format:json
   ```
   python format_json_fix.py
   ```

4. **llm_format_tester.py**: Comprehensive test of different API configurations
   ```
   python llm_format_tester.py
   ```

5. **simplified_agent.py**: Simplified version of the agent for testing
   ```
   python simplified_agent.py
   ```

6. **agent_patcher.py**: Tool for applying different patches to the agent
   ```
   python agent_patcher.py list
   python agent_patcher.py apply remove_response_format
   python agent_patcher.py restore
   ```

## Notes

- All scripts will create backups before modifying files
- The response_format parameter with type 'json_object' is OpenAI-specific and not universally supported
- Both removing the parameter or using format:json appear to work with your implementation
