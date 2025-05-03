# Research Pipeline Orchestrator Solution

## Problem Summary

The research pipeline orchestrator was failing to discover agent cards from the registry with 404 errors. We've implemented multiple fixes and workarounds to get the pipeline working.

## Solution Approaches

We've implemented three approaches to fix the issue:

### 1. Direct Agent Card Loading (Recommended)

The most reliable solution is to load agent cards directly from local files instead of querying the registry API. This bypasses any issues with the registry API or database.

**How to use:**
```bash
python direct_load_pipeline.py
```

This approach:
- Loads agent cards directly from the `agent_cards/` directory structure
- Handles the task polling/streaming logic correctly
- Properly manages error cases and missing attributes

### 2. Registry API Fix

We attempted to fix the registry API by:
- Adding better URL decoding for path parameters containing slashes
- Improving JSONB query handling in the database
- Adding an alternative query parameter endpoint

These fixes might work in some cases, but the direct loading approach is more reliable.

### 3. Database Diagnosis

We created scripts to diagnose database issues:
- `diagnose_db.py` - For direct database connections using SQLAlchemy/asyncpg
- `diagnose_db_docker.py` - For connecting to the database via Docker commands

## Script Descriptions

1. **`direct_load_pipeline.py`** (Recommended):
   - Complete standalone solution that loads agent cards directly from files
   - Fixed to handle the 'Task object has no attribute message' error
   - Implements fallback polling logic if streaming API isn't available

2. **`fix_and_run.py`**:
   - Diagnostic script that checks issues and runs the best available solution
   - Try this if you're not sure which approach to use

3. **`diagnose_db_docker.py`**:
   - Database diagnostic script using Docker commands
   - Use this if you need to verify database structure and content

## Root Cause Analysis

The core issues were:

1. **Path parameter handling** - The registry API wasn't correctly handling URL-encoded slashes in the Human Readable IDs (HRIs).

2. **JSONB query efficiency** - The queries used to extract values from the JSONB `card_data` column in PostgreSQL were inefficient.

3. **Client interface mismatch** - The client methods for streaming events didn't match what the orchestrator expected (`receive_events` vs possibly `subscribe_to_events`).

4. **Missing attribute error** - The `Task` object returned from the API doesn't have a `message` attribute that the code was trying to access.

## Next Steps

1. Use the `direct_load_pipeline.py` script as your primary solution.

2. If you need to diagnose database issues, use `diagnose_db_docker.py`.

3. If you want to fix the registry itself, apply our patches to:
   - `agentvault_registry/src/agentvault_registry/routers/agent_cards.py`
   - `agentvault_registry/src/agentvault_registry/crud/agent_card.py`

## Additional Diagnostic Tools

We've created additional tools to help diagnose service connectivity issues:

1. **`check_agent_services.py`**:
   - Checks if all agent services are running and responding
   - Attempts to send test messages to verify API functionality
   - Provides detailed diagnostics for each agent service

2. **`check_docker_containers.py`**:
   - Verifies which Docker containers are running
   - Identifies missing containers that should be started
   - Can start missing containers with the `--start` flag

3. **`diagnose_db_docker.py`**:
   - Safely connects to the PostgreSQL database via Docker commands
   - Checks for agent card data in the database
   - Examines database indexes and schema

## Latest Fixes

We've identified and fixed two additional issues with the orchestrator:

1. **URL Type Mismatch**:
   - The `agent_card.url` property is a Pydantic `AnyUrl` type but `httpx` expects a `str` or `httpx.URL`
   - Error: `Invalid type for url. Expected str or httpx.URL, got <class 'pydantic.networks.AnyUrl'>`
   - Fixed by converting all `agent_card.url` values to strings before passing to `httpx`

2. **HTTP Method Incompatibility**:
   - The agent services only accept POST requests, not HEAD requests
   - Error: HTTP 405 Method Not Allowed when trying to check service availability with HEAD
   - Fixed by using JSON-RPC formatted POST requests for service health checks

3. **Raw Content Dependency**:
   - Identified chain dependency between agents: information-extraction expects 'raw_content' from content-crawler
   - Error: `Missing 'raw_content' list in input content` when trying to run information-extraction task
   - Need to ensure proper data flow between agents
