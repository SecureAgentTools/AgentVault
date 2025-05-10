#!/usr/bin/env python
"""
Test script for verifying LLM configuration with Qwen3-8B model.
Run this script to test if the LLM is properly configured and responding.
"""

import asyncio
import logging
import json
import sys
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path if running script directly
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the LLM client and config
from shared.llm_config import get_llm_config, verify_llm_availability
from shared.llm_client import LLMClient, LLMMessage, LLMOptions

async def test_llm():
    """Test LLM availability and functionality"""
    print("\n=== LLM TEST SCRIPT FOR QWEN3-8B ===\n")
    
    # Step 1: Verify configuration
    print("Step 1: Checking LLM configuration...")
    config = get_llm_config()
    print(f"  API URL: {config['api_url']}")
    print(f"  Model: {config['model_name']}")
    print(f"  Timeout: {config['timeout']}s")
    print(f"  Running in Docker: {os.environ.get('RUNNING_IN_DOCKER', 'false')}")
    
    # Step 1.5: Test direct connection to verify URL is correct
    print("\nStep 1.5: Testing direct connection to LM Studio...")
    try:
        import socket
        host = config['api_url'].split('://')[1].split(':')[0]
        port = int(config['api_url'].split('://')[1].split(':')[1].split('/')[0])
        print(f"  Attempting to connect to {host}:{port}...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex((host, port))
        if result == 0:
            print(f"  + Connection successful: {host}:{port} is open and accessible")
        else:
            print(f"  - Connection failed: {host}:{port} is not accessible (Error code: {result})")
            # Try localhost as fallback if host.docker.internal failed
            if host == "host.docker.internal":
                fallback_host = "localhost"
                print(f"  Trying fallback connection to {fallback_host}:{port}...")
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                result = s.connect_ex((fallback_host, port))
                if result == 0:
                    print(f"  + Fallback connection successful: {fallback_host}:{port} is open and accessible")
                    print(f"  Suggestion: Use '{fallback_host}' instead of '{host}' in your configuration")
                else:
                    print(f"  - Fallback connection failed: {fallback_host}:{port} is not accessible (Error code: {result})")
                    print("  Suggestion: Check if LM Studio is running and the server is enabled")
        s.close()
    except Exception as e:
        print(f"  - Error during connection test: {str(e)}")
    
    # Step 2: Verify availability
    print("\nStep 2: Verifying LLM availability...")
    success, message = verify_llm_availability()
    if not success:
        print(f"  - ERROR: {message}")
        print("\nLLM is not available. Please make sure:")
        print("1. LM Studio is running")
        print("2. The Qwen3-8B model is loaded")
        print("3. Server is enabled in LM Studio settings")
        print("4. The model is accessible at the configured URL")
        return False
    else:
        print(f"  + SUCCESS: {message}")
    
    # Step 3: Test simple completion
    print("\nStep 3: Testing simple completion...")
    try:
        async with LLMClient() as client:
            messages = [
                LLMMessage(role="system", content="You are a helpful AI assistant."),
                LLMMessage(role="user", content="What's your name and what model are you running?")
            ]
            
            options = LLMOptions(
                temperature=0.7,
                max_tokens=100
            )
            
            response = await client.chat_completion(messages, options)
            
            if 'choices' in response and len(response['choices']) > 0:
                content = response['choices'][0]['message']['content']
                print(f"\nModel response:\n-------------\n{content}\n-------------")
                print("\n+ SUCCESS: LLM responded successfully!")
                return True
            else:
                print(f"- ERROR: Unexpected response format: {response}")
                return False
    except Exception as e:
        print(f"- ERROR: Failed to get completion: {e}")
        return False

# Test for security alert analysis
async def test_alert_analysis():
    """Test LLM's ability to analyze a security alert"""
    print("\nStep 4: Testing security alert analysis...")
    
    # Sample alert data
    alert_data = {
        "alert_id": "SEC-2025-1234",
        "name": "Suspicious Login Attempt",
        "severity": "Medium",
        "source": "SIEM",
        "timestamp": "2025-05-07T22:15:30Z",
        "description": "Multiple failed login attempts from unusual location",
        "details": {
            "user": "admin",
            "source_ip": "203.0.113.42",
            "attempts": 5,
            "timespan_minutes": 3
        }
    }
    
    # Enrichment data
    enrichment_data = {
        "203.0.113.42": {
            "reputation": "suspicious",
            "country": "Unknown",
            "tags": ["tor_exit_node", "proxy"]
        }
    }
    
    try:
        async with LLMClient() as client:
            result = await client.analyze_alert(alert_data, enrichment_data)
            
            if result.get("error"):
                print(f"- ERROR: {result['error']}")
                return False
            
            print("\nAlert analysis result:")
            print("----------------------")
            print(json.dumps(result, indent=2))
            print("----------------------")
            
            print("\n+ SUCCESS: LLM successfully analyzed the security alert!")
            return True
    except Exception as e:
        print(f"- ERROR: Failed to analyze alert: {e}")
        return False

if __name__ == "__main__":
    print("Testing LLM configuration and functionality...")
    
    # Run the tests
    loop = asyncio.get_event_loop()
    success = loop.run_until_complete(test_llm())
    
    if success:
        # If basic test succeeded, try alert analysis
        alert_success = loop.run_until_complete(test_alert_analysis())
        
        if alert_success:
            print("\n>> ALL TESTS PASSED: LLM is fully functional for the SecOps pipeline!")
            sys.exit(0)
        else:
            print("\n>> PARTIAL SUCCESS: Basic LLM functionality works but alert analysis failed")
            sys.exit(1)
    else:
        print("\n>> TEST FAILED: LLM is not properly configured or available")
        sys.exit(1)
