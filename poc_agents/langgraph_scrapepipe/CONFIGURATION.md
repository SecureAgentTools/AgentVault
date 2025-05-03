# Research Pipeline Configuration Guide

This document explains how to configure the Research Pipeline using the central configuration system.

## Overview

The Research Pipeline now features a comprehensive configuration system that allows you to customize various aspects of the pipeline's behavior, including:

- Web scraping parameters (timeouts, number of URLs, etc.)
- Search engine selection
- Fact extraction and verification settings
- Content synthesis and editing preferences
- Visualization options
- Artifact storage paths

## Using the Configuration System

### Basic Usage

To run the pipeline with custom configuration:

```bash
python run.py --topic "Climate Change Adaptation" --config my_config.json
```

### Creating a Configuration File

Use the `config_generator.py` tool to create a configuration file:

```bash
python config_generator.py create --output my_config.json
```

This will generate a default configuration file that you can then modify.

### Modifying Configuration Parameters

You can modify specific parameters using the config generator:

```bash
python config_generator.py set --file my_config.json --section scraper --param max_total_urls --value 30
```

### Viewing Configuration Settings

To view the current configuration:

```bash
python config_generator.py view --file my_config.json
```

You can also view a specific section:

```bash
python config_generator.py view --file my_config.json --section scraper
```

Or a specific parameter:

```bash
python config_generator.py view --file my_config.json --section scraper --param max_total_urls
```

### Validating Configuration Files

You can validate a configuration file to ensure it meets the expected schema:

```bash
python config_generator.py validate --file my_config.json
```

## Configuration Sections

The configuration is divided into the following sections:

### 1. Search Configuration (`search`)

Controls how the pipeline searches for content:

- `active_engines`: List of search engines to use (e.g., "DuckDuckGo Lite", "Ecosia", "Mojeek")
- `use_fallback_urls`: Whether to use fallback URLs if search fails
- `add_fallback_results`: Whether to add fallback results if too few results are found

### 2. Scraper Configuration (`scraper`)

Controls web scraping behavior:

- `max_urls_per_query`: Maximum number of URLs to scrape per search query
- `max_total_urls`: Maximum total URLs to scrape across all queries
- `scrape_timeout`: Timeout for each request in seconds
- `request_delay_min`: Minimum delay between requests in seconds
- `request_delay_max`: Maximum delay between requests in seconds
- `max_content_length`: Maximum content length to store per page
- `max_retries`: Maximum number of retries for failed requests

### 3. Fact Extraction Configuration (`fact_extraction`)

Controls how facts are extracted from content:

- `min_fact_chars`: Minimum character length for a valid fact
- `max_facts_per_content`: Maximum facts to extract from a single content piece
- `extract_direct_quotes`: Whether to extract direct quotes as separate facts
- `prioritize_statistics`: Whether to prioritize extracting statistical information

### 4. Fact Verification Configuration (`fact_verification`)

Controls fact verification behavior:

- `use_authority_scores`: Whether to use domain authority for verification
- `min_confidence_threshold`: Minimum confidence score for a fact to be considered 'verified'
- `detect_contradictions`: Whether to detect contradictions between facts
- `authority_score_weight`: Weight given to authority score in verification

### 5. Visualization Configuration (`visualization`)

Controls visualization generation:

- `max_visualizations`: Maximum number of visualizations to generate
- `prefer_chart_types`: Chart types in order of preference (e.g., "bar_chart", "pie_chart", "line_graph")
- `facts_per_visualization`: Maximum facts to include in a single visualization
- `generate_svg_content`: Whether to generate actual SVG content for visualizations

### 6. Content Synthesis Configuration (`content_synthesis`)

Controls content synthesis behavior:

- `max_article_length`: Maximum length of the generated article in characters
- `include_executive_summary`: Whether to include an executive summary
- `citation_style`: Citation style to use (inline, footnotes, endnotes)
- `include_images_placeholder`: Whether to include image placeholders in the article

### 7. Editor Configuration (`editor`)

Controls editor behavior:

- `style_guide`: Style guide to follow (academic, journalistic, business)
- `reading_level_target`: Target reading level (elementary, high_school, college, expert)
- `tone`: Tone to aim for (neutral, formal, conversational)
- `suggest_improvements`: Whether to suggest further improvements

