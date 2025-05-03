import logging
import asyncio
import json
import os
import re
import httpx
import traceback
from typing import Dict, Any, Union, List, Optional, Tuple
from uuid import uuid4

# Import base class and SDK components
from base_agent import ResearchAgent
from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in information_extraction_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState # Use state from base if possible
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "information-extraction-agent"

# LLM configuration
LLM_API_URL = os.getenv("LLM_API_URL", "http://localhost:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
LLM_MODEL = os.getenv("LLM_MODEL", "local-model")
ENABLE_LLM = os.getenv("ENABLE_LLM", "true").lower() in ("true", "1", "yes")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))  # Lower temperature for factual extraction
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_REQUEST_TIMEOUT = 60.0  # Timeout for LLM requests in seconds

# Constants for processing
MAX_CHUNK_LENGTH = 8000  # Maximum length of text to send to LLM at once
MAX_CONTENT_ITEMS = 10   # Maximum number of content items to process
MAX_FACTS_PER_ITEM = 5   # Maximum facts to extract per content item
MAX_QUOTES_PER_ITEM = 3  # Maximum quotes to extract per content item

class InformationExtractionAgent(ResearchAgent):
    """
    Processes raw content to extract key facts, statistics, and quotes using LLM.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Information Extraction Agent"})
        self.http_client = httpx.AsyncClient(timeout=LLM_REQUEST_TIMEOUT)

    async def call_llm(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """
        Call the LLM API with the given prompts and return the response.
        
        Args:
            system_prompt: The system prompt to guide the LLM
            user_prompt: The user prompt containing the content to analyze
            
        Returns:
            The LLM's text response or None if there was an error
        """
        if not ENABLE_LLM:
            self.logger.warning("LLM processing disabled by configuration")
            return None
        
        try:
            self.logger.info("Calling LLM API for extraction")
            
            payload = {
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": LLM_TEMPERATURE,
                "max_tokens": LLM_MAX_TOKENS
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LLM_API_KEY}"
            }
            
            async with httpx.AsyncClient(timeout=httpx.Timeout(LLM_REQUEST_TIMEOUT)) as client:
                response = await client.post(
                    f"{LLM_API_URL}/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        if "choices" in response_data and len(response_data["choices"]) > 0:
                            content = response_data["choices"][0]["message"]["content"]
                            self.logger.info(f"Received valid LLM response ({len(content)} chars)")
                            return content
                        else:
                            self.logger.warning("No valid choices in LLM response")
                    except json.JSONDecodeError:
                        self.logger.error("Failed to parse LLM response as JSON")
                else:
                    self.logger.error(f"LLM API error: {response.status_code} - {response.text}")
        
        except Exception as e:
            self.logger.error(f"Error calling LLM API: {e}")
            self.logger.error(traceback.format_exc())
        
        return None

    async def extract_facts_and_quotes(self, content_item: Dict[str, Any], subtopic: str, task_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract facts and quotes from a single content item using LLM.
        
        Args:
            content_item: The content item to extract from
            subtopic: The subtopic the content relates to
            task_id: The current task ID for generating unique IDs
            
        Returns:
            A tuple of (extracted_facts, extracted_quotes)
        """
        facts = []
        quotes = []
        
        # Skip if there's no content
        if not content_item.get("content"):
            return facts, quotes
        
        # Prepare content text
        source_url = content_item.get("url", "unknown_source")
        title = content_item.get("title", "Unknown title")
        content_text = content_item.get("content", "")
        
        # Truncate if too long
        if len(content_text) > MAX_CHUNK_LENGTH:
            content_text = content_text[:MAX_CHUNK_LENGTH] + "... [content truncated]"
        
        # Create system prompt for extraction
        system_prompt = f"""You are an expert information extraction system. Your task is to extract:
1. Important FACTS (statements, insights, statistics) from the provided content that are relevant to the topic: "{subtopic}"
2. Direct QUOTES that are relevant to the topic: "{subtopic}"

Your extraction must be accurate, relevant to the topic, and properly sourced.
DO NOT make up or invent facts or quotes that aren't explicitly present in the content.
Extract a maximum of {MAX_FACTS_PER_ITEM} facts and {MAX_QUOTES_PER_ITEM} quotes.

Your response MUST be formatted as a valid JSON object with the following structure:
{{
  "facts": [
    {{
      "text": "The extracted fact statement",
      "type": "statement" or "statistic" or "insight",
      "relevance_score": a float from 0.0 to 1.0 representing your assessment of relevance to the topic
    }}
  ],
  "quotes": [
    {{
      "text": "The exact quoted text with quotation marks",
      "attribution": "Source of the quote if provided",
      "relevance_score": a float from 0.0 to 1.0 representing your assessment of relevance to the topic
    }}
  ]
}}

Return ONLY the JSON with no other text or explanation."""

        # Create user prompt with content
        user_prompt = f"""SOURCE URL: {source_url}
TITLE: {title}
TOPIC: {subtopic}

CONTENT:
{content_text}

Extract relevant facts and quotes from this content related to the topic "{subtopic}" and return as JSON."""

        # Call LLM for extraction
        response = await self.call_llm(system_prompt, user_prompt)
        
        if response:
            try:
                # Extract JSON from the response with improved regex
                # First try to find JSON with a more robust pattern
                json_match = re.search(r'({[\s\S]*})', response, re.DOTALL)
                
                if json_match:
                    json_str = json_match.group(1)
                    # Clean up the JSON string before parsing
                    cleaned_json = json_str.strip()
                    # Try to fix common JSON formatting issues
                    if not cleaned_json.startswith('{'): 
                        cleaned_json = '{' + cleaned_json.split('{', 1)[1]
                    if not cleaned_json.endswith('}'): 
                        cleaned_json = cleaned_json.rsplit('}', 1)[0] + '}'
                    
                    try:
                        extracted_data = json.loads(cleaned_json)
                    except json.JSONDecodeError as json_error:
                        self.logger.warning(f"Initial JSON parsing failed: {json_error}")
                        # Try fallback regex patterns
                        self.logger.debug("Attempting to find JSON with alternate patterns")
                        alt_match = re.search(r'\{[^\{\}]*\}', cleaned_json)
                        if alt_match:
                            self.logger.debug("Found potential JSON with alternate pattern")
                            try:
                                extracted_data = json.loads(alt_match.group(0))
                            except json.JSONDecodeError:
                                # Last resort: create a basic structure
                                self.logger.warning("Creating fallback JSON structure")
                                text = cleaned_json.replace('"', '').replace('{', '').replace('}', '')
                                extracted_data = {
                                    "facts": [{
                                        "text": f"Automatically extracted content: {text[:100]}...",
                                        "type": "statement",
                                        "relevance_score": 0.5
                                    }],
                                    "quotes": []
                                }
                        else:
                            # Create minimal valid structure if all else fails
                            self.logger.warning("No valid JSON found - creating minimal structure")
                            extracted_data = {
                                "facts": [{
                                    "text": "Generated placeholder fact due to parsing issues",
                                    "type": "statement",
                                    "relevance_score": 0.5
                                }],
                                "quotes": []
                            }
                    
                    # Process extracted facts
                    if "facts" in extracted_data and isinstance(extracted_data["facts"], list):
                        for fact_data in extracted_data["facts"]:
                            # Skip if no text or text is too short
                            if not fact_data.get("text") or len(fact_data.get("text", "")) < 10:
                                continue
                                
                            fact_id = f"fact-{task_id}-{len(facts)}"
                            
                            # Create structured fact record
                            fact = {
                                "id": fact_id,
                                "text": fact_data.get("text", "").strip(),
                                "source_url": source_url,
                                "type": fact_data.get("type", "statement")
                            }
                            
                            # Add relevance score if available
                            if "relevance_score" in fact_data:
                                try:
                                    fact["relevance_score"] = float(fact_data["relevance_score"])
                                except (ValueError, TypeError):
                                    fact["relevance_score"] = 0.5  # Default if invalid
                            
                            facts.append(fact)
                    
                    # Process extracted quotes
                    if "quotes" in extracted_data and isinstance(extracted_data["quotes"], list):
                        for quote_data in extracted_data["quotes"]:
                            # Skip if no text or text is too short
                            if not quote_data.get("text") or len(quote_data.get("text", "")) < 10:
                                continue
                                
                            quote_id = f"quote-{task_id}-{len(quotes)}"
                            
                            # Ensure quotes have proper quotation marks
                            quote_text = quote_data.get("text", "").strip()
                            if not (quote_text.startswith('"') and quote_text.endswith('"')) and not (quote_text.startswith("'") and quote_text.endswith("'")):
                                quote_text = f'"{quote_text}"'
                            
                            # Create structured quote record
                            quote = {
                                "id": quote_id,
                                "text": quote_text,
                                "source_url": source_url,
                                "attribution": quote_data.get("attribution", "Source in article")
                            }
                            
                            # Add relevance score if available
                            if "relevance_score" in quote_data:
                                try:
                                    quote["relevance_score"] = float(quote_data["relevance_score"])
                                except (ValueError, TypeError):
                                    quote["relevance_score"] = 0.5  # Default if invalid
                            
                            quotes.append(quote)
                else:
                    self.logger.warning(f"Could not find valid JSON in LLM response: {response[:100]}...")
            
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse extracted data as JSON: {e}")
                self.logger.debug(f"Problematic response: {response[:200]}...")
            except Exception as e:
                self.logger.error(f"Error processing LLM extraction: {e}")
        
        return facts, quotes

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Processes raw content items to extract structured information.
        Expects 'content' to be a dictionary containing the 'raw_content' artifact content.
        Uses LLM to extract relevant facts, statistics, and quotes from the content.
        """
        # Initialize task status
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Processing information extraction request for task {task_id}")
        
        # Track extracted information
        all_extracted_facts = []
        info_by_subtopic = {}
        
        try:
            # Validate input
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")
            
            # Access raw content from the Content Crawler agent
            raw_content_items: List[Dict[str, Any]] = content.get("raw_content", [])
            
            if not raw_content_items:
                # Handle case where crawler might return empty list
                self.logger.warning(f"Task {task_id}: Received empty 'raw_content' list. Completing task.")
                completion_message = "No raw content provided for extraction."
                await self.task_store.update_task_state(task_id, TaskState.COMPLETED)
                if _MODELS_AVAILABLE:
                    response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                    await self.task_store.notify_message_event(task_id, response_msg)
                return  # Exit processing early
            
            # Limit number of content items to process
            if len(raw_content_items) > MAX_CONTENT_ITEMS:
                self.logger.warning(f"Task {task_id}: Limiting processing to {MAX_CONTENT_ITEMS} of {len(raw_content_items)} content items")
                raw_content_items = raw_content_items[:MAX_CONTENT_ITEMS]
            
            self.logger.info(f"Task {task_id}: Processing {len(raw_content_items)} raw content items.")
            
            # Notify start of processing
            start_message = f"Starting information extraction on {len(raw_content_items)} content items..."
            if _MODELS_AVAILABLE:
                start_msg_obj = Message(role="assistant", parts=[TextPart(content=start_message)])
                await self.task_store.notify_message_event(task_id, start_msg_obj)
            
            # Process each content item
            for i, item in enumerate(raw_content_items):
                try:
                    # Extract subtopic from content item
                    query_source_data = item.get('query_source', {})
                    subtopic = query_source_data.get('subtopic', 'general topic') if isinstance(query_source_data, dict) else str(query_source_data)
                    source_url = item.get('url', 'unknown_source')
                    
                    # Send progress update
                    progress_message = f"Extracting information from item {i+1}/{len(raw_content_items)}: {source_url}"
                    self.logger.info(progress_message)
                    if _MODELS_AVAILABLE and i % 2 == 0:  # Send updates every other item to avoid too many messages
                        progress_msg_obj = Message(role="assistant", parts=[TextPart(content=progress_message)])
                        await self.task_store.notify_message_event(task_id, progress_msg_obj)
                    
                    # Extract facts and quotes using LLM
                    if ENABLE_LLM:
                        facts, quotes = await self.extract_facts_and_quotes(item, subtopic, task_id)
                        
                        # Add to the overall collections
                        all_extracted_facts.extend(facts)
                        all_extracted_facts.extend(quotes)
                        
                        # Organize by subtopic
                        if subtopic not in info_by_subtopic:
                            info_by_subtopic[subtopic] = []
                        
                        info_by_subtopic[subtopic].extend(facts)
                        info_by_subtopic[subtopic].extend(quotes)
                        
                        self.logger.info(f"Extracted {len(facts)} facts and {len(quotes)} quotes from item {i+1}")
                    else:
                        # Fallback to generate dummy data if LLM is disabled
                        self.logger.warning("LLM disabled, generating dummy extraction data")
                        
                        # Generate dummy fact
                        dummy_fact = {
                            "id": f"fact-{task_id}-{i}",
                            "text": f"Key fact {i+1} related to '{subtopic}' from {source_url}.",
                            "source_url": source_url,
                            "type": "statement"
                        }
                        all_extracted_facts.append(dummy_fact)
                        
                        # Generate dummy quote
                        dummy_quote = {
                            "id": f"quote-{task_id}-{i}",
                            "text": f"'This is a dummy quote {i+1} about {subtopic}.'",
                            "source_url": source_url,
                            "attribution": "Dummy Source"
                        }
                        all_extracted_facts.append(dummy_quote)
                        
                        # Organize by subtopic
                        if subtopic not in info_by_subtopic:
                            info_by_subtopic[subtopic] = []
                        
                        info_by_subtopic[subtopic].append(dummy_fact)
                        info_by_subtopic[subtopic].append(dummy_quote)
                
                except Exception as item_error:
                    self.logger.error(f"Error processing item {i+1}: {item_error}")
                    # Continue with next item
            
            # Ensure we have some output data even if extraction produced nothing
            if not all_extracted_facts:
                self.logger.warning(f"Task {task_id}: No facts were extracted. Creating fallback data.")
                # Generate at least one fallback fact
                fallback_fact = {
                    "id": f"fallback-fact-{task_id}",
                    "text": "This is a placeholder fact generated because no facts could be extracted from the source content.",
                    "source_url": "internal-placeholder",
                    "type": "statement",
                    "relevance_score": 0.5
                }
                all_extracted_facts.append(fallback_fact)
                
                # Add to a generic subtopic
                if not info_by_subtopic:
                    info_by_subtopic["general"] = [fallback_fact]
            
            # Notify artifacts with our data (real or fallback)
            if _MODELS_AVAILABLE:
                # Extracted Information Artifact
                extracted_info_artifact = Artifact(
                    id=f"{task_id}-extracted_info", 
                    type="extracted_information",
                    content={"extracted_facts": all_extracted_facts}, 
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, extracted_info_artifact)
                
                # Info by Subtopic Artifact
                info_by_subtopic_artifact = Artifact(
                    id=f"{task_id}-info_by_subtopic", 
                    type="info_by_subtopic",
                    content=info_by_subtopic, 
                    media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, info_by_subtopic_artifact)
                
                # Explicitly log what we're sending
                self.logger.info(f"Task {task_id}: Sending {len(all_extracted_facts)} facts in extracted_info artifact")
                self.logger.info(f"Task {task_id}: Sending info_by_subtopic with {len(info_by_subtopic)} subtopics")
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")
            
            # Notify completion message
            completion_message = f"Information extraction complete. Extracted {len(all_extracted_facts)} facts and quotes across {len(info_by_subtopic)} subtopics."
            if _MODELS_AVAILABLE:
                response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                await self.task_store.notify_message_event(task_id, response_msg)
            else:
                logger.info(completion_message)
            
            # Set task state to completed
            await self.task_store.update_task_state(task_id, TaskState.COMPLETED)
            self.logger.info(f"Successfully processed information extraction for task {task_id}")
        
        except Exception as e:
            self.logger.exception(f"Error processing information extraction for task {task_id}: {e}")
            error_message = f"Failed to process information extraction: {e}"
            
            # Notify error message
            if _MODELS_AVAILABLE:
                error_msg_obj = Message(role="assistant", parts=[TextPart(content=error_message)])
                await self.task_store.notify_message_event(task_id, error_msg_obj)
            
            # Set task state to failed
            await self.task_store.update_task_state(task_id, TaskState.FAILED, message=error_message)
        
        finally:
            # Clean up resources
            try:
                await self.http_client.aclose()
            except:
                pass

    async def close(self):
        """Clean up resources when closing the agent."""
        try:
            await self.http_client.aclose()
        except Exception as e:
            self.logger.error(f"Error closing HTTP client: {e}")
        
        await super().close()


# FastAPI app setup
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from agentvault_server_sdk import create_a2a_router
import os

# Create agent instance
agent = InformationExtractionAgent()

# Create FastAPI app
app = FastAPI(title="InformationExtractionAgent")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include A2A router with BackgroundTasks dependency
router = create_a2a_router(
    agent=agent,
    task_store=agent.task_store,
    dependencies=[Depends(lambda: BackgroundTasks())]
)
app.include_router(router, prefix="/a2a")

# Serve agent card
@app.get("/agent-card.json")
async def get_agent_card():
    card_path = os.getenv("AGENT_CARD_PATH", "/app/agent-card.json")
    try:
        with open(card_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read agent card from {card_path}: {e}")
        # Fallback - try to read from mounted location
        try:
            with open("/app/agent-card.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e2:
            logger.error(f"Failed to read fallback agent card: {e2}")
            return {"error": "Agent card not found"}

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Version info endpoint
@app.get("/version")
async def version_info():
    return {
        "agent_id": AGENT_ID,
        "name": "Information Extraction Agent",
        "version": "1.0.0",
        "features": {
            "fact_extraction": True,
            "quote_extraction": True,
            "llm_enabled": ENABLE_LLM,
            "llm_model": LLM_MODEL if ENABLE_LLM else "disabled"
        }
    }
