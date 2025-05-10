# Alert Response Decision Matrix

## Alert Type: Authentication Anomalies

| Condition | Severity | Confidence | Recommended Action | Reasoning |
|-----------|----------|------------|-------------------|-----------|
| Failed logins + successful login from TOR exit node outside business hours | Medium | 85% | CREATE_TICKET | Suspicious pattern but requires investigation before taking disruptive actions |
| Same as above + admin/privileged account | High | 90% | CREATE_TICKET | Higher severity due to privileged access, but still needs investigation |
| Same as above + prior similar alerts for same user | High | 95% | BLOCK_IP | Pattern of suspicious activity justifies blocking |
| Multiple failed logins from multiple accounts from single IP | High | 85% | BLOCK_IP | Clear pattern of automated brute force attempt |

## Alert Type: Malware Detection

| Condition | Severity | Confidence | Recommended Action | Reasoning |
|-----------|----------|------------|-------------------|-----------|
| Ransomware/wiper behavior detected | Critical | 95% | ISOLATE_HOST | Immediate containment needed to prevent spread |
| Trojan/backdoor detection | High | 85% | ISOLATE_HOST | High risk of lateral movement/escalation |
| Potentially unwanted program (PUP) | Low | 70% | CREATE_TICKET | Low risk, requires cleanup but not emergency |
| Known malware on non-critical system | Medium | 80% | CREATE_TICKET | Requires remediation but lower urgency |

## Alert Type: Network Scanning

| Condition | Severity | Confidence | Recommended Action | Reasoning |
|-----------|----------|------------|-------------------|-----------|
| External IP scanning multiple systems | Medium | 80% | BLOCK_IP | Clear pattern of reconnaissance |
| Internal host scanning multiple systems | High | 85% | CREATE_TICKET | Potential lateral movement but could be IT tools |
| Targeted scan of critical services | High | 90% | BLOCK_IP | Focused attack targeting critical infrastructure |
| Low-volume periodic scanning | Low | 75% | CREATE_TICKET | Common internet background scanning |

## Alert Type: Data Transfer

| Condition | Severity | Confidence | Recommended Action | Reasoning |
|-----------|----------|------------|-------------------|-----------|
| Large data transfer to unknown external destination | High | 85% | CREATE_TICKET | Potential data exfiltration but needs investigation |
| Departing employee accessing unusual amount of data | High | 90% | ISOLATE_HOST | Clear risk of data theft before departure |
| Unusual transfer pattern + sensitive data | Critical | 90% | ISOLATE_HOST | High likelihood of data breach in progress |
| Moderate increase in data transfer volume | Medium | 70% | CREATE_TICKET | Anomaly requires investigation but may be legitimate |

## Implementation Notes

1. This matrix represents example decisions, but the LLM can make nuanced assessments beyond these specific conditions.

2. The LLM always provides confidence scores to indicate its certainty in the assessment.

3. Business context is considered in all decisions (e.g., impact of isolation vs. security risk).

4. Response actions are ordered by increasing impact:
   - CREATE_TICKET: Lowest impact, requires human review
   - BLOCK_IP: Medium impact, blocks external communication
   - ISOLATE_HOST: Highest impact, disconnects system from network

5. This matrix should be continuously refined based on feedback from security analysts.