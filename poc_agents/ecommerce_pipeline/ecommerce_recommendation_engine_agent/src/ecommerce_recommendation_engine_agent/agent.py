import logging
import asyncio
import json
import os
import random
from typing import Dict, Any, Union, Optional, List
from pydantic import ValidationError
import httpx

# LLM Integration
LLM_API_URL = os.environ.get("LLM_API_URL", "http://host.docker.internal:1234/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "lm-studio")

# Import base class and SDK components
try:
    from base_agent import ResearchAgent
except ImportError:
    try:
         from ...research_pipeline.base_agent import ResearchAgent
    except ImportError:
        logging.getLogger(__name__).critical("Could not import BaseA2AAgent. Agent will not function.")
        class ResearchAgent: # type: ignore
             def __init__(self, *args, **kwargs): pass
             async def process_task(self, task_id, content): pass
             task_store = None # type: ignore

from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError

# Import models from this agent's models.py
from .models import (
    UserProfile, ProductDetail, TrendingData, ProductRecommendation,
    RecommendationsArtifactContent
)

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact, DataPart
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in recommendation_engine_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    class DataPart: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState if hasattr(ResearchAgent, 'task_store') and ResearchAgent.task_store else None # type: ignore
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "local-poc/ecommerce-recommendation-engine"

class RecommendationEngineAgent(ResearchAgent):
    """
    Generates product recommendations based on user profile, product context, and trends.
    (Currently uses mock logic).
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Recommendation Engine Agent"})
        # Placeholder for loading recommendation models or parameters
        
    async def call_llm(self, prompt: str, system_prompt: str = None) -> str:
        """Call the LLM API with the given prompt."""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LLM_API_KEY}"
            }
            
            payload = {
                "model": "openhermes" if "openhermes" in LLM_API_URL else "llama3",
                "messages": []
            }
            
            if system_prompt:
                payload["messages"].append({"role": "system", "content": system_prompt})
                
            payload["messages"].append({"role": "user", "content": prompt})
            
            self.logger.info(f"Calling LLM API at: {LLM_API_URL}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{LLM_API_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120.0
                )
                
                if response.status_code != 200:
                    self.logger.error(f"LLM API error: {response.status_code} - {response.text}")
                    return f"Error: {response.status_code}"
                    
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "No response")
                
        except Exception as e:
            self.logger.error(f"Error calling LLM: {e}")
            return f"Error: {str(e)}"

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Generates recommendations based on the combined input data.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Processing recommendation request.")
        recommendations_list = []
        final_state = TaskState.FAILED
        error_message = "Failed to generate recommendations."
        completion_message = error_message

        try:
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # Validate and extract input data using Pydantic models
            try:
                user_profile_data = content.get("user_profile")
                product_details_data = content.get("product_details", []) # Default to empty list
                trending_data_data = content.get("trending_data")

                # Validate required inputs
                if not user_profile_data: raise ValueError("Missing 'user_profile' in input.")
                # Optional inputs: product_details, trending_data

                user_profile = UserProfile.model_validate(user_profile_data)
                product_details = [ProductDetail.model_validate(p) for p in product_details_data] if product_details_data else []
                trending_data = TrendingData.model_validate(trending_data_data) if trending_data_data else TrendingData(timeframe="unknown") # Default if missing

            except (ValidationError, ValueError, TypeError) as val_err: # Catch Pydantic and other validation errors
                self.logger.error(f"Task {task_id}: Invalid input data structure: {val_err}")
                raise AgentProcessingError(f"Invalid input data structure: {val_err}")

            max_recs = content.get("max_recommendations", 10)
            self.logger.info(f"Task {task_id}: Generating max {max_recs} recommendations for user '{user_profile.user_id}'.")
            self.logger.debug(f"Task {task_id}: Using {len(product_details)} context products and trends for {trending_data.timeframe}.")

            # --- LLM-based Recommendation Logic ---
            self.logger.info(f"Task {task_id}: Using LLM to generate personalized recommendations")
            
            # Prepare user profile summary
            user_profile_summary = (
                f"User ID: {user_profile.user_id}\n" +
                f"Preferred categories: {', '.join(user_profile.preferences.categories)}\n" +
                f"Preferred brands: {', '.join(user_profile.preferences.brands)}\n" +
                f"Purchase history: {', '.join(user_profile.purchase_history)}\n" +
                f"Recently browsed: {', '.join(user_profile.browsing_history[-5:] if len(user_profile.browsing_history) > 5 else user_profile.browsing_history)}"
            )
            
            # Prepare product details summary
            product_details_summary = "Available Product Details:\n"
            if product_details:
                for i, product in enumerate(product_details[:5]):  # Limit to 5 for prompt size
                    product_details_summary += f"{i+1}. ID: {product.product_id}, Name: {product.name}, Category: {product.category}, Brand: {product.brand}, Price: ${product.price}\n"
            else:
                product_details_summary += "No specific product details available."
            
            # Prepare trending data summary
            trending_summary = f"Trending for {trending_data.timeframe}:\n"
            if trending_data.trending_products:
                trending_summary += f"Trending products: {', '.join(trending_data.trending_products[:7])}\n"
            if trending_data.trending_categories:
                trending_summary += f"Trending categories: {', '.join(trending_data.trending_categories)}"
            else:
                trending_summary += "No trending data available."
            
            # Build LLM prompt
            system_prompt = (
                "You are an expert e-commerce recommendation system. Your task is to recommend products to users based on their profile, browsing history, "
                "and trending data. Generate detailed, personalized recommendations with clear reasoning."
            )
            
            prompt = f"""
            Based on the following information, generate {max_recs} product recommendations with reasoning:
            
            {user_profile_summary}
            
            {product_details_summary}
            
            {trending_summary}
            
            For each recommendation, provide:
            1. Product ID (in format 'rec-X' where X is a number if creating new ones)
            2. Product name
            3. Category (electronics, books, clothing, etc.)
            4. Brand (prefer user's preferred brands when possible)
            5. Price (reasonable for the category)
            6. Recommendation score (0.0-1.0)
            7. Reasoning (why this product would appeal to this user)
            
            Format each recommendation as a JSON object. Return an array of these objects.
            """
            
            # Call the LLM
            self.logger.info(f"Task {task_id}: Sending recommendation request to LLM")
            llm_response = await self.call_llm(prompt, system_prompt)
            self.logger.info(f"Task {task_id}: Received LLM response: {llm_response[:100]}...")
            
            # Try to extract JSON from the LLM response
            try:
                # Look for JSON array in the response
                json_start = llm_response.find('[')
                json_end = llm_response.rfind(']') + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = llm_response[json_start:json_end]
                    parsed_recs = json.loads(json_str)
                    
                    # Convert parsed recommendations to our model
                    for rec in parsed_recs[:max_recs]:
                        if isinstance(rec, dict):
                            try:
                                product_id = rec.get('product_id', f"rec-{random.randint(1000, 9999)}")
                                recommendations_list.append(ProductRecommendation(
                                    product_id=product_id,
                                    name=rec.get('name', 'Unknown Product'),
                                    category=rec.get('category', 'general'),
                                    brand=rec.get('brand', 'unknown'),
                                    price=float(rec.get('price', 99.99)),
                                    recommendation_score=float(rec.get('recommendation_score', 0.7)),
                                    reasoning=rec.get('reasoning', 'Recommended based on user preferences')
                                ))
                            except (ValueError, TypeError) as e:
                                self.logger.warning(f"Task {task_id}: Could not parse recommendation: {e}")
                else:
                    raise ValueError("No JSON array found in LLM response")
                    
            except Exception as e:
                self.logger.warning(f"Task {task_id}: Could not parse LLM recommendations: {e}. Using fallback.")
                # Fallback to simpler parsing - try to create recommendations from text
                try:
                    lines = llm_response.split('\n')
                    current_rec = {}
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        if line.startswith('Product ID') and current_rec:
                            # New recommendation starting, save the previous one
                            if 'product_id' in current_rec and 'reasoning' in current_rec:
                                recommendations_list.append(ProductRecommendation(
                                    product_id=current_rec.get('product_id', f"rec-{random.randint(1000, 9999)}"),
                                    name=current_rec.get('name', 'Unknown Product'),
                                    category=current_rec.get('category', 'general'),
                                    brand=current_rec.get('brand', 'unknown'),
                                    price=float(current_rec.get('price', 99.99)),
                                    recommendation_score=float(current_rec.get('recommendation_score', 0.7)),
                                    reasoning=current_rec.get('reasoning', 'Recommended based on user preferences')
                                ))
                            current_rec = {}
                            
                        # Parse key-value pairs
                        for key in ['product_id', 'name', 'category', 'brand', 'price', 'recommendation_score', 'reasoning']:
                            if line.lower().startswith(key.lower()):
                                value = line.split(':', 1)[1].strip() if ':' in line else ''
                                current_rec[key] = value
                    
                    # Add the last recommendation if valid
                    if current_rec and 'product_id' in current_rec and 'reasoning' in current_rec:
                        recommendations_list.append(ProductRecommendation(
                            product_id=current_rec.get('product_id', f"rec-{random.randint(1000, 9999)}"),
                            name=current_rec.get('name', 'Unknown Product'),
                            category=current_rec.get('category', 'general'),
                            brand=current_rec.get('brand', 'unknown'),
                            price=float(current_rec.get('price', 99.99)),
                            recommendation_score=float(current_rec.get('recommendation_score', 0.7)),
                            reasoning=current_rec.get('reasoning', 'Recommended based on user preferences')
                        ))
                except Exception as parse_err:
                    self.logger.error(f"Task {task_id}: Fallback parsing failed: {parse_err}")
            
            # If we still don't have recommendations, use the fallback mock logic
            if not recommendations_list:
                self.logger.warning(f"Task {task_id}: LLM recommendations failed. Using mock fallback logic.")
                # Create some generic recommendations
                categories = user_profile.preferences.categories or ["electronics", "books", "clothing"]
                brands = user_profile.preferences.brands or ["brand-a", "brand-b", "brand-c"]
                
                for i in range(min(max_recs, 5)):
                    category = random.choice(categories)
                    brand = random.choice(brands)
                    recommendations_list.append(ProductRecommendation(
                        product_id=f"fallback-{i+1}",
                        name=f"Fallback {category.title()} Item {i+1}",
                        category=category,
                        brand=brand,
                        price=round(random.uniform(49.99, 299.99), 2),
                        recommendation_score=round(random.uniform(0.6, 0.8), 2),
                        reasoning=f"Recommended {category} from preferred brand {brand}."
                    ))

            if _MODELS_AVAILABLE:
                artifact_content = RecommendationsArtifactContent(recommendations=recommendations_list).model_dump(mode='json')
                recs_artifact = Artifact(
                    id=f"{task_id}-recs", type="recommendations",
                    content=artifact_content,
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, recs_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")

            completion_message = f"Generated {len(recommendations_list)} product recommendations for user '{user_profile.user_id}'."
            final_state = TaskState.COMPLETED
            error_message = None # Clear error on success

        except AgentProcessingError as agent_err:
             self.logger.error(f"Task {task_id}: Agent processing error: {agent_err}")
             error_message = str(agent_err)
        except Exception as e:
            self.logger.exception(f"Task {task_id}: Unexpected error: {e}")
            error_message = f"Unexpected error generating recommendations: {e}"

        finally:
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else:
                 logger.info(f"Task {task_id}: {completion_message}")

            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            self.logger.info(f"Task {task_id}: EXITING process_task. Final State: {final_state}")

    async def close(self):
        """Close any resources."""
        await super().close()
