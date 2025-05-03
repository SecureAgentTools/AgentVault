#!/usr/bin/env python
"""
Database diagnostic script specifically for connecting directly to the Docker container.
"""

import asyncio
import logging
import sys
import subprocess
import json
from typing import List, Dict, Any, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database parameters
DB_HOST = "localhost"  # If connecting from host to Docker container
DB_PORT = 5432
DB_NAME = "agentvault_dev"
DB_USER = "postgres"
DB_PASSWORD = "postgres"  # Default password, can be overridden

# Docker container name
DOCKER_CONTAINER = "mypg"

# Agent HRIs to check
AGENT_HRIS = [
    "local-poc/topic-research",
    "local-poc/content-crawler",
    "local-poc/information-extraction",
    "local-poc/fact-verification",
    "local-poc/content-synthesis",
    "local-poc/editor",
    "local-poc/visualization"
]

def run_docker_command(command: str) -> str:
    """Run a command in the Docker container and return the output."""
    try:
        logger.info(f"Running command in Docker container: {command}")
        result = subprocess.run(
            ["docker", "exec", DOCKER_CONTAINER, "sh", "-c", command],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Docker command failed: {e.stderr}")
        raise

def check_docker_container():
    """Check if the Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={DOCKER_CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        if DOCKER_CONTAINER in result.stdout:
            logger.info(f"✅ Docker container '{DOCKER_CONTAINER}' is running")
            return True
        else:
            logger.error(f"❌ Docker container '{DOCKER_CONTAINER}' is not running")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to check Docker container: {e}")
        return False

def check_postgres_in_docker():
    """Check if PostgreSQL is running in the Docker container."""
    try:
        output = run_docker_command("ps -ef | grep postgres")
        if "postgres" in output:
            logger.info("✅ PostgreSQL is running in the Docker container")
            return True
        else:
            logger.error("❌ PostgreSQL is not running in the Docker container")
            return False
    except Exception as e:
        logger.error(f"Failed to check PostgreSQL status: {e}")
        return False

def check_database_exists():
    """Check if the database exists in the Docker container."""
    try:
        output = run_docker_command(f"psql -U {DB_USER} -l")
        if DB_NAME in output:
            logger.info(f"✅ Database '{DB_NAME}' exists")
            return True
        else:
            logger.error(f"❌ Database '{DB_NAME}' does not exist")
            return False
    except Exception as e:
        logger.error(f"Failed to check database existence: {e}")
        return False

def check_agent_cards_table():
    """Check if the agent_cards table exists and has data."""
    try:
        output = run_docker_command(f"psql -U {DB_USER} -d {DB_NAME} -c '\\dt agent_cards'")
        if "agent_cards" in output:
            logger.info("✅ Table 'agent_cards' exists")
            
            # Check row count
            count_output = run_docker_command(f"psql -U {DB_USER} -d {DB_NAME} -c 'SELECT COUNT(*) FROM agent_cards'")
            try:
                # Extract count from output (typical format: " count \n-------\n 10\n(1 row)")
                count_line = [line.strip() for line in count_output.splitlines() if line.strip() and line.strip().isdigit()]
                if count_line:
                    count = int(count_line[0])
                    logger.info(f"✅ Table 'agent_cards' has {count} rows")
                    return True
                else:
                    logger.warning("⚠️ Could not determine row count for 'agent_cards' table")
                    return True
            except Exception as e:
                logger.warning(f"⚠️ Error parsing row count: {e}")
                return True
        else:
            logger.error("❌ Table 'agent_cards' does not exist")
            return False
    except Exception as e:
        logger.error(f"Failed to check agent_cards table: {e}")
        return False

def check_agent_hris_in_db():
    """Check if specified agent HRIs exist in the database."""
    success_count = 0
    
    for hri in AGENT_HRIS:
        try:
            # We need to escape single quotes for SQL
            escaped_hri = hri.replace("'", "''")
            query = f"SELECT id, name FROM agent_cards WHERE card_data->>'humanReadableId' = '{escaped_hri}'"
            output = run_docker_command(f"psql -U {DB_USER} -d {DB_NAME} -c \"{query}\"")
            
            if "(0 rows)" in output:
                logger.warning(f"⚠️ Agent card for '{hri}' not found")
                
                # Try case-insensitive search
                case_query = f"SELECT id, name, card_data->>'humanReadableId' FROM agent_cards WHERE LOWER(card_data->>'humanReadableId') = LOWER('{escaped_hri}')"
                case_output = run_docker_command(f"psql -U {DB_USER} -d {DB_NAME} -c \"{case_query}\"")
                
                if "(0 rows)" not in case_output:
                    # Extract the actual HRI from the result
                    lines = case_output.splitlines()
                    # Find line with HRI data (should be after headers)
                    for line in lines[2:]:  # Skip header lines
                        if line.strip() and "|" in line:
                            # Split by | and get the last column (HRI)
                            columns = [col.strip() for col in line.split("|")]
                            if len(columns) >= 3:
                                actual_hri = columns[2]
                                logger.info(f"✅ Found case-insensitive match for '{hri}': '{actual_hri}'")
                                success_count += 1
                                break
                            else:
                                logger.warning(f"⚠️ Unexpected format in case-insensitive result: {line}")
                else:
                    logger.error(f"❌ No match found for '{hri}' (case-insensitive)")
            else:
                logger.info(f"✅ Found agent card for '{hri}'")
                success_count += 1
        except Exception as e:
            logger.error(f"Error checking HRI '{hri}': {e}")
    
    logger.info(f"Found {success_count}/{len(AGENT_HRIS)} agent cards in database")
    return success_count == len(AGENT_HRIS)

def check_database_indexes():
    """Check if appropriate indexes exist for the agent_cards table."""
    try:
        output = run_docker_command(f"psql -U {DB_USER} -d {DB_NAME} -c '\\di'")
        logger.info("Database indexes:")
        logger.info(output)
        
        # Check specific indexes for JSONB
        jsonb_output = run_docker_command(f"psql -U {DB_USER} -d {DB_NAME} -c \"SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'agent_cards' AND indexdef LIKE '%card_data%'\"")
        
        if "(0 rows)" in jsonb_output:
            logger.warning("⚠️ No JSONB indexes found for card_data column")
            logger.info("Consider adding an index like:")
            logger.info("CREATE INDEX idx_agent_cards_hri ON agent_cards USING gin ((card_data->>'humanReadableId') gin_trgm_ops);")
        else:
            logger.info("✅ JSONB indexes found:")
            logger.info(jsonb_output)
        
        return True
    except Exception as e:
        logger.error(f"Failed to check database indexes: {e}")
        return False

def main():
    """Run all database diagnostics."""
    logger.info("Starting database diagnostics using Docker container commands")
    
    # Check if Docker container is running
    if not check_docker_container():
        logger.error("Docker container check failed, cannot proceed with diagnostics")
        return
    
    # Check if PostgreSQL is running
    if not check_postgres_in_docker():
        logger.error("PostgreSQL check failed, cannot proceed with database diagnostics")
        return
    
    # Check if database exists
    if not check_database_exists():
        logger.error("Database does not exist, cannot proceed with table diagnostics")
        return
    
    # Check if agent_cards table exists
    if not check_agent_cards_table():
        logger.error("agent_cards table does not exist, cannot proceed with data diagnostics")
        return
    
    # Check if agent HRIs exist in database
    hris_exist = check_agent_hris_in_db()
    
    # Check database indexes
    indexes_ok = check_database_indexes()
    
    # Print summary
    logger.info("\n=== Database Diagnosis Summary ===")
    logger.info(f"Docker Container: ✅")
    logger.info(f"PostgreSQL Running: ✅")
    logger.info(f"Database Exists: ✅")
    logger.info(f"agent_cards Table Exists: ✅")
    logger.info(f"All Agent HRIs Found: {'✅' if hris_exist else '❌'}")
    logger.info(f"Database Indexes Checked: {'✅' if indexes_ok else '⚠️'}")
    
    if not hris_exist:
        logger.info("\nRecommendations:")
        logger.info("1. Verify the exact HRIs in the database and make sure they match what the orchestrator expects")
        logger.info("2. Consider using case-insensitive comparison for HRIs")
        logger.info("3. Use the direct loading approach from files since it's already working")
    
    if not indexes_ok:
        logger.info("4. Consider adding proper indexes for the JSONB card_data column")

if __name__ == "__main__":
    main()
