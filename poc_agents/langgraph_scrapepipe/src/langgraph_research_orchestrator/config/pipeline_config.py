"""
Central configuration module for the Research Pipeline.

This module provides a unified configuration system for all components of the research pipeline,
including web scraping, content extraction, fact verification, and visualization settings.
"""

import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional, Union
from enum import Enum

logger = logging.getLogger(__name__)

# Base directory for the pipeline artifacts
DEFAULT_ARTIFACTS_DIR = Path("D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts")


class ResearchDepth(str, Enum):
    """Enum defining the possible research depth options."""
    BRIEF = "brief"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"


class SearchEngineConfig(BaseModel):
    """Configuration for search engine settings."""
    active_engines: List[str] = Field(
        default=["DuckDuckGo Lite", "Ecosia", "Mojeek"],
        description="List of search engines to use (can be selectively disabled)"
    )
    use_fallback_urls: bool = Field(
        default=True,
        description="Whether to use fallback URLs if search fails"
    )
    add_fallback_results: bool = Field(
        default=True,
        description="Add fallback results if too few results are found"
    )


class ScraperConfig(BaseModel):
    """Configuration for web scraping behavior."""
    max_urls_per_query: int = Field(
        default=5,
        description="Maximum number of URLs to scrape per search query",
        ge=1, le=20
    )
    max_total_urls: int = Field(
        default=20,
        description="Maximum total URLs to scrape across all queries",
        ge=5, le=100
    )
    scrape_timeout: float = Field(
        default=20.0,
        description="Timeout for each request in seconds",
        ge=5.0, le=60.0
    )
    request_delay_min: float = Field(
        default=1.0,
        description="Minimum delay between requests in seconds",
        ge=0.5, le=10.0
    )
    request_delay_max: float = Field(
        default=3.0,
        description="Maximum delay between requests in seconds",
        ge=1.0, le=15.0
    )
    max_content_length: int = Field(
        default=20000,
        description="Maximum content length to store per page",
        ge=5000, le=100000
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retries for failed requests",
        ge=0, le=10
    )
    
    @validator('request_delay_max')
    def validate_delays(cls, v, values):
        """Ensure max delay is greater than min delay."""
        if 'request_delay_min' in values and v < values['request_delay_min']:
            raise ValueError("Maximum delay must be greater than minimum delay")
        return v


class FactExtractionConfig(BaseModel):
    """Configuration for fact extraction behavior."""
    min_fact_chars: int = Field(
        default=50,
        description="Minimum character length for a valid fact",
        ge=20, le=200
    )
    max_facts_per_content: int = Field(
        default=5,
        description="Maximum facts to extract from a single content piece",
        ge=1, le=20
    )
    extract_direct_quotes: bool = Field(
        default=True,
        description="Whether to extract direct quotes as separate facts"
    )
    prioritize_statistics: bool = Field(
        default=True,
        description="Whether to prioritize extracting statistical information"
    )


class FactVerificationConfig(BaseModel):
    """Configuration for fact verification behavior."""
    use_authority_scores: bool = Field(
        default=True,
        description="Whether to use domain authority for verification"
    )
    min_confidence_threshold: float = Field(
        default=0.6,
        description="Minimum confidence score for a fact to be considered 'verified'",
        ge=0.0, le=1.0
    )
    detect_contradictions: bool = Field(
        default=True,
        description="Whether to detect contradictions between facts"
    )
    authority_score_weight: float = Field(
        default=0.7,
        description="Weight given to authority score in verification",
        ge=0.0, le=1.0
    )


class VisualizationConfig(BaseModel):
    """Configuration for visualization generation."""
    max_visualizations: int = Field(
        default=5,
        description="Maximum number of visualizations to generate",
        ge=1, le=20
    )
    prefer_chart_types: List[str] = Field(
        default=["bar_chart", "pie_chart", "line_graph"],
        description="Chart types in order of preference"
    )
    facts_per_visualization: int = Field(
        default=5,
        description="Maximum facts to include in a single visualization",
        ge=1, le=20
    )
    generate_svg_content: bool = Field(
        default=False,
        description="Whether to generate actual SVG content for visualizations (currently a placeholder)"
    )


class ContentSynthesisConfig(BaseModel):
    """Configuration for content synthesis behavior."""
    max_article_length: int = Field(
        default=5000,
        description="Maximum length of the generated article in characters",
        ge=1000, le=50000
    )
    include_executive_summary: bool = Field(
        default=True,
        description="Whether to include an executive summary"
    )
    citation_style: str = Field(
        default="inline",
        description="Citation style to use (inline, footnotes, endnotes)"
    )
    include_images_placeholder: bool = Field(
        default=True,
        description="Whether to include image placeholders in the article"
    )


class EditorConfig(BaseModel):
    """Configuration for editor behavior."""
    style_guide: str = Field(
        default="academic",
        description="Style guide to follow (academic, journalistic, business)"
    )
    reading_level_target: str = Field(
        default="college",
        description="Target reading level (elementary, high_school, college, expert)"
    )
    tone: str = Field(
        default="neutral",
        description="Tone to aim for (neutral, formal, conversational)"
    )
    suggest_improvements: bool = Field(
        default=True,
        description="Whether to suggest further improvements"
    )


