"""
LLM Client for SecOps Pipeline Using Local LM Studio Qwen3 Instance
"""

import json
import logging
import asyncio
import os
from typing import Dict, Any, List, Optional, Union

import httpx
from pydantic import BaseModel, Field

# Import LLM configuration
from shared.llm_config import get_llm_config

# Configure logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Default LM Studio URL (can be overridden with env var)
DEFAULT_LMSTUDIO_URL = "http://127.0.0.1:1234/v1"
# Default model name (can be overridden with env var)
DEFAULT_MODEL_NAME = "lmstudio-community/Qwen3-8B-GGUF"
# Timeout for LLM requests (can be overridden with env var)
DEFAULT_TIMEOUT_SECONDS = 60

class LLMMessage(BaseModel):
    """Simple message model for LLM conversations."""
    role: str = Field(..., description="Role of the message sender (system, user, assistant)")
    content: str = Field(..., description="Content of the message")

class LLMOptions(BaseModel):
    """Configuration options for LLM calls."""
    temperature: float = Field(0.7, description="Temperature for response generation")
    max_tokens: int = Field(1024, description="Maximum tokens to generate")
    top_p: float = Field(0.9, description="Top probability mass to consider")
    frequency_penalty: float = Field(0.0, description="Frequency penalty")
    presence_penalty: float = Field(0.0, description="Presence penalty")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")
    stream: bool = Field(False, description="Whether to stream the response")
    use_no_think: bool = Field(False, description="Whether to use the /no_think directive")

