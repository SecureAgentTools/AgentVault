#!/usr/bin/env python
"""
Research Pipeline Configuration Generator

This script provides a command-line interface for creating and modifying research pipeline
configuration files. It allows users to:
1. Generate a default configuration file
2. Modify specific parameters 
3. View current configuration settings

Example usage:
  python config_generator.py create --output my_config.json
  python config_generator.py set --file my_config.json --section scraper --param max_total_urls --value 30
  python config_generator.py view --file my_config.json --section scraper
"""

import os
import sys
import json
import argparse
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the src directory to the path for importing modules
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir))

try:
    from src.langgraph_research_orchestrator.config.pipeline_config import ResearchPipelineConfig
    CONFIG_IMPORT_SUCCESSFUL = True
    logger.info("Successfully imported ResearchPipelineConfig")
except ImportError as e:
    logger.error(f"Could not import pipeline configuration modules: {e}")
    logger.info("Running in limited mode. Some features may not be available.")
    CONFIG_IMPORT_SUCCESSFUL = False

def create_default_config(output_path):
    """Create a default configuration file."""
    if not CONFIG_IMPORT_SUCCESSFUL:
        print("Error: Cannot create default configuration without required modules.")
        print("Make sure you're running this script from the project root directory.")
        return False
    
    try:
        # Create default config
        config = ResearchPipelineConfig()
        
        # Create the configuration dictionary manually
        config_dict = {
            "search": {
                "active_engines": ["DuckDuckGo Lite", "Ecosia", "Mojeek"],
                "use_fallback_urls": True,
                "add_fallback_results": True
            },
            "scraper": {
                "max_urls_per_query": 5,
                "max_total_urls": 20,
                "scrape_timeout": 20.0,
                "request_delay_min": 1.0,
                "request_delay_max": 3.0,
                "max_content_length": 20000,
                "max_retries": 3
            },
            "fact_extraction": {
                "min_fact_chars": 50,
                "max_facts_per_content": 5,
                "extract_direct_quotes": True,
                "prioritize_statistics": True
            },
            "fact_verification": {
                "use_authority_scores": True,
                "min_confidence_threshold": 0.6,
                "detect_contradictions": True,
                "authority_score_weight": 0.7
            },
            "visualization": {
                "max_visualizations": 5,
                "prefer_chart_types": ["bar_chart", "pie_chart", "line_graph"],
                "facts_per_visualization": 5,
                "generate_svg_content": False
            },
            "content_synthesis": {
                "max_article_length": 5000,
                "include_executive_summary": True,
                "citation_style": "inline",
                "include_images_placeholder": True
            },
            "editor": {
                "style_guide": "academic",
                "reading_level_target": "college",
                "tone": "neutral",
                "suggest_improvements": True
            },
            "orchestration": {
                "recursion_limit": 15,
                "artifact_base_path": "D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts"
            }
        }
        
        # Export to file directly
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2)
            
        print(f"Default configuration successfully created at: {output_path}")
        return True
    except Exception as e:
        print(f"Error creating default configuration: {e}")
        return False

def modify_config(file_path, section, param, value):
    """Modify a specific parameter in the configuration file."""
    try:
        # Load the existing configuration file
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Validate section
        if section not in config_data:
            print(f"Error: Section '{section}' not found in configuration. Available sections: {', '.join(config_data.keys())}")
            return False
        
        # Validate parameter
        if param not in config_data[section]:
            print(f"Error: Parameter '{param}' not found in section '{section}'. Available parameters: {', '.join(config_data[section].keys())}")
            return False
        
        # Try to convert value to appropriate type
        original_value = config_data[section][param]
        try:
            if isinstance(original_value, bool):
                # Convert string to boolean
                if value.lower() in ('true', 'yes', '1', 'y'):
                    typed_value = True
                elif value.lower() in ('false', 'no', '0', 'n'):
                    typed_value = False
                else:
                    print(f"Error: Value '{value}' cannot be converted to boolean. Use 'true' or 'false'.")
                    return False
            elif isinstance(original_value, int):
                typed_value = int(value)
            elif isinstance(original_value, float):
                typed_value = float(value)
            elif isinstance(original_value, list):
                # Treat value as comma-separated list
                if value.startswith('[') and value.endswith(']'):
                    # Try to parse as JSON
                    try:
                        typed_value = json.loads(value)
                    except json.JSONDecodeError:
                        print(f"Error: Value '{value}' is not valid JSON for a list.")
                        return False
                else:
                    typed_value = [item.strip() for item in value.split(',')]
                    
                # If original list had all strings, convert all items to strings
                if original_value and all(isinstance(item, str) for item in original_value):
                    typed_value = [str(item) for item in typed_value]
                    
            else:
                # Keep as string
                typed_value = value
        except ValueError:
            print(f"Error: Value '{value}' cannot be converted to the appropriate type for '{param}'.")
            return False
        
        # Update the configuration
        config_data[section][param] = typed_value
        
        # Save the updated configuration
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)
        
        print(f"Configuration updated: {section}.{param} = {typed_value}")
        return True
    except Exception as e:
        print(f"Error modifying configuration: {e}")
        return False

