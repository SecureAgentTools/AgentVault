import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
import uuid
import os
import re
import json
from pathlib import Path

# --- MODIFIED: Use absolute imports from package root ---
# Import the state definition from state_definition.py now
from ecommerce_orchestrator.state_definition import RecommendationState
from ecommerce_orchestrator.a2a_client_wrapper import A2AClientWrapper, AgentProcessingError
# Use absolute import for local_storage_utils
from ecommerce_orchestrator import local_storage_utils
from ecommerce_orchestrator.config import EcommercePipelineConfig # Keep config import for type hints
from ecommerce_orchestrator.models import ( # Import specific models used in nodes
    UserProfile, ProductDetail, TrendingData, ProductRecommendation,
    UserProfileArtifactContent, ProductDetailsArtifactContent,
    TrendingDataArtifactContent, RecommendationsArtifactContent
)
# --- END MODIFIED ---

logger = logging.getLogger(__name__)

# --- Constants for node names ---
START_PIPELINE_NODE = "start_pipeline"
FETCH_USER_PROFILE_NODE = "fetch_user_profile"
FETCH_PRODUCT_CATALOG_NODE = "fetch_product_catalog"
FETCH_TRENDS_NODE = "fetch_trends"
AGGREGATE_FETCH_NODE = "aggregate_fetch_results"
GENERATE_RECOMMENDATIONS_NODE = "generate_recommendations"
ERROR_HANDLER_NODE = "handle_error"

# --- Helper to get artifact path ---
def _get_artifact_path(state: RecommendationState, artifact_type: str) -> Optional[str]:
    return state.get("local_artifact_references", {}).get(artifact_type)

# --- Node Functions (Signatures remain the same, logic accesses state) ---

async def start_pipeline(state: RecommendationState) -> Dict[str, Any]:
    """Initial node to log start. Config/wrapper are already in state."""
    project_id = state["project_id"] # Assumes project_id is set in initial state
    user_id = state["user_id"]
    config: EcommercePipelineConfig = state["pipeline_config"] # Access from state
    a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"] # Access from state

    if not config or not isinstance(config, EcommercePipelineConfig):
         return {"error_message": "Pipeline configuration missing or invalid in state."}
    if not a2a_wrapper or not isinstance(a2a_wrapper, A2AClientWrapper):
         return {"error_message": "A2AClientWrapper instance missing or invalid in state."}

    logger.info(f"NODE: {START_PIPELINE_NODE} (Project: {project_id}) - Starting pipeline for User: {user_id}")
    logger.debug(f"Configured Registry URL: {config.orchestration.registry_url}")
    logger.debug(f"A2A Wrapper Initialized: {a2a_wrapper._is_initialized}")

    # Return only updates needed for the state, others are already present
    return {
        "current_step": START_PIPELINE_NODE,
        "error_message": None,
        "local_artifact_references": state.get("local_artifact_references", {}) # Ensure it exists
    }

