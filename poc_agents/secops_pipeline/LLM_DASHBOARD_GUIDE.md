# Understanding LLM Results in the SecOps Dashboard

This guide explains how to interpret the LLM-generated results displayed in the SecOps pipeline dashboard.

## Dashboard Overview

The SecOps dashboard provides a real-time visualization of the security pipeline execution, with particular emphasis on the LLM analysis and decision-making components. The dashboard is divided into several sections, each providing insights into different aspects of the pipeline.

## Pipeline Execution Flow

![Pipeline Flow](./demo_materials/images/pipeline_flow.png)

The top section of the dashboard displays the current state of the pipeline execution with these stages:

1. **Start**: Pipeline initialization
2. **Ingest Alert**: Standardization of the alert data
3. **Enrichment**: IOC lookup and context gathering
4. **Investigation**: LLM-powered analysis (critical LLM component)
5. **Determine Response**: LLM decision on appropriate action (critical LLM component)
6. **Execute Response**: Implementation of the determined action
7. **Complete**: Successful pipeline completion

The currently active step is highlighted, providing real-time visibility into where the alert is in the processing workflow.

## LLM-Enhanced Decision Section

![LLM Decision](./demo_materials/images/llm_decision.png)

This section displays the output from the LLM's investigation of the alert:

### Severity Rating

The LLM assigns a severity level to the alert based on its analysis:
- **Critical**: Immediate action required, high potential impact
- **High**: Urgent attention needed, significant potential impact
- **Medium**: Important but not urgent, moderate potential impact
- **Low**: Routine monitoring sufficient, minimal potential impact

### Confidence Percentage

This indicates how confident the LLM is in its assessment. Higher percentages (>80%) indicate high certainty, while lower percentages suggest there may be ambiguity in the alert data.

### Determined Action

The specific response action the LLM has recommended:
- **CREATE_TICKET**: Create a ticket in the ticketing system for investigation
- **BLOCK_IP**: Block a malicious IP address at the network perimeter
- **ISOLATE_HOST**: Isolate a compromised system from the network
- **CLOSE_FALSE_POSITIVE**: Dismiss the alert as a false positive
- **MANUAL_REVIEW**: Flag for human analysis due to uncertainty

### LLM Reasoning

The most important section for transparency, this displays the LLM's step-by-step reasoning process that led to its decision. This text explains:
- Which factors the LLM considered most important
- How it weighed different pieces of evidence
- Why it arrived at its severity assessment
- The justification for its recommended action

## Enrichment Results Section

![Enrichment Results](./demo_materials/images/enrichment.png)

This section displays the context gathered for Indicators of Compromise (IOCs) mentioned in the alert:

### Indicator Table

A table listing each identified IOC with:
- **Indicator Value**: The actual IOC (IP, domain, hash, etc.)
- **Type**: The IOC type (IP, Domain, Hash, etc.)
- **Verdict**: The reputation assessment (Clean, Suspicious, Malicious)

### Additional Context

Additional information gathered during enrichment, potentially including:
- **IP Location**: Geographic information for IP addresses
- **Previous Activity**: History of the indicator
- **Enrichment Source**: Where the context data was obtained

The LLM uses this enrichment data in its analysis, and references to these indicators often appear in the LLM reasoning section.

## Response Action Execution Section

![Response Action](./demo_materials/images/response_action.png)

This section shows the outcome of the LLM-determined response:

### Action Type

The specific action that was executed, matching the LLM's determination.

### Status

Whether the action was successfully executed:
- **Success**: Action completed successfully
- **Partial**: Action partially completed
- **Failed**: Action could not be completed

### Action Details

Specific information about the action execution:
- For tickets: Ticket ID, URL, etc.
- For blocking: Rule ID, block status, etc.
- For isolation: Isolation ID, affected system, etc.

## Interpreting LLM Responses

When evaluating the LLM's analysis and decisions in the dashboard:

1. **Check Reasoning Transparency**: The LLM should clearly articulate its thought process, considering multiple factors and explaining how they influenced its decision.

2. **Verify Evidence Correlation**: The reasoning should reference specific elements from the alert and enrichment data, demonstrating the LLM is basing its analysis on the actual data.

3. **Evaluate Severity Appropriateness**: The assigned severity should align with the actual risk the alert represents based on factors like:
   - Potential impact if the threat is real
   - Likelihood the alert represents a true threat
   - Criticality of affected systems

4. **Assess Decision Justification**: The response action should logically follow from the severity and confidence assessment.

5. **Consider Confidence Level**: Lower confidence levels suggest the LLM is uncertain and these cases may warrant additional human review.

## Potential LLM Analysis Issues

Watch for these potential issues in the LLM analysis:

1. **Hallucinations**: The LLM references facts not present in the alert or enrichment data
2. **Overconfidence**: High confidence despite limited or ambiguous information
3. **Underconfidence**: Low confidence despite clear indicators
4. **Inconsistency**: Reasoning that doesn't align with the final decision
5. **Failure to Prioritize**: Equal weight given to all factors regardless of importance

If you observe these issues, you may need to review the LLM prompts or adjust the model parameters.

## Advanced Feature: /no_think Mode

The Qwen3-8B model supports a "/no_think" mode that provides more direct responses without showing detailed reasoning steps. When this mode is enabled, the LLM Reasoning section will be more concise and focused on conclusions rather than the step-by-step analysis process.

This mode is useful for:
- High-volume processing where speed is critical
- Situations where only the decision is needed, not the explanation
- Integration with other systems that only require the final determination

However, for maximum transparency and auditability, the default mode with full reasoning is recommended for most security operations contexts.