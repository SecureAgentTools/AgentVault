#!/usr/bin/env python3
"""
Wrapper script to run the research pipeline with proper A2A format.
"""
import asyncio
import sys
import json
import argparse
from agentvault import AgentVaultClient
from agentvault.models.a2a_protocol import Message, TextPart

async def run_research_pipeline(topic: str, depth: str = "comprehensive", focus_areas: list = None):
    """Run the research pipeline with the given parameters."""
    client = AgentVaultClient()
    
    # Prepare input data
    input_data = {
        "topic": topic,
        "depth": depth,
        "focus_areas": focus_areas or ["emissions", "predictions", "solutions"]
    }
    
    # Create message with proper format
    message = Message(
        role="user",
        parts=[TextPart(content=json.dumps(input_data))]
    )
    
    try:
        # Send task to topic research agent
        task_id = await client.send_task(
            agent_url="http://localhost:8010/a2a",
            message=message
        )
        
        print(f"Started task: {task_id}")
        
        # Subscribe to events
        async for event in client.subscribe_events(
            agent_url="http://localhost:8010/a2a",
            task_id=task_id
        ):
            print(f"Event: {event.event}")
            
            if event.event == "status":
                print(f"  Status: {event.data.get('state')}")
                if event.data.get('state') in ['COMPLETED', 'FAILED', 'CANCELED']:
                    break
                    
            elif event.event == "message":
                print(f"  Message: {event.data}")
                
            elif event.event == "artifact":
                print(f"  Artifact: {event.data}")
                
            elif event.event == "error":
                print(f"  Error: {event.data}")
                break
                
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

def main():
    parser = argparse.ArgumentParser(description='Run the research pipeline')
    parser.add_argument('--topic', type=str, required=True, help='Research topic')
    parser.add_argument('--depth', type=str, default='comprehensive', help='Research depth')
    parser.add_argument('--focus-areas', nargs='+', help='Focus areas for research')
    
    args = parser.parse_args()
    
    return asyncio.run(run_research_pipeline(
        topic=args.topic,
        depth=args.depth,
        focus_areas=args.focus_areas
    ))

if __name__ == "__main__":
    sys.exit(main())
