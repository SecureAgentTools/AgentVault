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

def apply_format_json_fix():
    """Replace response_format with format:json parameter"""
    print("Applying fix: Use format:json parameter")
    
    # Create backup
    backup_file(AGENT_PATH)
    
    # Read the current file content
    with open(AGENT_PATH, 'r') as f:
        content = f.read()
    
    # Define the search pattern and replacement
    search_pattern = """            "response_format": { "type": "json_object" }"""
    
    replacement = """            "format": "json" # Using format:json parameter which works with this model"""
    
    # Apply the fix
    if search_pattern in content:
        new_content = content.replace(search_pattern, replacement)
        
        # Write the updated content
        with open(AGENT_PATH, 'w') as f:
            f.write(new_content)
        
        print("Successfully applied fix: Replaced response_format with format:json")
        return True
    else:
        print("Error: Could not find the search pattern in the file")
        return False

if __name__ == "__main__":
    print("Format JSON Fix Tool")
    print("===================")
    print(f"Target file: {AGENT_PATH}")
    print()
    
    if not os.path.exists(AGENT_PATH):
        print(f"Error: File not found at {AGENT_PATH}")
        exit(1)
    
    # Apply the fix
    apply_format_json_fix()
