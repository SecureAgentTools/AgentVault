"""
Helper functions for working with the AgentVault Registry.
"""

import httpx
import logging
from typing import Optional

# Import with fallback mechanism
try:
    from agentvault.models.agent_card import AgentCard
    from agentvault.agent_card_utils import fetch_agent_card_from_url
    _AGENTVAULT_AVAILABLE = True
except ImportError:
    logging.warning("Failed to import AgentCard models, using placeholder")
    class AgentCard:
        """Placeholder for AgentCard model"""
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    _AGENTVAULT_AVAILABLE = False

logger = logging.getLogger(__name__)

async def load_agent_card(agent_ref: str, registry_url: str) -> Optional[AgentCard]:
    """
    Fetch an agent card from the registry by human-readable ID.
    
    Args:
        agent_ref: The human-readable ID of the agent (e.g. 'local-poc/mcp-tool-proxy')
        registry_url: The base URL of the registry (e.g. 'http://host.docker.internal:8000')
        
    Returns:
        The agent card if found, or None if not found or an error occurred
    """
    if not _AGENTVAULT_AVAILABLE:
        logger.error("Cannot load agent card: agentvault library not available")
        return None
        
    try:
        card_url = f"{registry_url}/agent/{agent_ref}/card"
        logger.info(f"Fetching agent card from: {card_url}")
        
        return await fetch_agent_card_from_url(card_url)
    except Exception as e:
        logger.exception(f"Error fetching agent card for '{agent_ref}': {e}")
        return None

# Apply the monkey patch to the agent_card_utils module if available
try:
    from agentvault import agent_card_utils
    if not hasattr(agent_card_utils, 'load_agent_card'):
        logger.info("Applying load_agent_card monkey patch to agent_card_utils module")
        agent_card_utils.load_agent_card = load_agent_card
        logger.info("Successfully applied load_agent_card monkey patch")
    else:
        logger.debug("agent_card_utils.load_agent_card already exists, no patching needed")
except ImportError:
    logger.warning("Cannot apply monkey patch: agentvault.agent_card_utils not available")
except Exception as e:
    logger.exception(f"Error applying monkey patch: {e}")