class LLMClient:
    """Client for interacting with LM Studio hosted Qwen3 model."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        default_system_prompt: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize the LLM client.
        
        Args:
            base_url: Base URL for LM Studio API, defaults to config or env var
            timeout: Timeout in seconds for API calls
            default_system_prompt: Default system prompt to use if none provided
            model_name: Model name to use for requests
        """
        # Get configuration
        llm_config = get_llm_config()
        
        # Use parameters or config values
        self.base_url = base_url or llm_config['api_url']
        self.timeout = timeout or llm_config['timeout']
        self.model_name = model_name or llm_config['model_name']
        self.default_system_prompt = default_system_prompt or (
            "You are an AI assistant helping with cybersecurity operations. "
            "Analyze the information provided and respond with clear, accurate insights. "
            "Be concise and focus on security implications and actionable findings."
        )
        # Use a custom timeout configuration that's more generous for LLM processing
        custom_timeout = httpx.Timeout(connect=10.0, read=self.timeout, write=10.0, pool=45.0)
        self.client = httpx.AsyncClient(timeout=custom_timeout)
        logger.info(f"LLMClient initialized with base_url: {self.base_url}, model: {self.model_name}, timeout: {self.timeout}s")
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        logger.debug("LLMClient HTTP client closed")
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
    
    async def chat_completion(
        self,
        messages: List[LLMMessage],
        options: Optional[LLMOptions] = None,
    ) -> Dict[str, Any]:
        """Send a chat completion request to the LLM API.
        
        Args:
            messages: List of messages in the conversation
            options: LLM configuration options
            
        Returns:
            The LLM response as a dictionary
        """
        options = options or LLMOptions()
        
        # Ensure there's a system message
        has_system = any(msg.role == "system" for msg in messages)
        if not has_system:
            system_msg = LLMMessage(role="system", content=self.default_system_prompt)
            messages = [system_msg] + messages
        
        # If use_no_think is enabled, append it to the last user message
        if options.use_no_think and "qwen" in self.model_name.lower():
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].role == "user":
                    messages[i].content += " /no_think"
                    break
        
        # Prepare the request payload
        payload = {
            "model": self.model_name,  # Use configured model name
            "messages": [msg.dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
            "top_p": options.top_p,
            "frequency_penalty": options.frequency_penalty,
            "presence_penalty": options.presence_penalty,
            "stream": options.stream,
        }
        
        if options.stop:
            payload["stop"] = options.stop
        
        # Set up the endpoint
        endpoint = f"{self.base_url}/chat/completions"
        
        try:
            logger.debug(f"Sending chat completion request to {endpoint}")
            start_time = asyncio.get_event_loop().time()
            
            # Use an explicit timeout that considers the LLM's processing time
            timeout = httpx.Timeout(connect=10.0, read=self.timeout, write=10.0, pool=45.0)  # Explicitly set component timeouts
            
            response = await self.client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout  # Use the custom timeout configuration
            )
            
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.debug(f"LLM request completed in {elapsed:.2f}s")
            
            response.raise_for_status()
            result = response.json()
            
            # For streaming responses, this would need to be handled differently
            if options.stream:
                logger.warning("Streaming responses not yet fully implemented")
                
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during LLM request: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"LLM API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"Request error during LLM request: {str(e)}")
            raise RuntimeError(f"LLM connection error: {str(e)}") from e
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error from LLM response: {str(e)}")
            raise RuntimeError(f"Invalid JSON response from LLM API") from e
        except Exception as e:
            logger.exception(f"Unexpected error during LLM request: {str(e)}")
            raise RuntimeError(f"LLM request failed: {str(e)}") from e

    async def analyze_alert(
        self,
        alert_data: Dict[str, Any],
        enrichment_data: Optional[Dict[str, Any]] = None,
        investigation_data: Optional[Dict[str, Any]] = None,
        use_no_think: bool = True,
    ) -> Dict[str, Any]:
        """Analyze security alert data using the LLM.
        
        Args:
            alert_data: The standardized alert data
            enrichment_data: Optional enrichment data for IOCs
            investigation_data: Optional investigation findings
            use_no_think: Whether to use the /no_think directive (default True for analysis)
            
        Returns:
            Analysis results as a dictionary
        """
        # Construct the prompt
        user_content = "## Security Alert Analysis Request\n\n"
        
        # Add alert data
        user_content += "### Alert Data\n"
        user_content += json.dumps(alert_data, indent=2) + "\n\n"
        
        # Add enrichment data if available
        if enrichment_data:
            user_content += "### Enrichment Data\n"
            user_content += json.dumps(enrichment_data, indent=2) + "\n\n"
            
        # Add investigation data if available
        if investigation_data:
            user_content += "### Investigation Findings\n"
            user_content += json.dumps(investigation_data, indent=2) + "\n\n"
        
        # Add specific instructions
        user_content += (
            "### Analysis Request\n"
            "Please analyze this security alert and provide the following:\n"
            "1. A brief summary of the alert\n"
            "2. Assessment of severity (Low, Medium, High, Critical)\n"
            "3. Recommendation for response action\n"
            "4. Any important observations or patterns\n\n"
            "Format your response as a JSON object with the following structure:\n"
            "{\n"
            '  "summary": "Brief alert summary",\n'
            '  "severity_assessment": "Medium",\n'
            '  "recommended_action": "CREATE_TICKET",\n'
            '  "observations": ["Observation 1", "Observation 2"],\n'
            '  "confidence": 0.75\n'
            "}\n"
        )
        
        # Create message list
        messages = [
            LLMMessage(
                role="system", 
                content=(
                    "You are an expert SOC analyst AI assistant. Analyze security alerts "
                    "and provide clear, accurate assessments and recommendations. "
                    "Your response should be in valid JSON format as specified in the request."
                )
            ),
            LLMMessage(role="user", content=user_content)
        ]
        
        # Set options
        options = LLMOptions(
            temperature=0.2,  # Lower temperature for more deterministic responses
            max_tokens=1024,
            use_no_think=use_no_think  # Typically use /no_think for structured analysis
        )
        
        try:
            # Call the LLM
            response = await self.chat_completion(messages, options)
            
            # Extract and parse the content
            if 'choices' in response and len(response['choices']) > 0:
                content = response['choices'][0]['message']['content']
                
                # Try to extract JSON from the response
                try:
                    # Find JSON object in response (handling potential explanatory text)
                    json_str = self._extract_json(content)
                    result = json.loads(json_str)
                    return result
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse LLM response as JSON: {str(e)}")
                    # Return a structured error response
                    return {
                        "error": "Could not parse LLM response as JSON",
                        "raw_response": content,
                        "success": False
                    }
            else:
                logger.error(f"Unexpected LLM response format: {response}")
                return {
                    "error": "Unexpected LLM response format",
                    "success": False
                }
                
        except Exception as e:
            logger.exception(f"Error during alert analysis: {str(e)}")
            return {
                "error": f"LLM processing error: {str(e)}",
                "success": False
            }
    
    async def determine_response_action(
        self,
        alert_data: Dict[str, Any],
        findings: Dict[str, Any],
        enrichment_data: Optional[Dict[str, Any]] = None,
        use_no_think: bool = True,
    ) -> Dict[str, Any]:
        """Determine appropriate response action for a security alert.
        
        Args:
            alert_data: The standardized alert data
            findings: Investigation findings
            enrichment_data: Optional enrichment data
            use_no_think: Whether to use the /no_think directive
            
        Returns:
            Response action determination as a dictionary
        """
        # Construct the prompt
        user_content = "## Security Alert Response Determination\n\n"
        
        # Add alert data
        user_content += "### Alert Data\n"
        user_content += json.dumps(alert_data, indent=2) + "\n\n"
        
        # Add investigation findings
        user_content += "### Investigation Findings\n"
        user_content += json.dumps(findings, indent=2) + "\n\n"
        
        # Add enrichment data if available
        if enrichment_data:
            user_content += "### Enrichment Data\n"
            user_content += json.dumps(enrichment_data, indent=2) + "\n\n"
        
        # Add specific instructions with available actions
        user_content += (
            "### Response Actions Available\n"
            "- CREATE_TICKET: Create a ticket in the ticketing system\n"
            "- BLOCK_IP: Block an IP address in the firewall\n"
            "- ISOLATE_HOST: Isolate a host from the network\n"
            "- CLOSE_FALSE_POSITIVE: Close the alert as a false positive\n"
            "- MANUAL_REVIEW: Flag for manual review by an analyst\n\n"
            
            "### Response Determination Request\n"
            "Based on the alert data, investigation findings, and enrichment data, determine the most appropriate "
            "response action. Format your response as a JSON object with the following structure:\n"
            "{\n"
            '  "determined_action": "CREATE_TICKET",\n'
            '  "action_parameters": {\n'
            '    "summary": "Suspicious outbound connection from dev workstation",\n'
            '    "priority": "Medium",\n'
            '    // Additional parameters specific to the action\n'
            '  },\n'
            '  "rationale": "This connection matches known C2 behavior and the investigation confirmed...",\n'
            '  "confidence": 0.85\n'
            "}\n"
        )
        
        # Create message list
        messages = [
            LLMMessage(
                role="system", 
                content=(
                    "You are an expert SOC analyst AI assistant specialized in determining appropriate "
                    "response actions for security alerts. Provide clear, reasoned recommendations "
                    "with all required parameters for the selected action. "
                    "Your response must be in valid JSON format as specified in the request."
                )
            ),
            LLMMessage(role="user", content=user_content)
        ]
        
        # Set options
        options = LLMOptions(
            temperature=0.3,  # Slightly higher temperature for response determination
            max_tokens=1024,
            use_no_think=use_no_think
        )
        
        try:
            # Call the LLM
            response = await self.chat_completion(messages, options)
            
            # Extract and parse the content
            if 'choices' in response and len(response['choices']) > 0:
                content = response['choices'][0]['message']['content']
                
                # Try to extract JSON from the response
                try:
                    json_str = self._extract_json(content)
                    result = json.loads(json_str)
                    return result
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse LLM response as JSON: {str(e)}")
                    return {
                        "error": "Could not parse LLM response as JSON",
                        "raw_response": content,
                        "success": False
                    }
            else:
                logger.error(f"Unexpected LLM response format: {response}")
                return {
                    "error": "Unexpected LLM response format",
                    "success": False
                }
                
        except Exception as e:
            logger.exception(f"Error during response determination: {str(e)}")
            return {
                "error": f"LLM processing error: {str(e)}",
                "success": False
            }
    
    async def summarize_pipeline_results(
        self,
        project_id: str,
        alert_data: Dict[str, Any],
        enrichment_data: Dict[str, Any],
        investigation_findings: Dict[str, Any],
        response_action: Dict[str, Any],
        use_no_think: bool = False,  # More creative/detailed summary might benefit from thinking
    ) -> str:
        """Generate a human-readable summary of the pipeline execution results.
        
        Args:
            project_id: The pipeline execution project ID
            alert_data: The standardized alert data
            enrichment_data: The enrichment results
            investigation_findings: The investigation findings
            response_action: The response action determination
            use_no_think: Whether to use the /no_think directive
            
        Returns:
            A formatted text summary of the pipeline execution
        """
        # Construct the prompt
        user_content = f"## SecOps Pipeline Execution Summary (Project: {project_id})\n\n"
        
        # Add execution overview
        user_content += "### Pipeline Execution Data\n\n"
        
        # Add alert summary
        user_content += "#### Alert Data\n"
        user_content += f"- Alert ID: {alert_data.get('alert_id', 'Unknown')}\n"
        user_content += f"- Name: {alert_data.get('name', 'Unknown')}\n"
        user_content += f"- Severity: {alert_data.get('severity', 'Unknown')}\n"
        user_content += f"- Source: {alert_data.get('source', 'Unknown')}\n"
        user_content += f"- Timestamp: {alert_data.get('timestamp', 'Unknown')}\n\n"
        
        # Add enrichment summary
        user_content += "#### Enrichment Results\n"
        user_content += f"- IOCs Enriched: {len(enrichment_data)}\n"
        if enrichment_data:
            user_content += "- Notable findings:\n"
            for ioc, data in list(enrichment_data.items())[:3]:  # First 3 for brevity
                user_content += f"  - {ioc}: {json.dumps(data)[:100]}...\n"
        else:
            user_content += "- No enrichment data available\n\n"
        
        # Add investigation summary
        user_content += "#### Investigation Findings\n"
        user_content += f"- Severity Assessment: {investigation_findings.get('severity', 'Unknown')}\n"
        user_content += f"- Confidence: {investigation_findings.get('confidence', 'Unknown')}\n"
        user_content += f"- Summary: {investigation_findings.get('summary', 'No summary available')}\n\n"
        
        # Add response action summary
        user_content += "#### Response Action\n"
        user_content += f"- Action: {response_action.get('determined_response_action', 'Unknown')}\n"
        if 'response_action_parameters' in response_action and response_action['response_action_parameters']:
            params = response_action['response_action_parameters']
            if isinstance(params, dict):
                user_content += "- Parameters:\n"
                for k, v in params.items():
                    user_content += f"  - {k}: {v}\n"
        
        # Add request for summary
        user_content += (
            "\n### Summary Request\n"
            "Please generate a concise yet comprehensive executive summary of this SecOps pipeline execution. "
            "Include key findings, threat assessment, actions taken, and any recommendations for further steps. "
            "The summary should be suitable for both technical and non-technical stakeholders and follow "
            "a clear structure with appropriate headers and bullet points where helpful.\n"
        )
        
        # Create message list
        messages = [
            LLMMessage(
                role="system", 
                content=(
                    "You are an expert cybersecurity communication specialist. "
                    "Create clear, concise summaries of security operations activities that highlight "
                    "key information while maintaining technical accuracy. Use appropriate formatting "
                    "with headers, bullet points, and emphasis to improve readability."
                )
            ),
            LLMMessage(role="user", content=user_content)
        ]
        
        # Set options - higher temperature for more natural language
        options = LLMOptions(
            temperature=0.7,
            max_tokens=2048,  # Longer output for summary
            use_no_think=use_no_think
        )
        
        try:
            # Call the LLM
            response = await self.chat_completion(messages, options)
            
            # Extract the content
            if 'choices' in response and len(response['choices']) > 0:
                content = response['choices'][0]['message']['content']
                return content
            else:
                logger.error(f"Unexpected LLM response format: {response}")
                return "Error: Could not generate summary due to unexpected LLM response format."
                
        except Exception as e:
            logger.exception(f"Error during pipeline summary generation: {str(e)}")
            return f"Error: Could not generate summary. LLM processing error: {str(e)}"
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON object from text that might contain explanatory content.
        
        Args:
            text: Text that may contain a JSON object
            
        Returns:
            The extracted JSON string
        """
        # Try to find JSON pattern - look for matching braces
        start_idx = text.find('{')
        
        if start_idx == -1:
            # No JSON object found
            raise ValueError("No JSON object found in response")
        
        # Count braces to find the matching end brace
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start_idx, len(text)):
            char = text[i]
            
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
                
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    
                if brace_count == 0:
                    # Found the end of the JSON object
                    return text[start_idx:i+1]
        
        # If we get here, no matching end brace was found
        raise ValueError("Malformed JSON object in response")


# Singleton instance for module-level access
_client_instance = None

async def get_llm_client() -> LLMClient:
    """Get or create the LLM client singleton instance.
    
    Returns:
        The LLM client instance
    """
    global _client_instance
    if _client_instance is None:
        # Create a new instance with configuration
        _client_instance = LLMClient()
        
        # Log warning if LLM verification failed in the config module
        try:
            from shared.llm_config import verify_llm_availability
            success, message = verify_llm_availability()
            if not success:
                logger.warning(f"LLM availability check failed: {message}")
                logger.warning("Pipeline will continue but may encounter errors when calling the LLM")
            else:
                logger.info(f"LLM availability verified: {message}")
        except Exception as e:
            logger.warning(f"Failed to verify LLM availability: {e}")
    
    return _client_instance

async def close_llm_client():
    """Close the LLM client singleton instance."""
    global _client_instance
    if _client_instance is not None:
        await _client_instance.close()
        _client_instance = None