def view_config(file_path, section=None, param=None):
    """View configuration settings."""
    try:
        # Load the configuration file
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Filter based on section and param
        if section:
            if section not in config_data:
                print(f"Error: Section '{section}' not found in configuration. Available sections: {', '.join(config_data.keys())}")
                return False
            
            if param:
                if param not in config_data[section]:
                    print(f"Error: Parameter '{param}' not found in section '{section}'. Available parameters: {', '.join(config_data[section].keys())}")
                    return False
                
                # Display specific parameter
                print(f"{section}.{param} = {config_data[section][param]}")
            else:
                # Display entire section
                print(f"{section}:")
                for p, v in config_data[section].items():
                    print(f"  {p} = {v}")
        else:
            # Display entire configuration
            print("Research Pipeline Configuration:")
            print(json.dumps(config_data, indent=2))
        
        return True
    except Exception as e:
        print(f"Error viewing configuration: {e}")
        return False

def validate_config(file_path):
    """Validate a configuration file against the schema."""
    if not CONFIG_IMPORT_SUCCESSFUL:
        print("Error: Cannot validate configuration without required modules.")
        return False
    
    try:
        # Load the configuration file manually first
        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            
        # Basic validation
        required_sections = ["search", "scraper", "fact_extraction", "fact_verification", 
                            "visualization", "content_synthesis", "editor", "orchestration"]
        
        for section in required_sections:
            if section not in config_data:
                print(f"Error: Missing required section '{section}' in configuration")
                return False
                
        # Try loading with Pydantic model if available
        if CONFIG_IMPORT_SUCCESSFUL:
            config = ResearchPipelineConfig(**config_data)
            print(f"Configuration file is valid: {file_path}")
            
            # Print some key configuration values
            print("\nKey configuration values:")
            print(f"- Max URLs per query: {config_data['scraper']['max_urls_per_query']}")
            print(f"- Max total URLs: {config_data['scraper']['max_total_urls']}")
            print(f"- Active search engines: {', '.join(config_data['search']['active_engines'])}")
            print(f"- Artifact storage path: {config_data['orchestration']['artifact_base_path']}")
        else:
            print(f"Basic validation passed for: {file_path}")
            print("Note: Full validation requires the ResearchPipelineConfig module")
        
        return True
    except Exception as e:
        print(f"Error validating configuration: {e}")
        return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Research Pipeline Configuration Generator")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create command
    create_parser = subparsers.add_parser("create", help="Create a default configuration file")
    create_parser.add_argument("--output", "-o", default="pipeline_config.json", help="Output file path")
    
    # Set command
    set_parser = subparsers.add_parser("set", help="Set a configuration parameter")
    set_parser.add_argument("--file", "-f", required=True, help="Configuration file path")
    set_parser.add_argument("--section", "-s", required=True, help="Configuration section")
    set_parser.add_argument("--param", "-p", required=True, help="Parameter name")
    set_parser.add_argument("--value", "-v", required=True, help="Parameter value")
    
    # View command
    view_parser = subparsers.add_parser("view", help="View configuration settings")
    view_parser.add_argument("--file", "-f", required=True, help="Configuration file path")
    view_parser.add_argument("--section", "-s", help="Configuration section (optional)")
    view_parser.add_argument("--param", "-p", help="Parameter name (optional)")
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a configuration file")
    validate_parser.add_argument("--file", "-f", required=True, help="Configuration file path")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "create":
        create_default_config(args.output)
    elif args.command == "set":
        modify_config(args.file, args.section, args.param, args.value)
    elif args.command == "view":
        view_config(args.file, args.section, args.param)
    elif args.command == "validate":
        validate_config(args.file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
