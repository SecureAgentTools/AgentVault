# SecOps Pipeline Demo Materials

This directory contains materials for presenting and demonstrating the SecOps Pipeline project.

## Contents

1. **[Demo Script](demo_script.md)**: Step-by-step walkthrough of the pipeline demonstration, including talking points for each scenario.

2. **[LLM vs Rules Comparison](llm_vs_rules_comparison.md)**: A detailed comparison between traditional rule-based security analysis and LLM-enhanced security analysis, with examples.

3. **[Alert Response Matrix](alert_response_matrix.md)**: Decision matrix showing how different alert conditions map to severity levels and response actions.

## Running the Demo

To present a complete demonstration:

1. Start the pipeline components:
   ```bash
   docker-compose -f docker-compose.secops.yml up -d
   ```

2. Start the LLM backend (requires LM Studio):
   - Open LM Studio
   - Load Qwen3-8B model
   - Start local server on port 1234

3. Launch the dynamic dashboard:
   - Open `http://localhost:8080` for the static dashboard
   - Open `http://localhost:8081/dynamic_dashboard.html` for the dynamic WebSocket-connected dashboard

4. Process sample alerts sequentially for the demo:
   ```bash
   # Scenario 1: Authentication Alert
   docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert1.json
   
   # Scenario 2: Malware Alert
   docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert3.json
   
   # Scenario 3: Network Scanning Alert
   docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert4.json
   
   # Scenario 4: Data Exfiltration Alert
   docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file /app/input_alerts/sample_alert5.json
   ```

5. Use the talking points from the demo script to explain each stage of the pipeline process.

## Showcase Features

When presenting the demo, highlight these key aspects:

1. **LLM Decision Making**: Show how the Qwen3-8B model analyzes complex security scenarios with human-like reasoning.

2. **Real-time Pipeline Visualization**: Demonstrate the pipeline flow with each stage updating in real-time.

3. **Enrichment Process**: Show how raw indicators are enriched with additional context to improve decision quality.

4. **Transparent Reasoning**: Highlight the LLM's explanation of its decisions, building trust through transparency.

5. **Automated Response**: Demonstrate the different response actions (ticket creation, IP blocking, host isolation).

## Comparison with Traditional SOC

Be prepared to discuss how this approach compares to traditional Security Operations:

1. Traditional SOC processes 30-40% of alerts due to volume constraints
2. Average time to triage an alert: 8-15 minutes
3. False positive rates: 40-70% with traditional rule-based systems
4. Alert fatigue leading to missed critical events

Contrast with LLM-enhanced pipeline:
1. Can process 100% of alerts with initial automated triage
2. Average processing time: 10-15 seconds per alert
3. Estimated false positive reduction: 30-50%
4. Better prioritization reducing alert fatigue