class OrchestrationConfig(BaseModel):
    """Configuration for the LangGraph orchestration."""
    recursion_limit: int = Field(
        default=15,
        description="Maximum recursion steps in the graph",
        ge=5, le=50
    )
    artifact_base_path: str = Field(
        default=str(DEFAULT_ARTIFACTS_DIR),
        description="Base path for storing pipeline artifacts"
    )


class ResearchPipelineConfig(BaseModel):
    """Master configuration for the entire research pipeline."""
    search: SearchEngineConfig = Field(default_factory=SearchEngineConfig)
    scraper: ScraperConfig = Field(default_factory=ScraperConfig)
    fact_extraction: FactExtractionConfig = Field(default_factory=FactExtractionConfig)
    fact_verification: FactVerificationConfig = Field(default_factory=FactVerificationConfig)
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)
    content_synthesis: ContentSynthesisConfig = Field(default_factory=ContentSynthesisConfig)
    editor: EditorConfig = Field(default_factory=EditorConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)

    def export_to_json(self, file_path: Optional[str] = None) -> str:
        """Export the configuration to JSON format."""
        # Fix: Use model_dump() or dict() instead of json() method
        try:
            # For newer Pydantic (v2+)
            if hasattr(self, "model_dump"):
                config_dict = self.model_dump()
            # For older Pydantic
            else:
                config_dict = self.dict()
                
            json_str = json.dumps(config_dict, indent=2)
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                logger.info(f"Exported configuration to {file_path}")
            
            return json_str
        except Exception as e:
            logger.error(f"Error exporting configuration to JSON: {e}")
            # Fallback direct JSON dump of the dict
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.__dict__, f, indent=2, default=str)
                logger.info(f"Exported fallback configuration to {file_path}")
            return json.dumps(self.__dict__, indent=2, default=str)
    
    @classmethod
    def load_from_json(cls, file_path: str) -> 'ResearchPipelineConfig':
        """Load configuration from a JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Log the loaded configuration
            logger.info(f"Loading config from {file_path} with keys: {list(config_data.keys())}")
            if 'search' in config_data:
                logger.info(f"Loaded search config with use_fallback_urls={config_data.get('search', {}).get('use_fallback_urls', 'not specified')}")
                
            config = cls(**config_data)
            logger.info(f"Successfully created ResearchPipelineConfig object from {file_path}")
            return config
        except Exception as e:
            logger.error(f"Error loading configuration from {file_path}: {e}")
            logger.info("Falling back to default configuration")
            return cls()
    
    @classmethod
    def get_config(cls, config_path: Optional[str] = None) -> 'ResearchPipelineConfig':
        """
        Get configuration, either from a specified path or from environment variable.
        Falls back to default configuration if neither is available.
        """
        # First check explicit path
        if config_path and os.path.exists(config_path):
            return cls.load_from_json(config_path)
        
        # Then check environment variable
        env_config_path = os.environ.get("RESEARCH_PIPELINE_CONFIG")
        if env_config_path and os.path.exists(env_config_path):
            return cls.load_from_json(env_config_path)
        
        # Finally, check default location
        default_path = os.path.join(os.path.dirname(__file__), "default_config.json")
        if os.path.exists(default_path):
            return cls.load_from_json(default_path)
        
        # If all else fails, return default configuration
        logger.info("Using default pipeline configuration")
        return cls()


def ensure_config_object(config_input: Optional[Union[Dict[str, Any], 'ResearchPipelineConfig']]) -> Optional['ResearchPipelineConfig']:
    """
    Ensure that we have a ResearchPipelineConfig object.
    
    Args:
        config_input: Either a config object, a dictionary, or None
        
    Returns:
        A ResearchPipelineConfig object or None
    """
    if config_input is None:
        return None
        
    if isinstance(config_input, dict):
        # Convert the dictionary to a ResearchPipelineConfig object
        logger.debug("Converting dictionary to ResearchPipelineConfig object")
        try:
            return ResearchPipelineConfig(**config_input)
        except Exception as e:
            logger.warning(f"Failed to convert config dictionary to object: {e}")
            return None
    
    # It's already a config object
    if isinstance(config_input, ResearchPipelineConfig):
        return config_input
    
    # Unexpected type
    logger.warning(f"Unexpected config type: {type(config_input)}")
    return None


# Create a default configuration instance
default_config = ResearchPipelineConfig()

def get_pipeline_config(config_path: Optional[str] = None) -> ResearchPipelineConfig:
    """
    Helper function to get the pipeline configuration.
    This is the main entry point for other modules to access configuration.
    """
    config = ResearchPipelineConfig.get_config(config_path)
    
    # Ensure we're always returning a proper config object
    return ensure_config_object(config) or ResearchPipelineConfig()


if __name__ == "__main__":
    # When run directly, this will generate a default configuration file
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        output_path = sys.argv[1]
    else:
        output_path = os.path.join(os.path.dirname(__file__), "default_config.json")
    
    config = ResearchPipelineConfig()
    config.export_to_json(output_path)
    print(f"Default configuration exported to {output_path}")
