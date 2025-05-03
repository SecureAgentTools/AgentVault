import asyncio
import json
import httpx
import os
from pprint import pprint

# Configuration - adjust these as needed
LLM_API_URL = "http://host.docker.internal:1234"  # Same as in your error log
LLM_MODEL_NAME = "meta-llama/Meta-Llama-3-8B-Instruct"  # From your error log

# Sample JSON schema (simplified from your code)
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action_description": {"type": "string"},
                    "rationale": {"type": "string"},
                    "priority": {"type": "string", "enum": ["High", "Medium", "Low"]}
                },
                "required": ["action_description", "rationale", "priority"]
            }
        }
    },
    "required": ["recommended_actions"]
}

# Simple prompt for testing
SIMPLE_PROMPT = """
Generate 2 recommended business actions for a sales account.
Each action should have:
1. A clear action description
2. A rationale for the action
3. A priority level (High, Medium, or Low)

Format your response as a JSON object with the structure:
{
  "recommended_actions": [
    {
      "action_description": "...",
      "rationale": "...",
      "priority": "..."
    }
  ]
}
"""

async def test_llm_format(test_name, payload, print_response=True):
    """Test a specific LLM configuration and print results"""
    print(f"\n==== TEST: {test_name} ====")
    print(f"Request payload: {json.dumps(payload, indent=2)}")
    
    headers = {"Content-Type": "application/json"}
    endpoint = f"{LLM_API_URL.rstrip('/')}/v1/chat/completions"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            status_code = response.status_code
            
            print(f"Response status: {status_code}")
            
            if status_code != 200:
                print(f"ERROR: {response.text}")
                return False, None
            
            result = response.json()
            if print_response:
                if "choices" in result and result["choices"]:
                    content = result["choices"][0]["message"]["content"]
                    print(f"Response content: {content[:500]}...")
                else:
                    print(f"Full response: {json.dumps(result, indent=2)}")
            
            return True, result
    except Exception as e:
        print(f"Exception: {e}")
        return False, None

async def run_tests():
    """Run various tests to determine what the model supports"""
    results = {}
    
    # Test 1: Basic call with no response format
    payload1 = {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 600
    }
    success1, result1 = await test_llm_format("No response format", payload1)
    results["no_format"] = {"success": success1, "result": result1}
    
    # Test 2: With response_format type=json_object (OpenAI standard)
    payload2 = {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 600,
        "response_format": {"type": "json_object"}
    }
    success2, result2 = await test_llm_format("response_format.type=json_object", payload2)
    results["json_object"] = {"success": success2, "result": result2}
    
    # Test 3: With response_format type=json_schema (with schema)
    payload3 = {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 600,
        "response_format": {"type": "json_schema", "schema": JSON_SCHEMA}
    }
    success3, result3 = await test_llm_format("response_format.type=json_schema with schema", payload3)
    results["json_schema"] = {"success": success3, "result": result3}
    
    # Test 4: With response_format type=text (fallback)
    payload4 = {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 600,
        "response_format": {"type": "text"}
    }
    success4, result4 = await test_llm_format("response_format.type=text", payload4)
    results["text"] = {"success": success4, "result": result4}
    
    # Test 5: Try with llama.cpp format parameter if applicable
    payload5 = {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 600,
        "format": "json"  # Some llama.cpp endpoints use this
    }
    success5, result5 = await test_llm_format("format=json parameter", payload5)
    results["format_json"] = {"success": success5, "result": result5}
    
    # Test 6: Try with no format but schema inside prompt
    schema_prompt = SIMPLE_PROMPT + "\n\nUse this JSON schema:\n" + json.dumps(JSON_SCHEMA, indent=2)
    payload6 = {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": schema_prompt}],
        "temperature": 0.4,
        "max_tokens": 600
    }
    success6, result6 = await test_llm_format("Schema in prompt only", payload6)
    results["schema_in_prompt"] = {"success": success6, "result": result6}
    
    # Summary
    print("\n==== RESULTS SUMMARY ====")
    for test_name, result in results.items():
        print(f"{test_name}: {'✅ Success' if result['success'] else '❌ Failed'}")
    
    # Save results to file for later reference
    with open("llm_format_test_results.json", "w") as f:
        # Remove full result data to keep file manageable
        for k in results:
            if results[k]["result"]:
                results[k]["result"] = "Result data stored but removed for summary file"
        json.dump(results, f, indent=2)
    
    print("\nTest results saved to llm_format_test_results.json")
    return results

if __name__ == "__main__":
    asyncio.run(run_tests())
