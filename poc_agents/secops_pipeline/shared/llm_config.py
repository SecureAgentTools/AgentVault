"""
LLM Configuration module for SecOps pipeline to use Qwen3-8B model.
This module is imported by llm_client.py to configure the LLM properly.
"""

import os
import logging
import requests
from typing import Dict, Any, List, Optional, Union, Tuple

# Configure logger
logger = logging.getLogger(__name__)

# LLM Configuration
DEFAULT_LLM_URL = "http://localhost:1234/v1"  # Local endpoint for Qwen3-8b
DEFAULT_DOCKER_URL = "http://host.docker.internal:1234/v1"  # Docker container endpoint for Qwen3-8b
DEFAULT_MODEL_NAME = "qwen3-8b"  # Model name as specified in the model list
DEFAULT_TIMEOUT_SECONDS = 120  # Increased timeout for complex queries

def get_llm_config() -> Dict[str, Any]:
    """
    Get the LLM configuration from environment variables or defaults.
    
    Returns:
        Dict containing LLM configuration parameters
    """
    # Detect if we're running in Docker or locally
    # If RUNNING_IN_DOCKER env var is set, use Docker URL, otherwise use localhost
    running_in_docker = os.environ.get("RUNNING_IN_DOCKER", "false").lower() == "true"
    default_url = DEFAULT_DOCKER_URL if running_in_docker else DEFAULT_LLM_URL
    
    config = {
        "api_url": os.environ.get("LLM_API_URL", default_url),
        "model_name": os.environ.get("LLM_MODEL_NAME", DEFAULT_MODEL_NAME),
        "timeout": int(os.environ.get("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    }
    
    logger.info(f"LLM configuration loaded: API URL={config['api_url']}, Model={config['model_name']}, Timeout={config['timeout']}s")
    return config

def verify_llm_availability() -> Tuple[bool, str]:
    """
    Verify that the LLM is available and the model is loaded.
    
    Returns:
        Tuple of (success, message)
    """
    config = get_llm_config()
    
    try:
        # Check if LM Studio is running
        try:
            response = requests.get(f"{config['api_url']}/models", timeout=5)
        except requests.exceptions.ConnectionError as e:
            # If host.docker.internal fails, try localhost
            if "host.docker.internal" in config['api_url'] and "Failed to establish a new connection" in str(e):
                logger.warning(f"Connection to {config['api_url']} failed, trying localhost fallback")
                fallback_url = config['api_url'].replace("host.docker.internal", "localhost")
                response = requests.get(f"{fallback_url}/models", timeout=5)
                # If localhost worked, suggest updating the config
                logger.info(f"Fallback to {fallback_url} successful")
                if "LMSTUDIO_API_URL" not in os.environ:
                    logger.info("Consider setting LMSTUDIO_API_URL environment variable to use localhost")
            else:
                raise
        
        if response.status_code != 200:
            return False, f"Failed to connect to LM Studio: Status code {response.status_code}"
        
        # Check if the model is available
        models_data = response.json()
        available_models = [model["id"] for model in models_data.get("data", [])]
        
        if not available_models:
            return False, "No models available in LM Studio"
        
        logger.info(f"Available models: {available_models}")
        
        if config["model_name"] not in available_models:
            # Try variations of the model name (capitalization differences, etc.)
            model_name_lower = config["model_name"].lower()
            similar_models = [m for m in available_models if model_name_lower in m.lower()]
            
            if similar_models:
                logger.info(f"Found similar models: {similar_models}")
                return True, f"Found similar model(s) to '{config['model_name']}': {similar_models[0]}"
            else:
                available_str = ", ".join(available_models)
                return False, f"Model '{config['model_name']}' not found. Available models: {available_str}"
        
        # Test the model with a simple prompt
        test_response = requests.post(
            f"{config['api_url']}/chat/completions",
            json={
                "model": config["model_name"],
                "messages": [{"role": "user", "content": "Say hello in one word."}],
                "max_tokens": 10
            },
            timeout=10
        )
        
        if test_response.status_code != 200:
            return False, f"Failed to get response from model: Status code {test_response.status_code}"
        
        # Success!
        return True, f"LLM is available and '{config['model_name']}' is loaded"
        
    except requests.exceptions.RequestException as e:
        return False, f"Connection error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

if __name__ == "__main__":
    # When run directly, perform the verification check
    logging.basicConfig(level=logging.INFO)
    
    print(f"Checking LLM configuration for Qwen3-8B model...")
    print(f"Using configuration: {get_llm_config()}")
    
    success, message = verify_llm_availability()
    if success:
        print(f"+ SUCCESS: {message}")
        exit(0)
    else:
        print(f"- ERROR: {message}")
        print("\nPlease make sure:")
        print("1. LM Studio is running")
        print("2. The Qwen3-8B model is loaded")
        print("3. Server is enabled in LM Studio settings")
        print("4. The model is properly set in environment variables or defaults")
        exit(1)
