import os
import shutil
import datetime

# Path to the agent.py file
AGENT_PATH = r"D:\AgentVault\poc_agents\dynamics_pipeline\action_recommender_agent\src\action_recommender_agent\agent.py"

def backup_file(file_path):
    """Create a backup of the file"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.{timestamp}.bak"
    shutil.copy2(file_path, backup_path)
    print(f"Created backup at: {backup_path}")
    return backup_path

def remove_response_format():
    """Remove the response_format parameter completely"""
    print("Applying fix: Remove response_format parameter")
    
    # Create backup
    backup_file(AGENT_PATH)
    
    # Read the current file content
    with open(AGENT_PATH, 'r') as f:
        content = f.read()
    
    # Define the search pattern and replacement
    search_pattern = """            "temperature": 0.4, # Slightly lower temp for more deterministic structure
            "max_tokens": 600, # Allow more tokens for JSON structure + content
            # Explicitly request JSON output if the API supports it (OpenAI standard)
            # Check LM Studio docs if this specific key works or if schema in prompt is sufficient
            "response_format": { "type": "json_object" }"""
    
    replacement = """            "temperature": 0.4, # Slightly lower temp for more deterministic structure
            "max_tokens": 600 # Allow more tokens for JSON structure + content
            # Removed response_format parameter as it was causing API errors"""
    
    # Apply the fix
    if search_pattern in content:
        new_content = content.replace(search_pattern, replacement)
        
        # Write the updated content
        with open(AGENT_PATH, 'w') as f:
            f.write(new_content)
        
        print("Successfully applied fix: Removed response_format parameter")
        return True
    else:
        print("Error: Could not find the search pattern in the file")
        return False

if __name__ == "__main__":
    print("Fix Agent Tool")
    print("=============")
    print(f"Target file: {AGENT_PATH}")
    print()
    
    if not os.path.exists(AGENT_PATH):
        print(f"Error: File not found at {AGENT_PATH}")
        exit(1)
    
    # Apply the fix
    remove_response_format()
