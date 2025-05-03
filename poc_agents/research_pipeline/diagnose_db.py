#!/usr/bin/env python
"""
Database diagnostic script to directly diagnose PostgreSQL connectivity issues
and check agent card data in the database.
"""

import asyncio
import logging
import sys
from typing import List, Dict, Any, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import required libraries
try:
    import asyncpg
    import sqlalchemy
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
except ImportError as e:
    logger.error(f"Failed to import required libraries: {e}")
    logger.info("Try installing the missing libraries with: pip install asyncpg sqlalchemy")
    sys.exit(1)

# Database connection parameters
DB_URL = "postgresql+asyncpg://postgres:Password1337%3F@localhost:5432/agentvault_dev"

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

async def test_raw_connection():
    """Test direct connection to the database using asyncpg."""
    logger.info("Testing direct asyncpg connection...")
    
    try:
        # Extract connection parameters from URL
        url_parts = DB_URL.replace("postgresql+asyncpg://", "").split("@")
        
        auth_parts = url_parts[0].split(":")
        location_parts = url_parts[1].split("/")
        
        user = auth_parts[0]
        password = auth_parts[1]
        host_port = location_parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 5432
        database = location_parts[1]
        
        logger.info(f"Connecting to PostgreSQL at {host}:{port}/{database} as {user}...")
        
        # Connect directly with asyncpg
        conn = await asyncpg.connect(
            user=user,
            password=password,
            database=database,
            host=host,
            port=port
        )
        
        try:
            # Test simple query
            version = await conn.fetchval('SELECT version()')
            logger.info(f"Successfully connected to PostgreSQL: {version}")
            
            # Check for agent_cards table
            table_check = await conn.fetch("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'agent_cards'
                );
            """)
            
            if table_check and table_check[0]['exists']:
                logger.info("✅ agent_cards table exists in database")
                
                # Count records
                count = await conn.fetchval('SELECT COUNT(*) FROM agent_cards')
                logger.info(f"Total agent cards in database: {count}")
                
                # Check for our specific HRIs
                for hri in AGENT_HRIS:
                    # Try exact match first
                    exact_match = await conn.fetchval(
                        "SELECT COUNT(*) FROM agent_cards WHERE card_data->>'humanReadableId' = $1",
                        hri
                    )
                    
                    if exact_match and exact_match > 0:
                        logger.info(f"✅ Found {exact_match} exact matches for HRI '{hri}'")
                        
                        # Get sample data
                        row = await conn.fetchrow(
                            "SELECT id, name, card_data FROM agent_cards WHERE card_data->>'humanReadableId' = $1 LIMIT 1",
                            hri
                        )
                        
                        if row:
                            logger.info(f"  - ID: {row['id']}, Name: {row['name']}")
                    else:
                        logger.warning(f"❌ No exact matches found for HRI '{hri}'")
                        
                        # Try case-insensitive search
                        case_insensitive = await conn.fetchval(
                            "SELECT COUNT(*) FROM agent_cards WHERE LOWER(card_data->>'humanReadableId') = LOWER($1)",
                            hri
                        )
                        
                        if case_insensitive and case_insensitive > 0:
                            logger.info(f"✅ Found {case_insensitive} case-insensitive matches for HRI '{hri}'")
                            
                            # Get sample with correct casing
                            row = await conn.fetchrow(
                                "SELECT id, name, card_data->>'humanReadableId' AS actual_hri FROM agent_cards WHERE LOWER(card_data->>'humanReadableId') = LOWER($1) LIMIT 1",
                                hri
                            )
                            
                            if row:
                                logger.info(f"  - Actual HRI in database: '{row['actual_hri']}' (ID: {row['id']}, Name: {row['name']})")
                        else:
                            # Try partial match as last resort
                            parts = hri.split('/')
                            if len(parts) == 2:
                                partial_matches = await conn.fetch(
                                    "SELECT id, name, card_data->>'humanReadableId' AS hri FROM agent_cards WHERE card_data->>'humanReadableId' LIKE $1",
                                    f"%{parts[1]}%"
                                )
                                
                                if partial_matches:
                                    logger.info(f"Found {len(partial_matches)} partial matches for '{parts[1]}':")
                                    for match in partial_matches:
                                        logger.info(f"  - {match['name']} (HRI: {match['hri']})")
            else:
                logger.error("❌ agent_cards table does not exist in database!")
        
        finally:
            # Close the connection
            await conn.close()
            logger.info("Database connection closed.")
            
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        return False
    
    return True

async def test_sqlalchemy_connection():
    """Test connection using SQLAlchemy."""
    logger.info("Testing SQLAlchemy connection...")
    
    try:
        # Create engine and session
        engine = create_async_engine(DB_URL)
        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            # Test simple query
            result = await session.execute("SELECT version()")
            version = result.scalar()
            logger.info(f"Successfully connected to PostgreSQL via SQLAlchemy: {version}")
            
            # Check agent_cards table
            try:
                result = await session.execute("SELECT COUNT(*) FROM agent_cards")
                count = result.scalar()
                logger.info(f"Total agent cards in database (SQLAlchemy): {count}")
                
                # Sample query for humanReadableIds
                result = await session.execute(
                    "SELECT card_data->>'humanReadableId' AS hri FROM agent_cards LIMIT 10"
                )
                sample_hris = result.scalars().all()
                
                if sample_hris:
                    logger.info("Sample HRIs in database:")
                    for hri in sample_hris:
                        logger.info(f"  - {hri}")
                
            except Exception as e:
                logger.error(f"Error querying agent_cards table: {e}")
        
    except Exception as e:
        logger.error(f"Failed to connect using SQLAlchemy: {e}", exc_info=True)
        return False
    
    return True

async def diagnose_database_indexes():
    """Check database indexes that might affect query performance."""
    logger.info("Checking database indexes...")
    
    try:
        # Connect directly with asyncpg
        url_parts = DB_URL.replace("postgresql+asyncpg://", "").split("@")
        auth_parts = url_parts[0].split(":")
        location_parts = url_parts[1].split("/")
        
        user = auth_parts[0]
        password = auth_parts[1]
        host = location_parts[0].split(":")[0]
        port = int(location_parts[0].split(":")[1]) if ":" in location_parts[0] else 5432
        database = location_parts[1]
        
        conn = await asyncpg.connect(
            user=user,
            password=password,
            database=database,
            host=host,
            port=port
        )
        
        try:
            # Check indexes on agent_cards table
            indexes = await conn.fetch("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'agent_cards'
                ORDER BY indexname
            """)
            
            if indexes:
                logger.info(f"Found {len(indexes)} indexes on agent_cards table:")
                has_json_index = False
                
                for idx in indexes:
                    logger.info(f"  - {idx['indexname']}: {idx['indexdef']}")
                    
                    # Check if we have a proper index for humanReadableId in JSONB
                    if "humanreadableid" in idx['indexdef'].lower() or "card_data" in idx['indexdef'] and "gin" in idx['indexdef'].lower():
                        has_json_index = True
                
                if not has_json_index:
                    logger.warning("⚠️ No specific index found for humanReadableId in card_data JSONB column!")
                    logger.info("Consider adding an index with: CREATE INDEX idx_agent_cards_hri ON agent_cards USING gin ((card_data->>'humanReadableId'))")
            else:
                logger.warning("⚠️ No indexes found on agent_cards table!")
            
            # Check the execution plan for our query
            logger.info("Analyzing query execution plan...")
            
            plan = await conn.fetch("""
                EXPLAIN ANALYZE
                SELECT * FROM agent_cards 
                WHERE card_data->>'humanReadableId' = 'local-poc/topic-research'
            """)
            
            if plan:
                logger.info("Query execution plan:")
                for row in plan:
                    logger.info(f"  {row['QUERY PLAN']}")
            
        finally:
            await conn.close()
    
    except Exception as e:
        logger.error(f"Failed to check database indexes: {e}", exc_info=True)

async def main():
    """Run all database diagnostic tests."""
    logger.info(f"Starting database diagnostics with connection URL: {DB_URL}")
    
    # Test raw connection
    raw_conn_success = await test_raw_connection()
    
    # Test SQLAlchemy connection
    sqlalchemy_conn_success = await test_sqlalchemy_connection()
    
    # If connections worked, check indexes
    if raw_conn_success or sqlalchemy_conn_success:
        await diagnose_database_indexes()
        
        # Print summary
        logger.info("\n=== Database Diagnosis Summary ===")
        logger.info(f"Raw Connection: {'✅ SUCCESS' if raw_conn_success else '❌ FAILED'}")
        logger.info(f"SQLAlchemy Connection: {'✅ SUCCESS' if sqlalchemy_conn_success else '❌ FAILED'}")
        
        if raw_conn_success:
            logger.info("\nRecommendations:")
            logger.info("1. Check if the specific HRIs are in the database with the exact expected format")
            logger.info("2. Verify the JSONB query syntax in the registry's CRUD function")
            logger.info("3. Consider adding a specific index for the humanReadableId field in the JSONB column")
    else:
        logger.error("❌ All connection attempts failed. Check database credentials and connectivity.")

if __name__ == "__main__":
    asyncio.run(main())