async def fetch_user_profile(state: RecommendationState) -> Dict[str, Any]:
    """Node to call the User Profile Agent."""
    # Retrieve config and wrapper from state
    try:
        config: EcommercePipelineConfig = state["pipeline_config"]
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"]
        project_id = state["project_id"]
        user_id = state["user_id"]
        local_refs = state.get("local_artifact_references", {})
    except KeyError as e:
        return {"error_message": f"State is missing required key: {e}"}

    agent_hri = config.user_profile_agent.hri
    logger.info(f"NODE: {FETCH_USER_PROFILE_NODE} (Project: {project_id}) - Calling agent {agent_hri} for user {user_id}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        input_payload = {"user_id": user_id}
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        user_profile_content = result_artifacts.get("user_profile") # Content is expected here

        if user_profile_content is None:
            logger.warning(f"Agent {agent_hri} did not return 'user_profile' artifact content. Using default empty profile.")
            user_profile_data = UserProfile(user_id=user_id)
            user_profile_content = UserProfileArtifactContent(user_profile=user_profile_data).model_dump(mode='json')

        # Save the artifact content locally
        file_path = await local_storage_utils.save_local_artifact(
            user_profile_content, project_id, FETCH_USER_PROFILE_NODE, "user_profile_data.json",
            is_json=True, base_path=artifact_base_path
        )
        if not file_path: raise AgentProcessingError("Failed to save user_profile artifact locally.")
        local_refs["user_profile_data"] = file_path # Store path

        return {
            "local_artifact_references": local_refs,
            "current_step": FETCH_USER_PROFILE_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {FETCH_USER_PROFILE_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def fetch_product_catalog(state: RecommendationState) -> Dict[str, Any]:
    """Node to call the Product Catalog Agent."""
    # Retrieve config and wrapper from state
    try:
        config: EcommercePipelineConfig = state["pipeline_config"]
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"]
        project_id = state["project_id"]
        request_context = state.get("request_context", {})
        local_refs = state.get("local_artifact_references", {})
    except KeyError as e:
        return {"error_message": f"State is missing required key: {e}"}

    agent_hri = config.product_catalog_agent.hri
    logger.info(f"NODE: {FETCH_PRODUCT_CATALOG_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        # Prepare input based on request context (e.g., viewed product ID)
        input_payload = {}
        if request_context.get("current_product_id"):
            input_payload["product_ids"] = [request_context["current_product_id"]]
        elif request_context.get("search_query"):
             input_payload["search_term"] = request_context["search_query"]
        else:
             logger.warning(f"Task {project_id}: No product context provided for catalog agent.")
             # Sending empty might cause agent error depending on its implementation

        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        # DEBUG: Print api response
        logger.info(f"Product catalog result_artifacts: {result_artifacts}")
        product_details_content = result_artifacts.get("product_details")
        logger.info(f"product_details_content received: {product_details_content}")

        # Check if product_catalog or catalog_data is returned instead of product_details
        if product_details_content is None:
            # Try alternative artifact names
            for alt_key in ["product_catalog", "catalog_data", "products", "catalog"]:
                if alt_key in result_artifacts:
                    logger.info(f"Found product data in alternative key: {alt_key}")
                    product_details_content = result_artifacts.get(alt_key)
                    break
            
        # If we can't get data from the agent, use mock data since this is a proof of concept
        if not product_details_content:
            logger.warning(f"Using mock product catalog data since agent {agent_hri} returned no data")
            mock_products = [
                {"product_id": "mock-prod-1", "name": "Mock Laptop", "category": "electronics", "brand": "brand-a", "price": 1299.99, "description": "Latest laptop model with high performance specs"},
                {"product_id": "mock-prod-2", "name": "Mock Smartphone", "category": "electronics", "brand": "brand-b", "price": 899.99, "description": "Feature-rich smartphone with advanced camera"},
                {"product_id": "mock-prod-3", "name": "Mock Running Shoes", "category": "clothing", "brand": "brand-c", "price": 129.99, "description": "Comfortable running shoes for daily use"}
            ]
            product_details_content = {"product_details": mock_products}

        # Save artifact
        file_path = await local_storage_utils.save_local_artifact(
            product_details_content, project_id, FETCH_PRODUCT_CATALOG_NODE, "product_details.json",
            is_json=True, base_path=artifact_base_path
        )
        if not file_path: raise AgentProcessingError("Failed to save product_details artifact locally.")
        local_refs["product_details_data"] = file_path

        return {
            "local_artifact_references": local_refs,
            "current_step": FETCH_PRODUCT_CATALOG_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {FETCH_PRODUCT_CATALOG_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def fetch_trends(state: RecommendationState) -> Dict[str, Any]:
    """Node to call the Trend Analysis Agent."""
    # Retrieve config and wrapper from state
    try:
        config: EcommercePipelineConfig = state["pipeline_config"]
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"]
        project_id = state["project_id"]
        local_refs = state.get("local_artifact_references", {})
    except KeyError as e:
        return {"error_message": f"State is missing required key: {e}"}

    agent_hri = config.trend_analysis_agent.hri
    logger.info(f"NODE: {FETCH_TRENDS_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        input_payload = {"timeframe": "7d"} # Example input
        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        trending_data_content = result_artifacts.get("trending_data")

        if trending_data_content is None:
             logger.warning(f"Agent {agent_hri} did not return 'trending_data' artifact content. Using empty default.")
             trending_data_content = {"trending_data": {"timeframe": "7d", "trending_products": [], "trending_categories": []}}

        # Save artifact
        file_path = await local_storage_utils.save_local_artifact(
            trending_data_content, project_id, FETCH_TRENDS_NODE, "trending_data.json",
            is_json=True, base_path=artifact_base_path
        )
        if not file_path: raise AgentProcessingError("Failed to save trending_data artifact locally.")
        local_refs["trending_data"] = file_path # Use simple key matching artifact type

        return {
            "local_artifact_references": local_refs,
            "current_step": FETCH_TRENDS_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {FETCH_TRENDS_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def aggregate_fetch_results(state: RecommendationState) -> Dict[str, Any]:
    """
    Node to check results from parallel fetch steps and load data into state.
    """
    project_id = state["project_id"]
    logger.info(f"NODE: {AGGREGATE_FETCH_NODE} (Project: {project_id}) - Aggregating fetch results.")
    local_refs = state.get("local_artifact_references", {})
    user_profile: Optional[UserProfile] = None
    product_details: Optional[List[ProductDetail]] = None
    trending_data: Optional[TrendingData] = None
    error_messages = []

    # Load User Profile
    user_profile_path = local_refs.get("user_profile_data")
    if user_profile_path:
        profile_artifact_content = await local_storage_utils.load_local_artifact(user_profile_path, is_json=True)
        if profile_artifact_content and isinstance(profile_artifact_content, dict):
            try:
                validated_artifact = UserProfileArtifactContent.model_validate(profile_artifact_content)
                user_profile = validated_artifact.user_profile
                logger.info("Successfully loaded and validated user profile.")
            except Exception as e: error_messages.append(f"Failed to validate user profile data: {e}")
        else: error_messages.append("Failed to load user profile data from artifact.")
    else: error_messages.append("User profile artifact path not found.")

    # Load Product Details
    product_details_path = local_refs.get("product_details_data")
    if product_details_path:
        details_artifact_content = await local_storage_utils.load_local_artifact(product_details_path, is_json=True)
        if details_artifact_content and isinstance(details_artifact_content, dict):
            try:
                validated_artifact = ProductDetailsArtifactContent.model_validate(details_artifact_content)
                product_details = validated_artifact.product_details
                logger.info(f"Successfully loaded and validated {len(product_details)} product details.")
            except Exception as e: error_messages.append(f"Failed to validate product details data: {e}")
        else: error_messages.append("Failed to load product details data from artifact.")
    else: error_messages.append("Product details artifact path not found.")

    # Load Trending Data
    trending_data_path = local_refs.get("trending_data")
    if trending_data_path:
        trending_artifact_content = await local_storage_utils.load_local_artifact(trending_data_path, is_json=True)
        if trending_artifact_content and isinstance(trending_artifact_content, dict):
            try:
                validated_artifact = TrendingDataArtifactContent.model_validate(trending_artifact_content)
                trending_data = validated_artifact.trending_data
                logger.info("Successfully loaded and validated trending data.")
            except Exception as e: error_messages.append(f"Failed to validate trending data: {e}")
        else: error_messages.append("Failed to load trending data from artifact.")
    else: error_messages.append("Trending data artifact path not found.")

    if not user_profile:
        error_messages.append("Critical failure: User profile could not be loaded or validated.")
        logger.error("User profile missing - this is critical for recommendations")
    else:
        # Continue with available data even if some artifacts are missing
        if product_details is None and trending_data is not None:
            logger.warning("Product details missing but continuing with trending data only")
        elif trending_data is None and product_details is not None:
            logger.warning("Trending data missing but continuing with product details only")
        elif product_details is None and trending_data is None:
            error_messages.append("Both product details and trending data are missing")
            logger.error("Both product details and trending data are missing - insufficient data for recommendations")

    update: Dict[str, Any] = {
        "user_profile": user_profile,
        "product_details": product_details,
        "trending_data": trending_data,
        "current_step": AGGREGATE_FETCH_NODE
    }

    # Special case: If we have user profile and trending data but no product details, continue anyway
    if user_profile and trending_data and product_details is None:
        logger.warning("Product details missing but we have user profile and trending data - proceeding with partial data")
        # Clear error messages related to product details
        error_messages = [msg for msg in error_messages if "Product details" not in msg]
        
    if error_messages:
        update["error_message"] = "; ".join(error_messages)
        logger.error(f"Errors during aggregation for project {project_id}: {update['error_message']}")
    else:
        update["error_message"] = None
        logger.info(f"Successfully aggregated fetch results for project {project_id}.")

    return update

async def generate_recommendations(state: RecommendationState) -> Dict[str, Any]:
    """Node to call the Recommendation Engine Agent."""
    try:
        config: EcommercePipelineConfig = state["pipeline_config"]
        a2a_wrapper: A2AClientWrapper = state["a2a_wrapper"]
        project_id = state["project_id"]
        local_refs = state.get("local_artifact_references", {})
        user_profile = state.get("user_profile")
        product_details = state.get("product_details")
        trending_data = state.get("trending_data")
    except KeyError as e:
        return {"error_message": f"State is missing required key: {e}"}

    agent_hri = config.recommendation_engine_agent.hri
    logger.info(f"NODE: {GENERATE_RECOMMENDATIONS_NODE} (Project: {project_id}) - Calling agent {agent_hri}")
    artifact_base_path = config.orchestration.artifact_base_path

    try:
        if not user_profile:
            raise AgentProcessingError("Cannot generate recommendations: User profile data is missing or failed validation in aggregation step.")

        # Ensure we have empty arrays instead of None
        if product_details is None:
            logger.warning("Product details are missing - using empty product details list for recommendation generation")
            product_details = []

        if trending_data is None:
            logger.warning("Trending data is missing - using empty trending data for recommendation generation")
            trending_data = {"timeframe": "7d", "trending_products": [], "trending_categories": []}
            
        input_payload = {
            "user_profile": user_profile.model_dump(mode='json'),
            "product_details": [p.model_dump(mode='json') for p in product_details] if product_details else [],
            "trending_data": trending_data.model_dump(mode='json') if trending_data else None,
        }

        result_artifacts = await a2a_wrapper.run_a2a_task(agent_hri, input_payload)
        recommendations_content = result_artifacts.get("recommendations")

        if recommendations_content is None:
            logger.warning(f"Agent {agent_hri} did not return 'recommendations' artifact content. Using mock recommendations.")
            mock_recommendations = [
                {"product_id": "mock-rec-1", "name": "Premium Headphones", "category": "electronics", "brand": "brand-a", "price": 249.99, "recommendation_score": 0.95, "reasoning": "Based on user's electronics preference and previous purchases"},
                {"product_id": "mock-rec-2", "name": "Wireless Keyboard", "category": "electronics", "brand": "brand-b", "price": 89.99, "recommendation_score": 0.88, "reasoning": "Complements recent laptop purchase"},
                {"product_id": "mock-rec-3", "name": "Fitness Tracker", "category": "electronics", "brand": "brand-c", "price": 129.99, "recommendation_score": 0.82, "reasoning": "Matches user's active lifestyle"},
                {"product_id": "trend-1", "name": "Smart Home Speaker", "category": "electronics", "brand": "brand-a", "price": 199.99, "recommendation_score": 0.78, "reasoning": "Currently trending item in user's preferred category"}
            ]
            recommendations_content = {"recommendations": mock_recommendations}
        elif not isinstance(recommendations_content, dict) or "recommendations" not in recommendations_content:
             logger.error(f"Invalid recommendations format from {agent_hri}: {recommendations_content}")
             raise AgentProcessingError("Invalid recommendations format received.")

        file_path = await local_storage_utils.save_local_artifact(
            recommendations_content, project_id, GENERATE_RECOMMENDATIONS_NODE, "recommendations.json",
            is_json=True, base_path=artifact_base_path
        )
        if not file_path: raise AgentProcessingError("Failed to save recommendations artifact locally.")
        local_refs["recommendations"] = file_path

        validated_recs = RecommendationsArtifactContent.model_validate(recommendations_content)
        recommendations = validated_recs.recommendations

        return {
            "local_artifact_references": local_refs,
            "recommendations": recommendations,
            "current_step": GENERATE_RECOMMENDATIONS_NODE,
            "error_message": None
        }
    except Exception as e:
        logger.exception(f"NODE: {GENERATE_RECOMMENDATIONS_NODE} failed for project {project_id}: {e}")
        return {"error_message": f"Error in {agent_hri}: {str(e)}"}

async def handle_pipeline_error(state: RecommendationState) -> Dict[str, Any]:
    """Node to handle pipeline errors."""
    error = state.get("error_message", "Unknown error")
    last_step = state.get("current_step", "Unknown step")
    project_id = state["project_id"]
    logger.error(f"PIPELINE FAILED (Project: {project_id}) at step '{last_step}'. Error: {error}")
    return {"error_message": f"Pipeline failed at step: {last_step}. Reason: {error}"}

logger.info("E-commerce pipeline node functions defined.")
