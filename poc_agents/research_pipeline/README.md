# Research Pipeline POC

This POC demonstrates a multi-agent research and content generation pipeline that orchestrates 7 specialized agents to produce comprehensive research articles.

## Architecture

The pipeline consists of the following agents:

1. **Topic Research Agent** (Port 8010): Analyzes topics and creates research strategies
2. **Content Crawler Agent** (Port 8011): Searches and downloads relevant web content
3. **Information Extraction Agent** (Port 8012): Extracts key facts, statistics, and quotes
4. **Fact Verification Agent** (Port 8013): Cross-references and verifies extracted information
5. **Content Synthesis Agent** (Port 8014): Generates article structure and content
6. **Editor Agent** (Port 8015): Refines content for clarity and style
7. **Visualization Agent** (Port 8016): Creates data visualizations and diagrams

## Prerequisites

- Docker and Docker Compose installed
- LM Studio running on port 1234 with:
  - bartowski/meta-llama-3.1-8b-instruct
  - nomic-embed-text-v1.5-GGUF/nomic-embed-text-v1.5.f16.gguf
- PostgreSQL running on port 5432
- AgentVault Registry running

## Deployment

### Using Docker Compose (Recommended)

```bash
# From the research_pipeline directory
docker-compose up -d

# View logs
docker-compose logs -f
```

### Using the deployment script

```bash
# From the AgentVault root directory
chmod +x ./poc_agents/research_pipeline/deploy_research_pipeline.sh
./poc_agents/research_pipeline/deploy_research_pipeline.sh
```

## Testing the Pipeline

Test the complete pipeline:

```bash
agentvault_cli run --agent http://localhost:8010/agent-card.json --input "Impact of AI on Healthcare"
```

Test individual agents:

```bash
# Test Content Crawler
agentvault_cli run --agent http://localhost:8011/agent-card.json --input '{"search_queries": ["AI healthcare diagnosis"]}'

# Test Information Extraction
agentvault_cli run --agent http://localhost:8012/agent-card.json --input '{"raw_content": {"content": "AI is transforming medical diagnosis..."}}'
```

## Monitoring

Monitor individual agents:

```bash
docker logs -f topic-research-agent
docker logs -f content-crawler-agent
# etc...
```

## Troubleshooting

1. If agents can't connect to LM Studio, ensure it's running and accessible from Docker containers using `host.docker.internal`
2. If agents can't find agent cards, ensure the cards are properly mounted in the container
3. Check environment variables in the `.env` files match your setup

## Architecture Details

The pipeline uses:
- AgentVault A2A protocol for communication
- Server-Sent Events (SSE) for real-time updates
- PostgreSQL for persistent storage
- JSON artifacts for data exchange between agents

Each agent follows the same base structure:
- FastAPI server with A2A endpoints
- In-memory task store for state management
- Background task processing
- Proper error handling and logging
