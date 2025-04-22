# D:\AgentVault\docs\diagrams\architecture_diagram.py
import os
import platform
import subprocess
from diagrams import Diagram, Cluster, Edge
# --- Option 1: Using different built-in icons ---
from diagrams.programming.language import Python
from diagrams.programming.framework import Fastapi # Correct icon for FastAPI
from diagrams.onprem.database import Postgresql # Correct icon for the DB
# Remove the incorrect API import: from diagrams.generic.network import API
from diagrams.onprem.compute import Server # Correct module for generic Server
from diagrams.generic.device import Computer # Generic User PC/Terminal
from diagrams.generic.os import Ubuntu # Example generic OS/Node
# --- Option 2: Required for Custom Icons ---
from diagrams.custom import Custom # Import the Custom node type

# --- Define paths to your custom icons (replace with your actual filenames) ---
# Assume icons are in a 'custom_icons' subfolder relative to this script
script_dir = os.path.dirname(__file__)
icon_folder = os.path.join(script_dir, "custom_icons")

# Define paths (use raw strings `r"..."` or os.path.join for reliability)
# Replace 'placeholder_*.png' with your actual icon file names if you have them!
library_icon = os.path.join(icon_folder, "placeholder_library.png")
cli_icon = os.path.join(icon_folder, "placeholder_cli.png")
sdk_icon = os.path.join(icon_folder, "placeholder_sdk.png")
registry_icon = os.path.join(icon_folder, "placeholder_registry.png")
agent_icon = os.path.join(icon_folder, "placeholder_agent.png")
# --- End Custom Icon Paths ---


# Give the diagram a filename (without extension)
output_filename = "agentvault_high_level_architecture_v2"

# Define the diagram context
with Diagram("AgentVault High-Level Architecture (Improved Icons)",
             show=False,
             filename=output_filename,
             outformat="png", # Or "svg"
             direction="LR"): # Layout direction: Left-to-Right

    # --- Option 1 Example: Using a generic 'Computer' for the user ---
    user = Computer("Developer/User")

    # --- Main AgentVault Components (using mix of built-in & custom) ---
    with Cluster("AgentVault Monorepo Components"):
        # --- Option 2 Example: Using Custom Icons ---
        # Check if icon file exists before using Custom, otherwise fallback or raise error
        if os.path.exists(cli_icon):
            cli = Custom("agentvault_cli", cli_icon)
        else:
            print(f"Warning: Custom icon not found at {cli_icon}, using default.")
            cli = Python("agentvault_cli") # Fallback

        if os.path.exists(library_icon):
            library = Custom("agentvault_library", library_icon)
        else:
            print(f"Warning: Custom icon not found at {library_icon}, using default.")
            library = Python("agentvault_library") # Fallback

        if os.path.exists(sdk_icon):
            server_sdk = Custom("agentvault_server_sdk", sdk_icon)
        else:
            print(f"Warning: Custom icon not found at {sdk_icon}, using default.")
            server_sdk = Python("agentvault_server_sdk") # Fallback

        # testing_utils could remain Python or use a custom 'test' icon
        testing_utils = Python("agentvault_testing_utils")

        # Dependencies
        cli >> Edge(label="uses") >> library
        server_sdk >> Edge(label="uses") >> library
        testing_utils >> Edge(label="tests") >> library
        testing_utils >> Edge(label="tests") >> server_sdk

    # --- Registry Service (using mix of built-in & custom) ---
    with Cluster("AgentVault Registry Service"):
        # --- Option 1/2 Example: Choose Custom or FastAPI ---
        if os.path.exists(registry_icon):
             registry_api = Custom("Registry API", registry_icon)
        else:
             print(f"Warning: Custom icon not found at {registry_icon}, using FastAPI icon as fallback.")
             # Fallback to the accurate FastAPI icon if custom one is missing
             registry_api = Fastapi("Registry API")

        # --- Using the specific Postgresql icon ---
        registry_db = Postgresql("Registry DB")

        # UI could be Python, a generic 'Web' icon, or custom
        registry_ui = Python("Registry UI (Static/JS via FastAPI)")

        registry_api >> Edge(label="stores/retrieves") >> registry_db
        registry_ui >> Edge(label="calls") >> registry_api

    # --- Example Deployed A2A Agent (using Custom) ---
    with Cluster("Example A2A Agent Server"):
         # --- Option 2: Using Custom Agent Icon ---
         if os.path.exists(agent_icon):
             agent_server = Custom("A2A Agent", agent_icon)
         else:
             print(f"Warning: Custom icon not found at {agent_icon}, using generic Server.")
             agent_server = Server("A2A Agent") # Fallback to generic Server

         # Agent logic could be Python or custom
         agent_logic = Python("Agent Logic")

         agent_server >> Edge(label="runs") >> agent_logic # Changed label slightly
         agent_logic >> Edge(label="uses") >> server_sdk

    # Define the main interaction flows
    user >> Edge(label="runs tasks/config") >> cli
    cli >> Edge(label="queries") >> registry_api
    cli >> Edge(label="A2A Calls") >> agent_server
    registry_api >> Edge(label="validates models") >> library # More specific label
    user >> Edge(label="browses/registers") >> registry_ui


print(f"Diagram generated: {output_filename}.png (or specified outformat)")
# Add a reminder about custom icons if placeholders were used
if "placeholder_" in open(__file__).read():
     print("\nReminder: This script uses placeholder paths for custom icons.")
     print(f"Please add your actual .png/.jpg icon files to the '{icon_folder}' directory")
     print("and update the icon paths (e.g., library_icon, cli_icon) in this script.")