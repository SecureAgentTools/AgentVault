#!/bin/bash

# Research Pipeline Deployment Script
# This script builds and deploys all agents in the research pipeline

echo "Deploying Research Pipeline Agents..."

# Stop and remove all existing research pipeline containers
echo "Cleaning up existing containers..."
docker stop topic-research-agent content-crawler-agent information-extraction-agent fact-verification-agent content-synthesis-agent editor-agent visualization-agent 2>/dev/null
docker rm topic-research-agent content-crawler-agent information-extraction-agent fact-verification-agent content-synthesis-agent editor-agent visualization-agent 2>/dev/null

# Remove existing images
echo "Removing existing images..."
docker rmi topic-research-agent:latest content-crawler-agent:latest information-extraction-agent:latest fact-verification-agent:latest content-synthesis-agent:latest editor-agent:latest visualization-agent:latest 2>/dev/null

# Build and deploy Topic Research Agent
echo "Building and deploying Topic Research Agent..."
docker build --no-cache -t topic-research-agent -f ./poc_agents/research_pipeline/dockerfiles/Dockerfile.topic-research .
docker run -d -p 8010:8010 --name topic-research-agent --env-file ./poc_agents/research_pipeline/envs/topic-research.env topic-research-agent:latest

# Build and deploy Content Crawler Agent
echo "Building and deploying Content Crawler Agent..."
docker build --no-cache -t content-crawler-agent -f ./poc_agents/research_pipeline/dockerfiles/Dockerfile.content-crawler .
docker run -d -p 8011:8011 --name content-crawler-agent --env-file ./poc_agents/research_pipeline/envs/content-crawler.env content-crawler-agent:latest

# Build and deploy Information Extraction Agent
echo "Building and deploying Information Extraction Agent..."
docker build --no-cache -t information-extraction-agent -f ./poc_agents/research_pipeline/dockerfiles/Dockerfile.information-extraction .
docker run -d -p 8012:8012 --name information-extraction-agent --env-file ./poc_agents/research_pipeline/envs/information-extraction.env information-extraction-agent:latest

# Build and deploy Fact Verification Agent
echo "Building and deploying Fact Verification Agent..."
docker build --no-cache -t fact-verification-agent -f ./poc_agents/research_pipeline/dockerfiles/Dockerfile.fact-verification .
docker run -d -p 8013:8013 --name fact-verification-agent --env-file ./poc_agents/research_pipeline/envs/fact-verification.env fact-verification-agent:latest

# Build and deploy Content Synthesis Agent
echo "Building and deploying Content Synthesis Agent..."
docker build --no-cache -t content-synthesis-agent -f ./poc_agents/research_pipeline/dockerfiles/Dockerfile.content-synthesis .
docker run -d -p 8014:8014 --name content-synthesis-agent --env-file ./poc_agents/research_pipeline/envs/content-synthesis.env content-synthesis-agent:latest

# Build and deploy Editor Agent
echo "Building and deploying Editor Agent..."
docker build --no-cache -t editor-agent -f ./poc_agents/research_pipeline/dockerfiles/Dockerfile.editor .
docker run -d -p 8015:8015 --name editor-agent --env-file ./poc_agents/research_pipeline/envs/editor.env editor-agent:latest

# Build and deploy Visualization Agent
echo "Building and deploying Visualization Agent..."
docker build --no-cache -t visualization-agent -f ./poc_agents/research_pipeline/dockerfiles/Dockerfile.visualization .
docker run -d -p 8016:8016 --name visualization-agent --env-file ./poc_agents/research_pipeline/envs/visualization.env visualization-agent:latest

# Wait for all agents to start
echo "Waiting for agents to start..."
sleep 10

# Show running containers
echo "Running Research Pipeline Agents:"
docker ps | grep -E "topic-research|content-crawler|information-extraction|fact-verification|content-synthesis|editor|visualization"

# Test the pipeline with a simple query
echo "Testing the pipeline..."
echo "You can test with: agentvault_cli run --agent http://localhost:8010/agent-card.json --input \"Impact of AI on Healthcare\""

# Monitor logs
echo "To monitor logs, use:"
echo "docker logs -f topic-research-agent"
echo "docker logs -f content-crawler-agent"
echo "docker logs -f information-extraction-agent"
echo "docker logs -f fact-verification-agent"
echo "docker logs -f content-synthesis-agent"
echo "docker logs -f editor-agent"
echo "docker logs -f visualization-agent"
