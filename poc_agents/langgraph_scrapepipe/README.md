# LangGraph Research Pipeline Orchestrator

This directory contains the implementation of the multi-agent research pipeline orchestrator using the LangGraph & Agentvault framework.

## Overview

This orchestrator manages the flow of information between the 7 specialized agents defined in the parent `research_pipeline` directory:

1. **Topic Research Agent** - Creates a research plan and generates search queries
2. **Content Crawler Agent** - Searches and extracts content from the web
3. **Information Extraction Agent** - Analyzes and extracts relevant information from content
4. **Fact Verification Agent** - Verifies and validates extracted information
5. **Content Synthesis Agent** - Creates a draft article from the verified information
6. **Editor Agent** - Refines and improves the draft article
7. **Visualization Agent** - Creates visualizations based on the verified facts

It leverages LangGraph to define the workflow as a state graph, providing better state management, resilience, and observability compared to the previous direct script approach.

## Key Features

- **Robust Agent Communication** - Communicates with agents using the AgentVault A2A protocol, handling both JSON-RPC and SSE streaming events with retry logic
- **Local Artifact Storage** - Stores intermediate artifacts locally, avoiding the need for S3/cloud storage
- **Error Handling** - Implements comprehensive error handling including retries for network issues and graceful failure paths
- **Conditional Workflow** - Conditionally routes execution based on success/failure of each step
- **Command Line Interface** - Provides a flexible CLI for running the pipeline with different topics and configurations
- **Central Configuration System** - Customizable settings for all aspects of the pipeline

## Prerequisites

Before running the orchestrator, ensure you have:

1. **Python 3.11+** installed
2. **Poetry** for dependency management
3. **Docker** for running the agent containers
4. All agent services running (the 7 research pipeline agents)

## Setup

1. **Install Dependencies:**

   ```bash
   cd poc_agents/langgraph_scrapepipe
   poetry install
   ```

2. **Configure Environment:**
   
   Copy the example environment file:
   
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with any necessary configuration.

3. **Ensure Agents are Running:**
   
   All 7 pipeline agents should be running. You can start them using Docker Compose from the parent directory:
   
   ```bash
   cd ../research_pipeline
   docker-compose up -d
   ```
   
   Verify they're running at these ports:
   - Topic Research: 8010
   - Content Crawler: 8011
   - Information Extraction: 8012
   - Fact Verification: 8013
   - Content Synthesis: 8014
   - Editor: 8015
   - Visualization: 8016

## Running the Orchestrator

Run the pipeline with your own research topic:

```bash
# Using the module directly
poetry run python -m src.langgraph_research_orchestrator.run --topic "Your Research Topic" --depth standard

# Or using the convenience script
python run_pipeline.py --topic "Your Research Topic" --depth standard
```

### Command Line Options

- `--topic` (required): The research topic to investigate
- `--depth`: Research depth (`brief`, `standard`, or `comprehensive`), default is `standard`
- `--focus-areas`: Optional list of focus areas, e.g., `--focus-areas "Area 1" "Area 2"`
- `--log-level`: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`), default is `INFO`
- `--project-id`: Optional custom project ID (auto-generated if not provided)
- `--config`: Path to a custom configuration file (see Configuration section)

## Configuration System

The research pipeline now features a comprehensive configuration system that allows you to customize various aspects of its behavior.

### Creating a Configuration File

```bash
python config_generator.py create --output my_config.json
```

This generates a configuration file with default settings that you can customize.

### Modifying Configuration Settings

```bash
python config_generator.py set --file my_config.json --section scraper --param max_total_urls --value 30
```

### Using a Configuration File

```bash
python run_pipeline.py --topic "Climate Change Adaptation" --config my_config.json
```

### Configuration Sections

The configuration is divided into sections for different components:

- **search**: Controls search engine selection and fallback behavior
- **scraper**: Web scraping parameters (timeouts, URL limits, etc.)
- **fact_extraction**: Controls fact extraction behavior
- **fact_verification**: Settings for fact verification
- **visualization**: Visualization generation options
- **content_synthesis**: Article generation parameters
- **editor**: Editing style and preferences
- **orchestration**: LangGraph settings and artifact paths

See [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration options.

## Pipeline Process

1. **Initialization**: Loads agent cards and prepares the initial state
2. **Topic Research**: Generates a research plan and search queries
3. **Content Crawling**: Retrieves web content based on search queries
4. **Information Extraction**: Extracts structured information from the content
5. **Fact Verification**: Verifies the extracted information
6. **Content Synthesis**: Creates a draft article from the verified facts
7. **Editing**: Refines and improves the article
8. **Visualization**: Creates visualizations based on the verified facts
9. **Completion**: Returns a final state with paths to all generated artifacts

## Output Artifacts

The pipeline generates the following artifacts, which are stored in the `pipeline_artifacts` directory (configurable):

- Research plan and search queries
- Raw content from web searches
- Extracted information
- Verified facts
- Draft article
- Edited article
- Visualization metadata

Each artifact is stored in its own subdirectory based on the project ID and pipeline step.

## Architecture

- **State Management**: LangGraph handles the flow of information between steps
- **Agent Communication**: A2A Client Wrapper handles communication with agents
- **Error Handling**: Comprehensive error handling with retries for network issues
- **Artifacts**: Local storage of all intermediate and final artifacts
- **Configuration**: Central configuration system for customizing pipeline behavior

## Troubleshooting

- **Missing Agent**: Ensure all 7 agents are running in Docker
- **Communication Error**: Check that agent cards are correctly loaded from the specified directory
- **Artifact Storage**: Make sure the `pipeline_artifacts` directory is writable
- **Empty Results**: Check the logs for errors during pipeline execution
- **Configuration Issues**: Validate your configuration file with `python config_generator.py validate --file my_config.json`

## Advanced Usage

For more advanced usage, you can import and use the `run_pipeline` function from your own code:

```python
from src.langgraph_research_orchestrator.run import run_pipeline
import asyncio

async def main():
    final_state = await run_pipeline(
        topic="Sustainable Agriculture",
        depth="comprehensive",
        focus_areas=["Vertical Farming", "Drip Irrigation", "Organic Pest Control"],
        config_path="custom_config.json"  # Optional configuration file
    )
    print(final_state)

asyncio.run(main())
```

This allows you to integrate the research pipeline into your own applications.
