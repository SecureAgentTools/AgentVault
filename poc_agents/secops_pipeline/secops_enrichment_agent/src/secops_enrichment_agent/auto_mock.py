"""
Auto-mock enrichment data generator for dashboard development.
This will automatically generate mock enrichment data when the agent starts.
"""

import logging
import json
import redis
import asyncio
import random
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_mock_enrichment(execution_id):
    """Generate detailed mock enrichment data for an execution ID"""
    # Create more realistic indicators with varying types and verdicts
    indicators = [
        {
            "indicator": "192.168.1.1",
            "type": "IP",
            "verdict": "Clean",
            "details": {"source": "tip_virustotal", "reputation": "clean"}
        },
        {
            "indicator": f"malicious-domain-{random.randint(1, 100)}.com",
            "type": "Domain",
            "verdict": "Malicious",
            "details": {"source": "tip_abuseipdb", "reputation": "malicious"}
        },
        {
            "indicator": f"{random.randint(10**31, 10**32):x}",
            "type": "Hash",
            "verdict": "Suspicious",
            "details": {"source": "tip_virustotal", "reputation": "suspicious"}
        },
        {
            "indicator": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}",
            "type": "IP",
            "verdict": "Unknown",
            "details": {"source": "internal_network", "reputation": "unknown"}
        },
        {
            "indicator": f"user{random.randint(100,999)}@example.com",
            "type": "Email",
            "verdict": "Suspicious",
            "details": {"source": "tip_abuseipdb", "reputation": "suspicious"}
        }
    ]
    
    # Randomly select 3-5 indicators for variety
    selected_indicators = random.sample(indicators, min(len(indicators), random.randint(3, 5)))
    
    enrichment_event = {
        "event_type": "enrichment_results",
        "project_id": execution_id,
        "results": selected_indicators,
        "timestamp": datetime.now().isoformat()
    }
    
    return enrichment_event

