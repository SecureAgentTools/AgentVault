import httpx
import json
import asyncio

# Configuration - same as in your real agent
LLM_API_URL = "http://host.docker.internal:1234" 
LLM_MODEL_NAME = "meta-llama/Meta-Llama-3-8B-Instruct"

# Sample JSON schema (from your agent)
RECOMMENDATION_JSON_SCHEMA = {
  "type": "object",
  "properties": {
    "recommended_actions": {
      "type": "array",
      "description": "A list of 2-3 recommended next actions for the account.",
      "items": {
        "type": "object",
        "properties": {
          "action_description": {
            "type": "string",
            "description": "A clear, concise description of the recommended action."
          },
          "rationale": {
            "type": "string",
            "description": "The reason why this action is recommended."
          },
          "priority": {
            "type": "string",
            "enum": ["High", "Medium", "Low"],
            "description": "The priority level of the action."
          },
          "related_record_id": {
            "type": ["string", "null"],
            "description": "The ID of the related Dynamics record if applicable."
          }
        },
        "required": ["action_description", "rationale", "priority"]
      }
    }
  },
  "required": ["recommended_actions"]
}

# Simple prompt for testing
TEST_PROMPT = """
You are an expert sales assistant. Generate 2 recommended business actions for a sales account.
Each action should have:
1. A clear action description
2. A rationale for the action
3. A priority level (High, Medium, or Low)
4. A related record ID (can be null)

Format your response as a JSON object with the structure:
{
  "recommended_actions": [
    {
      "action_description": "...",
      "rationale": "...",
      "priority": "...",
      "related_record_id": "..." or null
    }
  ]
}
"""

async def test_configurations():
    """Test different request configurations and print the results"""
    http_client = httpx.AsyncClient(timeout=60.0)
    endpoint = f"{LLM_API_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    # Test configurations
    configurations = [
        # Test 1: No response format (baseline)
        {
            "name": "No response format (baseline)",
            "payload": {
                "model": LLM_MODEL_NAME,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "temperature": 0.4,
                "max_tokens": 600
            }
        },
        
        # Test 2: Original format that caused error
        {
            "name": "response_format.type=json_object (original error)",
            "payload": {
                "model": LLM_MODEL_NAME,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "temperature": 0.4,
                "max_tokens": 600,
                "response_format": {"type": "json_object"}
            }
        },
        
        # Test 3: Modified format attempted fix
        {
            "name": "response_format.type=json_schema",
            "payload": {
                "model": LLM_MODEL_NAME,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "temperature": 0.4,
                "max_tokens": 600,
                "response_format": {"type": "json_schema", "schema": RECOMMENDATION_JSON_SCHEMA}
            }
        },
        
        # Test 4: Alternative format
        {
            "name": "Alternative format - just schema in payload",
            "payload": {
                "model": LLM_MODEL_NAME,
                "messages": [{"role": "user", "content": TEST_PROMPT}],
                "temperature": 0.4,
                "max_tokens": 600,
                "schema": RECOMMENDATION_JSON_SCHEMA
            }
        }
    ]
    
    results = {}
    
    for config in configurations:
        print(f"\n\n==== TESTING: {config['name']} ====")
        try:
            print(f"Sending request to: {endpoint}")
            print(f"Request payload: {json.dumps(config['payload'], indent=2)}")
            
            response = await http_client.post(
                endpoint, 
                headers=headers, 
                json=config['payload']
            )
            
            status_code = response.status_code
            print(f"Response status code: {status_code}")
            
            if status_code == 200:
                result = response.json()
                if "choices" in result and result["choices"]:
                    content = result["choices"][0]["message"]["content"]
                    print(f"Success! First 200 chars of content: {content[:200]}...")
                    # Try to parse the response as JSON to verify structure
                    try:
                        parsed_json = json.loads(content)
                        print(f"JSON parsed successfully: {json.dumps(parsed_json, indent=2)[:200]}...")
                    except json.JSONDecodeError:
                        print("Warning: Content is not valid JSON")
                else:
                    print(f"Unexpected response structure: {json.dumps(result, indent=2)}")
                results[config['name']] = {"success": True, "status": status_code}
            else:
                error_text = response.text
                print(f"Error: {error_text}")
                results[config['name']] = {"success": False, "status": status_code, "error": error_text}
        
        except Exception as e:
            print(f"Exception occurred: {e}")
            results[config['name']] = {"success": False, "error": str(e)}
    
    await http_client.aclose()
    
    # Print summary
    print("\n\n==== RESULTS SUMMARY ====")
    for name, result in results.items():
        status = "✅ Success" if result.get("success") else f"❌ Failed ({result.get('status')})"
        print(f"{name}: {status}")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_configurations())