### 8. Orchestration Configuration (`orchestration`)

Controls LangGraph orchestration:

- `recursion_limit`: Maximum recursion steps in the graph
- `artifact_base_path`: Base path for storing pipeline artifacts

## Environment Variables

You can also specify the configuration file path using an environment variable:

```bash
export RESEARCH_PIPELINE_CONFIG=/path/to/my_config.json
python run.py --topic "Climate Change Adaptation"
```

## Configuration Flow

The pipeline loads configuration in this order of precedence:

1. Configuration file specified via command line (`--config`)
2. Configuration file specified via environment variable (`RESEARCH_PIPELINE_CONFIG`)
3. Default configuration file in the project directory
4. Built-in default configuration values

## Example Configuration

Here's an example of a complete configuration file:

```json
{
  "search": {
    "active_engines": [
      "DuckDuckGo Lite",
      "Ecosia"
    ],
    "use_fallback_urls": true,
    "add_fallback_results": true
  },
  "scraper": {
    "max_urls_per_query": 5,
    "max_total_urls": 30,
    "scrape_timeout": 15.0,
    "request_delay_min": 2.0,
    "request_delay_max": 5.0,
    "max_content_length": 30000,
    "max_retries": 5
  },
  "fact_extraction": {
    "min_fact_chars": 50,
    "max_facts_per_content": 8,
    "extract_direct_quotes": true,
    "prioritize_statistics": true
  },
  "fact_verification": {
    "use_authority_scores": true,
    "min_confidence_threshold": 0.7,
    "detect_contradictions": true,
    "authority_score_weight": 0.8
  },
  "visualization": {
    "max_visualizations": 3,
    "prefer_chart_types": [
      "bar_chart",
      "line_graph",
      "pie_chart"
    ],
    "facts_per_visualization": 5,
    "generate_svg_content": false
  },
  "content_synthesis": {
    "max_article_length": 8000,
    "include_executive_summary": true,
    "citation_style": "inline",
    "include_images_placeholder": true
  },
  "editor": {
    "style_guide": "academic",
    "reading_level_target": "college",
    "tone": "formal",
    "suggest_improvements": true
  },
  "orchestration": {
    "recursion_limit": 15,
    "artifact_base_path": "D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts"
  }
}
```

## Programmatic Access

You can also access the configuration programmatically:

```python
from langgraph_research_orchestrator.config import get_pipeline_config

# Load the default configuration
config = get_pipeline_config()

# Load a specific configuration file
config = get_pipeline_config('/path/to/config.json')

# Access configuration parameters
max_urls = config.scraper.max_total_urls
artifact_path = config.orchestration.artifact_base_path
```

## Troubleshooting

### Common Issues

1. **Configuration file not found**: Ensure the path to your configuration file is correct.
2. **Invalid JSON**: Validate your JSON syntax with a tool like [JSONLint](https://jsonlint.com/).
3. **Invalid parameter values**: Use the `validate` command to check your configuration file.
4. **Permissions issues**: Ensure the specified artifact path is writable.

### Logging

The pipeline logs configuration-related events. To see more detailed logs:

```bash
python run.py --topic "Climate Change Adaptation" --log-level DEBUG --config my_config.json
```

## Advanced Usage

### Temporary Configuration

You can create temporary configuration files for specific runs:

```python
from langgraph_research_orchestrator.config import ResearchPipelineConfig

# Create a configuration with specific overrides
config = ResearchPipelineConfig(
    scraper={"max_total_urls": 50},
    orchestration={"artifact_base_path": "/tmp/research-artifacts"}
)

# Export to a temporary file
config.export_to_json("/tmp/temp_config.json")
```

### Extending the Configuration System

To add new configuration parameters:

1. Add new fields to the appropriate model class in `pipeline_config.py`
2. Update the relevant components to use the new parameters
3. Update this documentation

## Further Support

If you encounter issues with the configuration system, please consult the following:

- Check the logs for detailed error messages
- Ensure your configuration file follows the expected schema
- Use the validation tool to verify your configuration file
