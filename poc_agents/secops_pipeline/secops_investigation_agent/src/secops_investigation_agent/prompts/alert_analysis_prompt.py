"""
Alert analysis prompt templates for the SecOps Investigation Agent.
These are used to generate the final prompt for the LLM when analyzing security alerts.
"""

ALERT_ANALYSIS_PROMPT = """
# SECURITY ALERT FOR ANALYSIS

## Alert Details
{alert_json}

## Enrichment Information
{enrichment_json}

## Analysis Instructions
1. Analyze the alert details and enrichment information above
2. Determine the appropriate severity level for this alert
3. Decide on the most appropriate response action
4. Provide your reasoning and confidence level for your decision

## Response Format
Respond with a JSON object in the following format:
{{
  "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL>",
  "confidence_percentage": <0-100>,
  "recommended_action": "<CREATE_TICKET|BLOCK_IP|ISOLATE_HOST>",
  "reasoning": "Your detailed analysis of why this severity and action are appropriate"
}}
"""

# Template for specific alert types
MALWARE_ANALYSIS_PROMPT = """
# MALWARE ALERT FOR ANALYSIS

## Alert Details
{alert_json}

## Enrichment Information
{enrichment_json}

## Analysis Instructions
1. Analyze the malware alert details and enrichment information above
2. Consider the malware type, family, and affected systems
3. Assess the stage of infection (initial access vs. active execution)
4. Determine if immediate containment is necessary to prevent spread
5. Provide your reasoning and confidence level for your decision

## Response Format
Respond with a JSON object in the following format:
{{
  "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL>",
  "confidence_percentage": <0-100>,
  "recommended_action": "<CREATE_TICKET|BLOCK_IP|ISOLATE_HOST>",
  "reasoning": "Your detailed analysis of why this severity and action are appropriate"
}}
"""

NETWORK_SCAN_ANALYSIS_PROMPT = """
# NETWORK SCANNING ALERT FOR ANALYSIS

## Alert Details
{alert_json}

## Enrichment Information
{enrichment_json}

## Analysis Instructions
1. Analyze the network scanning alert details and enrichment information above
2. Consider the scan source, target systems, targeted ports, and timing
3. Assess if this is a targeted attack or general internet scanning
4. Determine if immediate blocking is necessary
5. Provide your reasoning and confidence level for your decision

## Response Format
Respond with a JSON object in the following format:
{{
  "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL>",
  "confidence_percentage": <0-100>,
  "recommended_action": "<CREATE_TICKET|BLOCK_IP|ISOLATE_HOST>",
  "reasoning": "Your detailed analysis of why this severity and action are appropriate"
}}
"""

DATA_TRANSFER_ANALYSIS_PROMPT = """
# DATA TRANSFER ALERT FOR ANALYSIS

## Alert Details
{alert_json}

## Enrichment Information
{enrichment_json}

## Analysis Instructions
1. Analyze the data transfer alert details and enrichment information above
2. Consider the data volume, type of data, destination, and timing
3. Assess if this activity appears to be data exfiltration
4. Determine if the affected host needs to be isolated
5. Provide your reasoning and confidence level for your decision

## Response Format
Respond with a JSON object in the following format:
{{
  "severity": "<CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL>",
  "confidence_percentage": <0-100>,
  "recommended_action": "<CREATE_TICKET|BLOCK_IP|ISOLATE_HOST>",
  "reasoning": "Your detailed analysis of why this severity and action are appropriate"
}}
"""