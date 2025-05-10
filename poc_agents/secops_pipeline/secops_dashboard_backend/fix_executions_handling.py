#!/usr/bin/env python
"""
Patch for dashboard backend execution handling.
This script enhances the execution handling for the SecOps Dashboard backend.
"""

import os
import sys
import json
import logging
import argparse
import re
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("dashboard-fixer")

# Root directory is one level up from this script
ROOT_DIR = Path(__file__).parent

def backup_file(file_path):
    """Create a backup of a file"""
    backup_path = f"{file_path}.bak"
    with open(file_path, 'r') as src:
        with open(backup_path, 'w') as dst:
            dst.write(src.read())
    logger.info(f"Created backup of {file_path} at {backup_path}")
    return backup_path

def fix_app_py():
    """Fix the app.py file to better handle execution list events"""
    app_py_path = ROOT_DIR / "app.py"
    
    # Backup the file
    backup_file(app_py_path)
    
    with open(app_py_path, 'r') as f:
        content = f.read()
    
    # Check if the fix is already applied
    if "Force broadcast of executions list" in content:
        logger.info("app.py already contains the fix.")
        return
    
    # Find the execution_summary handler section
    exec_summary_pattern = r"elif event_type == \"execution_summary\":(.*?)# Track alert details"
    
    # Prepare the enhanced execution_summary handler
    enhanced_handler = """
                    elif event_type == "execution_summary":
                        project_id = msg_data.get("project_id")
                        status = msg_data.get("status")
                        alert_source = msg_data.get("alert_source", "Unknown")
                        response_action = msg_data.get("response_action", "")
                        
                        logger.info(f"Processing execution_summary event for project {project_id} with status {status}")
                        
                        # Create a name based on available info
                        name = f"Alert from {alert_source}"
                        if status == "ERROR":
                            # For errors, include the error message in the name if possible
                            if "Error" in response_action:
                                name = f"Error: {response_action[:50]}..."
                            else:
                                name = f"Error in {alert_source} processing"
                        
                        # Get alert name if available by searching in alert_details events
                        # In a real implementation, this would be stored in a database
                        if project_id:
                            # Add to executions list
                            execution_data = {
                                "project_id": project_id,
                                "name": name,
                                "status": status,
                                "timestamp": datetime.now().isoformat()
                            }
                            add_execution(execution_data)
                            
                            # Force broadcast of executions list to all connected clients
                            try:
                                executions_list = get_executions()
                                executions_event = {
                                    "event_type": "execution_list",
                                    "executions": executions_list
                                }
                                logger.info(f"Broadcasting execution_list with {len(executions_list)} executions")
                                await manager.broadcast(json.dumps(executions_event))
                            except Exception as bcast_err:
                                logger.error(f"Error broadcasting execution list: {bcast_err}")
                    
                    # Also handle explicit execution_list events
                    elif event_type == "execution_list":
                        executions_data = msg_data.get("executions", [])
                        
                        if not isinstance(executions_data, list):
                            logger.warning(f"Invalid executions data: {executions_data}")
                            continue
                            
                        logger.info(f"Received execution_list event with {len(executions_data)} executions")
                        
                        # Process each execution
                        for execution in executions_data:
                            if not isinstance(execution, dict):
                                continue
                                
                            project_id = execution.get("project_id")
                            if not project_id:
                                continue
                                
                            # Add the execution to our store
                            add_execution(execution)
                        
                        # Broadcast to all clients
                        try:
                            executions_list = get_executions()
                            executions_event = {
                                "event_type": "execution_list",
                                "executions": executions_list
                            }
                            logger.info(f"Broadcasting updated execution_list with {len(executions_list)} executions")
                            await manager.broadcast(json.dumps(executions_event))
                        except Exception as bcast_err:
                            logger.error(f"Error broadcasting execution list: {bcast_err}")
                    
                    # Track alert details"""
    
    # Replace the execution_summary handler
    content = re.sub(exec_summary_pattern, enhanced_handler, content, flags=re.DOTALL)
    
    # Save the modified content
    with open(app_py_path, 'w') as f:
        f.write(content)
    
    logger.info("Updated app.py with enhanced execution list handling")

def fix_execution_storage():
    """Fix the execution_storage.py file for better execution tracking"""
    storage_py_path = ROOT_DIR / "execution_storage.py"
    
    # Backup the file
    backup_file(storage_py_path)
    
    with open(storage_py_path, 'r') as f:
        content = f.read()
    
    # Check if the fix is already applied
    if "Enhanced logging for execution storage" in content:
        logger.info("execution_storage.py already contains the fix.")
        return
    
    # Add enhanced logging in add_execution
    add_execution_pattern = r"def add_execution\([^)]+\):.*?_save_to_file\(\)"
    
    # Prepare the enhanced add_execution function
    enhanced_add_execution = """def add_execution(execution_data: Dict[str, Any]) -> None:
    """Add a new execution to storage. Enhanced logging for execution storage."""
    project_id = execution_data.get("project_id")
    if not project_id:
        logger.warning("Cannot add execution without project_id")
        return
    
    # Handle error status specifically - we want to make sure errors show up in the list
    is_error = execution_data.get("status") == "ERROR"
    
    # Format for dashboard display
    formatted_execution = {
        "project_id": project_id,
        "name": execution_data.get("name", execution_data.get("alert_name", "Unknown Alert")),
        "status": execution_data.get("status", "UNKNOWN"),
        "timestamp": execution_data.get("timestamp", datetime.now().isoformat()),
    }
    
    logger.info(f"STORAGE: Adding/updating execution {project_id} - {formatted_execution['name']} - {formatted_execution['status']}")
    
    with executions_lock:
        # Check if this execution already exists (by project_id)
        existing_index = -1
        for i, exe in enumerate(executions):
            if exe.get("project_id") == project_id:
                existing_index = i
                break
                
        if existing_index >= 0:
            # Update existing execution
            executions[existing_index] = formatted_execution
            logger.debug(f"Updated existing execution {project_id}")
        else:
            # Add new execution at the beginning (most recent first)
            executions.insert(0, formatted_execution)
            logger.info(f"Added new execution {project_id} with status {formatted_execution['status']}")
        
        # Trim to max size
        if len(executions) > MAX_EXECUTIONS:
            executions.pop()  # Remove oldest
        
        # Log all executions for diagnostic purposes
        logger.debug(f"Current executions after add/update ({len(executions)}):")
        for i, exe in enumerate(executions):
            logger.debug(f"  {i+1}. {exe.get('name')} - {exe.get('status')} - {exe.get('project_id')} ({exe.get('timestamp')})")
        
        _save_to_file()"""
    
    # Replace the add_execution function
    content = re.sub(add_execution_pattern, enhanced_add_execution, content, flags=re.DOTALL)
    
    # Save the modified content
    with open(storage_py_path, 'w') as f:
        f.write(content)
    
    logger.info("Updated execution_storage.py with enhanced logging and functionality")

def main():
    parser = argparse.ArgumentParser(description='Fix execution handling in the SecOps Dashboard backend')
    parser.add_argument('--app', action='store_true', help='Fix app.py')
    parser.add_argument('--storage', action='store_true', help='Fix execution_storage.py')
    parser.add_argument('--all', action='store_true', help='Fix all files')
    
    args = parser.parse_args()
    
    if args.all or (not args.app and not args.storage):
        fix_app_py()
        fix_execution_storage()
    else:
        if args.app:
            fix_app_py()
        if args.storage:
            fix_execution_storage()
    
    logger.info("All fixes applied successfully")
    logger.info("You need to restart the dashboard backend for changes to take effect.")

if __name__ == "__main__":
    main()
