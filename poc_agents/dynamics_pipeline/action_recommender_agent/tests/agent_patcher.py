import os
import sys
import shutil
import datetime

# Path to the agent.py file
AGENT_PATH = r"D:\AgentVault\poc_agents\dynamics_pipeline\action_recommender_agent\src\action_recommender_agent\agent.py"

# Make sure the file exists before proceeding
if not os.path.exists(AGENT_PATH):
    print(f"Error: File not found at {AGENT_PATH}")
    sys.exit(1)

# Create a backup of the original file
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{AGENT_PATH}.{timestamp}.bak"
shutil.copy2(AGENT_PATH, backup_path)
print(f"Created backup at: {backup_path}")

# The patches we want to try
patches = [
    {
        "name": "remove_response_format",
        "description": "Remove response_format parameter completely, rely on prompt instructions",
        "search": """            "temperature": 0.4, # Slightly lower temp for more deterministic structure
            "max_tokens": 600, # Allow more tokens for JSON structure + content
            # Explicitly request JSON output if the API supports it (OpenAI standard)
            # Check LM Studio docs if this specific key works or if schema in prompt is sufficient
            "response_format": { "type": "json_object" }""",
        "replace": """            "temperature": 0.4, # Slightly lower temp for more deterministic structure
            "max_tokens": 600 # Allow more tokens for JSON structure + content
            # Removed response_format as it was causing API errors with this LLM"""
    },
    {
        "name": "use_json_schema_type",
        "description": "Use json_schema type instead of json_object",
        "search": """            "response_format": { "type": "json_object" }""",
        "replace": """            "response_format": { "type": "json_schema", "schema": RECOMMENDATION_JSON_SCHEMA }"""
    },
    {
        "name": "use_format_parameter",
        "description": "Try format parameter used in some implementations",
        "search": """            "temperature": 0.4, # Slightly lower temp for more deterministic structure
            "max_tokens": 600, # Allow more tokens for JSON structure + content
            # Explicitly request JSON output if the API supports it (OpenAI standard)
            # Check LM Studio docs if this specific key works or if schema in prompt is sufficient
            "response_format": { "type": "json_object" }""",
        "replace": """            "temperature": 0.4, # Slightly lower temp for more deterministic structure
            "max_tokens": 600, # Allow more tokens for JSON structure + content
            # Using format parameter instead of response_format which caused errors
            "format": "json" """
    }
]

def apply_patch(patch_name):
    # Find the patch by name
    selected_patch = None
    for patch in patches:
        if patch["name"] == patch_name:
            selected_patch = patch
            break
    
    if not selected_patch:
        print(f"Error: Patch '{patch_name}' not found")
        return False
    
    # Read the current file content
    with open(AGENT_PATH, 'r') as f:
        content = f.read()
    
    # Apply the patch
    if selected_patch["search"] in content:
        new_content = content.replace(selected_patch["search"], selected_patch["replace"])
        
        # Write the updated content
        with open(AGENT_PATH, 'w') as f:
            f.write(new_content)
        
        print(f"Successfully applied patch: {selected_patch['name']}")
        print(f"Description: {selected_patch['description']}")
        return True
    else:
        print(f"Error: Could not find the search pattern for patch '{patch_name}'")
        return False

def restore_backup():
    """Restore from the latest backup"""
    # Find the latest backup
    backups = [f for f in os.listdir(os.path.dirname(AGENT_PATH)) 
               if f.startswith(os.path.basename(AGENT_PATH)) and f.endswith('.bak')]
    
    if not backups:
        print("No backups found to restore")
        return False
    
    # Sort by timestamp (newest last)
    backups.sort()
    latest_backup = os.path.join(os.path.dirname(AGENT_PATH), backups[-1])
    
    # Restore from this backup
    shutil.copy2(latest_backup, AGENT_PATH)
    print(f"Restored from backup: {latest_backup}")
    return True

def list_patches():
    """List all available patches"""
    print("Available patches:")
    for i, patch in enumerate(patches, 1):
        print(f"{i}. {patch['name']} - {patch['description']}")

if __name__ == "__main__":
    print("Agent Patcher Tool")
    print("=================")
    print(f"Target file: {AGENT_PATH}")
    print()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python agent_patcher.py list           - Show available patches")
        print("  python agent_patcher.py apply [name]   - Apply a specific patch")
        print("  python agent_patcher.py restore        - Restore from latest backup")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "list":
        list_patches()
    
    elif command == "apply" and len(sys.argv) >= 3:
        patch_name = sys.argv[2]
        apply_patch(patch_name)
    
    elif command == "restore":
        restore_backup()
    
    else:
        print("Invalid command or missing arguments")
        print("Use 'python agent_patcher.py' for usage information")
