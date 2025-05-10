# SecOps Pipeline Demo Script

## Introduction (30 seconds)
"Welcome to our demonstration of an LLM-powered Security Operations Pipeline. This system leverages the Qwen3-8B large language model to analyze security alerts, make risk assessments, and determine appropriate responses - automating key decision points in security operations while maintaining full transparency."

## Pipeline Architecture (30 seconds)
[SHOW DASHBOARD PIPELINE VISUALIZATION]
"Our pipeline consists of several stages: alert ingestion, enrichment of security indicators, LLM-powered investigation, response determination, and automated action execution. The entire process is visualized in this interactive dashboard. The LLM integration uses direct API calls to Qwen3-8B to provide real-time security reasoning."

## Demo Scenario 1: Suspicious Authentication (1 minute)
[LOAD SAMPLE_ALERT1.JSON]
"Let's examine our first scenario - a suspicious authentication alert. Here we see a user logging in from a Tor exit node outside normal business hours, after multiple failed attempts. Watch as we send this to Qwen3-8B for analysis..."

[SHOW LLM REASONING SECTION]
"The LLM's reasoning is completely transparent - you can see it evaluate the combination of failed attempts, unusual source, and non-business hours access. Since this is a finance administrator account, it determines this is a Medium severity issue with an 85% confidence rating, and recommends creating a security ticket for investigation while not taking more disruptive actions due to the possibility of legitimate use."

## Demo Scenario 2: Malware Detection (1 minute)
[LOAD SAMPLE_ALERT3.JSON]
"In our second scenario, we have a ransomware detection alert. The system identifies BlackCat ransomware behavior on an engineering workstation. Let's see how the LLM analyzes this high-severity situation."

[SHOW LLM DECISION AND RESPONSE ACTION]
"Notice how the LLM reasons about multiple factors: the specific ransomware variant identified, the affected system being an engineering workstation, and the indicators of lateral movement. It recognizes this as a Critical severity incident with high confidence and recommends immediate host isolation to prevent further damage."

## Dashboard Features (30 seconds)
[SHOW DYNAMIC DASHBOARD]
"Our dashboard provides complete visibility into the pipeline's operation. Each alert processing stage updates in real-time, showing the LLM's analysis process. Security teams can see exactly why certain decisions were made and track which alerts are being handled automatically versus which require manual intervention."

## LLM Integration Details (30 seconds)
"What sets our solution apart is the direct integration with Qwen3-8B using an OpenAI-compatible API. The LLM receives structured security data, analyzes it using sophisticated reasoning, and returns actionable decisions with detailed explanations. This creates a more intelligent security operations workflow with complete transparency."

## Reliability Features (30 seconds)
"We've also implemented robust error handling and fallback mechanisms. If the LLM becomes unavailable or returns errors, the pipeline continues to function with backup decision logic. This ensures critical security operations are never interrupted, even during model outages or API issues."

## Conclusion (30 seconds)
"By combining structured security data processing with the advanced reasoning capabilities of large language models, we've created a system that enhances security operations through automation while maintaining human oversight. This approach scales to handle increasing alert volumes while providing high-quality, transparent decision making that security teams can trust."