"""
Prompt templates for the SecOps Investigation Agent.
"""

from .base_system_prompt import BASE_SYSTEM_PROMPT
from .alert_analysis_prompt import (
    ALERT_ANALYSIS_PROMPT,
    MALWARE_ANALYSIS_PROMPT,
    NETWORK_SCAN_ANALYSIS_PROMPT,
    DATA_TRANSFER_ANALYSIS_PROMPT
)

__all__ = [
    'BASE_SYSTEM_PROMPT',
    'ALERT_ANALYSIS_PROMPT',
    'MALWARE_ANALYSIS_PROMPT',
    'NETWORK_SCAN_ANALYSIS_PROMPT',
    'DATA_TRANSFER_ANALYSIS_PROMPT'
]