# AgentVault Examples

This section provides practical examples demonstrating how to use AgentVault and its components to build various multi-agent systems and integrations.

## Core Concepts Examples

These examples illustrate specific features of the AgentVault client library (`agentvault`) and the server SDK (`agentvault-server-sdk`).

*   **[Basic A2A Server](./basic_a2a_server.md):** Shows the minimal setup for creating an A2A-compliant agent using FastAPI and the Server SDK. Demonstrates handling `tasks/send`, `get`, `cancel`, and `subscribe`.
*   **[Direct Library Usage](./library_usage_example.md):** Illustrates how to use the `AgentVaultClient` directly in Python to interact with an A2A agent, including task initiation and SSE event streaming.
*   **[OAuth2 Authenticated Agent](./oauth_agent_example.md):** Demonstrates building an agent server that requires OAuth2 Client Credentials flow for authentication, including a mock token endpoint and protecting the A2A endpoint.
*   **[Stateful Agent](./stateful_agent_example.md):** Shows how to build an agent that maintains state across multiple interactions within a single task lifecycle using the SDK's task store concepts.
*   **[Simple Communication Agents](./basic_agents.md):** Covers agents like the Task Logger, Registry Query (LLM Test Mode), and Simple Summary Agent, showcasing basic database interaction, LLM integration, and simple agent-to-agent calls.

## Integration Examples

*   **[LangChain Tool Integration](./langchain_integration.md):** Provides a template for wrapping an AgentVault A2A agent as a custom tool within the LangChain framework.

## End-to-End Pipeline POCs

These Proof-of-Concept (POC) pipelines demonstrate how multiple specialized agents can collaborate to solve more complex problems using AgentVault orchestration principles.

*   **[Research Pipeline](./poc_research.md):** A sophisticated pipeline orchestrating 7 agents (topic research, crawling, extraction, verification, synthesis, editing, visualization) to generate comprehensive research reports on a given topic. Demonstrates complex workflow, artifact passing, and local artifact storage. (Uses LangGraph for orchestration).
*   **[Support Ticket Pipeline](./poc_support.md):** Orchestrates 4 agents (ticket analysis, KB search, customer history, response suggestion) to process customer support tickets and suggest responses. Showcases integrating different data sources. (Uses LangGraph for orchestration).
*   **[Dynamics 365 Pipeline](./poc_dynamics.md):** A pipeline simulating integration with Dynamics 365 data. It involves fetching data, enrichment, health analysis, action recommendation, briefing generation, and task creation/notification execution. Demonstrates rule-based analysis, LLM usage, and executing actions based on insights. (Uses LangGraph for orchestration).
*   **[E-commerce Pipeline](./poc_ecommerce.md):** Orchestrates agents for user profiling, product catalog lookup, trend analysis, and recommendation generation to provide personalized e-commerce suggestions. (Uses LangGraph for orchestration).
*   **[ETL Pipeline](./poc_etl.md):** Demonstrates an Extract, Transform, Load workflow using multiple agents and a database for artifact storage between steps. (Uses LangGraph for orchestration).
*   **[MCP Test Pipeline](./poc_mcp_pipeline.md):** Showcases the Model Context Protocol (MCP) by using a proxy agent to interact with MCP-compliant tool servers (filesystem, code runner) for executing specific operations. (Uses LangGraph for orchestration).
