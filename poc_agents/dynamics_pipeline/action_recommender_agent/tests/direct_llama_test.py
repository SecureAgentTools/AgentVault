import requests
import json

# Configuration
API_URL = "http://localhost:1234/v1/chat/completions"  # Adjust if your URL is different

# Simple test message
message = "Generate a list of 3 recommended actions for a sales team."

# Test cases with different configurations
test_cases = [
    {
        "name": "Basic (no response format)",
        "payload": {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "messages": [{"role": "user", "content": message}],
            "temperature": 0.7,
            "max_tokens": 500
        }
    },
    {
        "name": "With json_object format",
        "payload": {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "messages": [{"role": "user", "content": message}],
            "temperature": 0.7,
            "max_tokens": 500,
            "response_format": {"type": "json_object"}
        }
    },
    {
        "name": "With format:json parameter",
        "payload": {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "messages": [{"role": "user", "content": message}],
            "temperature": 0.7,
            "max_tokens": 500,
            "format": "json"
        }
    }
]

def run_test(test_case):
    print(f"\n===== Testing: {test_case['name']} =====")
    print(f"Request payload: {json.dumps(test_case['payload'], indent=2)}")
    
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(API_URL, json=test_case['payload'], headers=headers)
        status_code = response.status_code
        print(f"Response status: {status_code}")
        
        if status_code == 200:
            response_data = response.json()
            print("Success!")
            if "choices" in response_data and response_data["choices"]:
                content = response_data["choices"][0]["message"]["content"]
                print(f"Response preview: {content[:150]}...")
            else:
                print(f"Unexpected response structure: {json.dumps(response_data, indent=2)}")
        else:
            print(f"Error response: {response.text}")
    
    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    print("Meta-Llama-3 API Parameter Test")
    print("==============================")
    
    for test_case in test_cases:
        run_test(test_case)
        print("\n")