async def auto_generate_enrichment_data():
    """
    Auto-generate mock enrichment data for all executions.
    This runs periodically to ensure enrichment data is available.
    """
    try:
        # Wait a bit to ensure Redis is fully started
        await asyncio.sleep(5)
        
        logger.info("Starting auto-generation of mock enrichment data...")
        
        # Connect to Redis with better error handling
        redis_client = None
        try:
            # Try to connect with more specific host address
            logger.info("Connecting to Redis at secops-redis:6379")
            redis_client = redis.Redis(host='secops-redis', port=6379, decode_responses=True)
            ping_result = redis_client.ping()
            logger.info(f"Redis ping result: {ping_result}")
        except Exception as redis_err:
            # Try using localhost as fallback
            logger.warning(f"Failed to connect to Redis at secops-redis:6379: {redis_err}, trying localhost")
            try:
                redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
                ping_result = redis_client.ping()
                logger.info(f"Redis ping result with localhost: {ping_result}")
            except Exception as local_err:
                logger.error(f"Failed to connect to Redis at localhost:6379: {local_err}")
                redis_client = None

        # Define default execution IDs to use if we can't get them from Redis
        default_ids = [
            "secops-default1",
            "secops-default2",
            "secops-default3",
            "secops-default4",
            "secops-default5"
        ]
        
        # Get execution IDs from Redis if connected
        execution_ids = default_ids
        if redis_client:
            try:
                logger.info("Searching for execution keys in Redis")
                # First try to get all keys
                execution_keys = redis_client.keys("*")
                logger.info(f"Found {len(execution_keys)} Redis keys")
                
                # Try different patterns to find executions
                possible_execution_keys = [
                    k for k in execution_keys 
                    if (isinstance(k, str) and (k.startswith('execution:') or k.startswith('secops-') or 'project' in k))
                ]
                
                if possible_execution_keys:
                    logger.info(f"Found {len(possible_execution_keys)} possible execution keys")
                    # Extract IDs from keys
                    extracted_ids = []
                    for key in possible_execution_keys:
                        if ':' in key:
                            extracted_ids.append(key.split(":")[-1])
                        else:
                            extracted_ids.append(key)
                    
                    if extracted_ids:
                        logger.info(f"Extracted {len(extracted_ids)} execution IDs from Redis")
                        # Combine with default IDs
                        execution_ids = list(set(extracted_ids + default_ids))
                    else:
                        logger.info("Couldn't extract execution IDs, using defaults")
                else:
                    logger.info("No execution keys found, using default IDs")
            except Exception as e:
                logger.warning(f"Error getting execution IDs from Redis: {e}")
                # Use default IDs if there's an error
        else:
            logger.info("Redis not available, using default execution IDs")
        
        logger.info(f"Processing {len(execution_ids)} execution IDs: {execution_ids}")
        
        # Generate and store enrichment data for each execution
        for execution_id in execution_ids:
            try:
                logger.info(f"Generating mock enrichment data for {execution_id}")
                enrichment_event = generate_mock_enrichment(execution_id)
                
                if redis_client:
                    # Store in Redis with the correct key format
                    redis_key = f"enrichment:results:{execution_id}"
                    redis_client.set(redis_key, json.dumps(enrichment_event), ex=3600)
                    logger.info(f"Stored enrichment data in Redis with key '{redis_key}'")
                    
                    # Also publish to the Redis channel for real-time updates
                    try:
                        redis_client.publish('secops_events', json.dumps(enrichment_event))
                        logger.info(f"Published enrichment event to Redis channel for {execution_id}")
                    except Exception as pub_err:
                        logger.warning(f"Failed to publish enrichment event: {pub_err}")
                else:
                    logger.warning(f"Redis unavailable - mock data for {execution_id} created but not stored")
                
                # Create additional mock data for fixed execution IDs to ensure dashboard works
                if execution_id == "secops-default1":
                    for fixed_id in ["secops-20250509193115-d38c34", "recent-execution1", "recent-execution2"]:
                        logger.info(f"Creating additional mock data for {fixed_id}")
                        extra_event = generate_mock_enrichment(fixed_id)
                        if redis_client:
                            redis_key = f"enrichment:results:{fixed_id}"
                            redis_client.set(redis_key, json.dumps(extra_event), ex=3600)
                            redis_client.publish('secops_events', json.dumps(extra_event))
                
                # Small delay between operations
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to generate enrichment data for {execution_id}: {e}")
        
        # Close Redis connection
        if redis_client:
            redis_client.close()
            
        logger.info("Auto-generation of mock enrichment data completed successfully")
        
        # Schedule to run again after 30 seconds
        asyncio.create_task(periodic_enrichment_generation())
        
    except Exception as e:
        logger.exception(f"Error in auto_generate_enrichment_data: {e}")
        # Still try to reschedule even after error
        asyncio.create_task(periodic_enrichment_generation())

async def periodic_enrichment_generation():
    """Run enrichment generation periodically"""
    await asyncio.sleep(30)  # Wait 30 seconds
    await auto_generate_enrichment_data()

def start_auto_generation():
    """Start the auto-generation process"""
    logger.info("Starting automatic mock enrichment data generation")
    asyncio.create_task(auto_generate_enrichment_data())

# Create a direct endpoint function to generate mock data for a specific execution ID
async def generate_mock_data_for_id(execution_id):
    """Generate mock data for a specific execution ID"""
    logger.info(f"Direct request to generate mock data for {execution_id}")
    
    try:
        # Generate enrichment data
        enrichment_event = generate_mock_enrichment(execution_id)
        
        # Connect to Redis
        try:
            redis_client = redis.Redis(host='secops-redis', port=6379, decode_responses=True)
            
            # Store in Redis
            redis_key = f"enrichment:results:{execution_id}"
            redis_client.set(redis_key, json.dumps(enrichment_event), ex=3600)
            
            # Publish to Redis channel
            redis_client.publish('secops_events', json.dumps(enrichment_event))
            
            redis_client.close()
            logger.info(f"Successfully generated mock data for {execution_id}")
            return True
        except Exception as redis_err:
            logger.error(f"Redis error while generating mock data: {redis_err}")
            return False
    except Exception as e:
        logger.exception(f"Error generating mock data for {execution_id}: {e}")
        return False
