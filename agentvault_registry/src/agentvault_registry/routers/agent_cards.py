import logging
import uuid
import math
import datetime
import os
from typing import Optional, List, Dict, Any, Tuple, Annotated

from sqlalchemy import select, func, or_, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import cast, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload # Keep import for get_agent_card

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import ValidationError as PydanticValidationError # To catch validation errors

# Import local dependencies with absolute imports
from agentvault_registry import schemas, models, database, security
from agentvault_registry.crud import agent_card

# Import the AgentCard model from the core library for validation
try:
    from agentvault import AgentCard as AgentCardModel
    _agentvault_lib_available = True
except ImportError:
    AgentCardModel = None # type: ignore
    _agentvault_lib_available = False
    logging.warning("Could not import 'agentvault' library. Agent Card validation during CRUD operations will be skipped.")

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Helper Function to build response dict (Original Version - Assumes developer loaded) ---
def _build_agent_card_read_dict(db_card: models.AgentCard) -> dict:
    """Builds the dictionary for AgentCardRead response from the ORM model."""
    if not db_card:
        return {} # Should not happen if called correctly

    developer_verified = False # Default to False if not loaded
    # Original logic assumed relationship was loaded via selectinload
    if hasattr(db_card, 'developer') and db_card.developer:
        developer_verified = getattr(db_card.developer, 'is_verified', False)
        logger.debug(f"Developer relationship was loaded for Card {db_card.id}. Verified: {developer_verified}")
    else:
        logger.warning(f"Developer relationship not loaded for AgentCard {db_card.id} when building response.")

    return {
        "id": db_card.id,
        "developer_id": db_card.developer_id,
        "card_data": db_card.card_data,
        "name": db_card.name,
        "description": db_card.description,
        "is_active": db_card.is_active,
        "created_at": db_card.created_at,
        "updated_at": db_card.updated_at,
        "developer_is_verified": developer_verified,
    }
# --- End Helper ---


# --- POST /agent-cards ---
@router.post(
    "/",
    response_model=schemas.AgentCardRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new Agent Card",
    description="Submits a new Agent Card associated with the authenticated developer.",
    dependencies=[Depends(security.get_current_developer)] # Apply standard JWT auth here
)
async def submit_agent_card(
    card_in: schemas.AgentCardCreate,
    # Dependencies last
    db: AsyncSession = Depends(database.get_db),
    current_developer: models.Developer = Depends(security.get_current_developer),
) -> schemas.AgentCardRead:
    """
    Endpoint to submit a new Agent Card.
    Requires developer authentication via JWT Bearer token.
    Validates the provided `card_data` against the core AgentCard schema.
    """
    logger.info(f"Received request to create agent card from developer ID: {current_developer.id}")
    try:
        db_agent_card = await agent_card.create_agent_card(
            db=db, developer_id=current_developer.id, card_create=card_in
        )
        # Refresh to load the relationship for the response
        if db_agent_card:
             logger.info(f"Refreshing developer relationship for created card {db_agent_card.id}")
             await db.refresh(db_agent_card, attribute_names=['developer'])
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create agent card record.")


        response_dict = _build_agent_card_read_dict(db_agent_card)
        return schemas.AgentCardRead.model_validate(response_dict)
    except ValueError as e:
        logger.warning(f"Failed to create agent card due to validation/DB error: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to create agent card: {e}",
        )
    except Exception as e:
        logger.exception(f"Unexpected error creating agent card for developer {current_developer.id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the agent card.",
        )


# --- GET /agent-cards ---
@router.get(
    "/",
    response_model=schemas.AgentCardListResponse,
    summary="List Agent Cards",
    description="Retrieves a paginated list of active Agent Cards, optionally filtered by search query, tags, TEE status, or ownership.",
)
async def list_agent_cards(
    # Dependencies (non-default) first
    db: AsyncSession = Depends(database.get_db),
    current_developer: Optional[models.Developer] = Depends(security.get_current_developer_optional), # Correct dependency
    # Query parameters with defaults after dependencies
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(100, ge=1, le=250, description="Maximum number of records to return."),
    active_only: bool = Query(True, description="Filter for active agent cards only."),
    search: Optional[str] = Query(
        None,
        max_length=100,
        description="Search term to filter by name or description (case-insensitive, max 100 chars)."
    ),
    tags: Optional[List[str]] = Query(
        None,
        description="List of tags to filter by (agents must have ALL specified tags)."
    ),
    has_tee: Optional[bool] = Query(None, description="Filter for agents that have TEE details declared."),
    tee_type: Optional[str] = Query(None, max_length=50, description="Filter by the specific TEE type string (e.g., 'Intel SGX', max 50 chars)."),
    owned_only: bool = Query(False, description="If true, only return cards owned by the authenticated developer (requires authentication).")
):
    """
    Public endpoint to list and search for Agent Cards.
    Can optionally filter by owned cards if authenticated.
    Can filter by TEE presence and type.
    """
    developer_id_filter: Optional[int] = None
    if owned_only:
        if current_developer is None:
            logger.warning("Attempted to list owned cards without valid authentication.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to list owned agent cards."
            )
        developer_id_filter = current_developer.id
        logger.info(f"Listing agent cards for owner ID: {developer_id_filter}, skip={skip}, limit={limit}, active_only={active_only}, search='{search}', tags={tags}, has_tee={has_tee}, tee_type='{tee_type}'")
    else:
        logger.info(f"Listing public agent cards with skip={skip}, limit={limit}, active_only={active_only}, search='{search}', tags={tags}, has_tee={has_tee}, tee_type='{tee_type}'")

    try:
        # Call CRUD function (which now includes selectinload again)
        items, total_items = await agent_card.list_agent_cards(
            db=db, skip=skip, limit=limit, active_only=active_only, search=search, tags=tags,
            developer_id=developer_id_filter,
            has_tee=has_tee,
            tee_type=tee_type
        )

        # Construct pagination info
        current_page = (skip // limit) + 1 if limit > 0 else 1
        total_pages = math.ceil(total_items / limit) if limit > 0 else (1 if total_items > 0 else 0)

        pagination_info = schemas.PaginationInfo(
            total_items=total_items,
            limit=limit,
            offset=skip,
            total_pages=total_pages,
            current_page=current_page,
        )
        # Serialize items to summary schema
        summaries = [schemas.AgentCardSummary.model_validate(item) for item in items]
        return schemas.AgentCardListResponse(items=summaries, pagination=pagination_info)

    except Exception as e:
        logger.exception("Error listing agent cards")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving agent cards.",
        )


# --- GET /agent-cards/{card_id} ---
@router.get(
    "/{card_id}",
    response_model=schemas.AgentCardRead,
    summary="Get Agent Card by ID",
    description="Retrieves the details of a specific Agent Card by its UUID.",
)
async def get_agent_card(
    card_id: uuid.UUID,
    # Dependency after path param
    db: AsyncSession = Depends(database.get_db),
) -> schemas.AgentCardRead:
    """
    Public endpoint to retrieve a specific Agent Card by its UUID.
    """
    logger.info(f"Fetching agent card with ID: {card_id}")
    db_card = await agent_card.get_agent_card(db=db, card_id=card_id)
    if db_card is None:
        logger.warning(f"Agent card with ID {card_id} not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Card not found")

    response_dict = _build_agent_card_read_dict(db_card) # Helper handles potential missing dev
    return schemas.AgentCardRead.model_validate(response_dict)


# --- NEW: Alternative endpoint that uses query parameter instead of path parameter ---
@router.get(
    "/by-hri",
    response_model=schemas.AgentCardRead,
    summary="Get Agent Card by Human-Readable ID (Query Parameter)",
    description="Alternative endpoint to retrieve an agent card by HRI using a query parameter.",
    tags=["Agent Cards"]
)
async def get_agent_card_by_hri_query(
    hri: str = Query(..., description="The humanReadableId of the agent to retrieve"),
    db: AsyncSession = Depends(database.get_db),
) -> schemas.AgentCardRead:
    """
    Alternative endpoint to retrieve a specific Agent Card by its humanReadableId using a query parameter.
    This avoids potential issues with URL path parameters containing slashes.
    """
    logger.info(f"=== ENDPOINT CALLED: get_agent_card_by_hri_query with HRI: '{hri}' ===")
    
    # This HRI comes directly as a query parameter, so no URL decoding needed
    # But we'll log what we received for debugging
    logger.info(f"Received HRI query parameter: '{hri}'")
    
    # Try a direct database lookup to verify if the card exists
    try:
        # Use parameterized query for safety
        raw_query = text("SELECT COUNT(*) FROM agent_cards WHERE card_data->>'humanReadableId' = :hri")
        result = await db.execute(raw_query, {"hri": hri})
        count = result.scalar_one()
        logger.info(f"Direct DB check: Found {count} cards with humanReadableId '{hri}'")
        
        if count > 0:
            # Also show a sample of what's in the database
            sample_query = text("SELECT id, name, card_data->>'humanReadableId' AS hri FROM agent_cards LIMIT 3")
            sample_result = await db.execute(sample_query)
            sample_rows = sample_result.all()
            logger.info(f"Sample rows in database: {sample_rows}")
            
            # Try a direct retrieval since we know it exists
            direct_query = text("SELECT * FROM agent_cards WHERE card_data->>'humanReadableId' = :hri")
            direct_result = await db.execute(direct_query, {"hri": hri})
            row = direct_result.first()
            
            if row:
                # Use SQLAlchemy's get method to load as proper ORM object
                card_id = row[0]  # Assuming first column is id
                orm_query = select(models.AgentCard).options(selectinload(models.AgentCard.developer)).where(models.AgentCard.id == card_id)
                orm_result = await db.execute(orm_query)
                card = orm_result.scalar_one_or_none()
                
                if card:
                    response_dict = _build_agent_card_read_dict(card)
                    return schemas.AgentCardRead.model_validate(response_dict)
    except Exception as e:
        logger.warning(f"Error during direct DB check: {e}")
    
    # If direct approach didn't work, try the CRUD method  
    db_card = await agent_card.get_agent_card_by_human_readable_id(db=db, human_readable_id=hri)
    
    if db_card is None:
        logger.error(f"⚠️ Agent card with humanReadableId '{hri}' not found.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Agent Card with humanReadableId '{hri}' not found"
        )
    
    logger.info(f"✓ Successfully found agent card: {db_card.name} (ID: {db_card.id})")
    
    response_dict = _build_agent_card_read_dict(db_card) # Helper handles potential missing dev
    return schemas.AgentCardRead.model_validate(response_dict)


# --- PUT /agent-cards/{card_id} ---
@router.put(
    "/{card_id}",
    response_model=schemas.AgentCardRead,
    summary="Update an Agent Card",
    description="Updates an existing Agent Card. Requires ownership.",
    dependencies=[Depends(security.get_current_developer)]
)
async def update_agent_card(
    card_id: uuid.UUID,
    card_in: schemas.AgentCardUpdate,
    # Dependencies after path and body params
    db: AsyncSession = Depends(database.get_db),
    current_developer: models.Developer = Depends(security.get_current_developer),
) -> schemas.AgentCardRead:
    """
    Endpoint to update an Agent Card.
    Requires developer authentication (JWT) and ownership of the card.
    Validates `card_data` if provided.
    """
    logger.info(f"Received request to update agent card {card_id} from developer ID: {current_developer.id}")
    # Fetch card WITH developer info for ownership check
    db_card = await agent_card.get_agent_card(db=db, card_id=card_id)
    if db_card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Card not found")

    # Check ownership
    if db_card.developer_id != current_developer.id:
        logger.warning(f"Developer {current_developer.id} attempted to update agent card {card_id} owned by {db_card.developer_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this agent card")

    try:
        # Pass the fetched db_card to the update function
        updated_card = await agent_card.update_agent_card(db=db, db_card=db_card, card_update=card_in)

        # Refresh developer relationship AFTER update
        if updated_card:
             logger.info(f"Refreshing developer relationship for updated card {updated_card.id}")
             await db.refresh(updated_card, attribute_names=['developer'])
        else:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update agent card record.")


        response_dict = _build_agent_card_read_dict(updated_card)
        return schemas.AgentCardRead.model_validate(response_dict)
    except ValueError as e:
        logger.warning(f"Failed to update agent card {card_id} due to validation/DB error: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to update agent card: {e}",
        )
    except Exception as e:
        logger.exception(f"Unexpected error updating agent card {card_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the agent card.",
        )


# --- DELETE /agent-cards/{card_id} ---
@router.delete(
    "/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an Agent Card",
    description="Marks an Agent Card as inactive (soft delete). Requires ownership.",
    dependencies=[Depends(security.get_current_developer)]
)
async def delete_agent_card(
    card_id: uuid.UUID,
    # Dependencies after path param
    db: AsyncSession = Depends(database.get_db),
    current_developer: models.Developer = Depends(security.get_current_developer),
):
    """
    Endpoint to soft-delete (deactivate) an Agent Card.
    Requires developer authentication (JWT) and ownership.
    Returns 204 No Content on success.
    """
    logger.info(f"Received request to deactivate agent card {card_id} from developer ID: {current_developer.id}")
    # Fetch card WITH developer info for ownership check
    db_card = await agent_card.get_agent_card(db=db, card_id=card_id)
    if db_card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Card not found")

    # Check ownership
    if db_card.developer_id != current_developer.id:
        logger.warning(f"Developer {current_developer.id} attempted to delete agent card {card_id} owned by {db_card.developer_id}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this agent card")

    # Call the delete (deactivate) function
    success = await agent_card.delete_agent_card(db=db, card_id=card_id)

    # Check result and raise appropriate error if deletion failed unexpectedly
    if not success:
        # Re-check the card status to see if it failed because it wasn't found
        # or due to a DB error during the update.
        check_card = await agent_card.get_agent_card(db=db, card_id=card_id)
        if not check_card:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Card not found during deletion process.")
        elif check_card.is_active: # Still active? Then the update failed.
             logger.error(f"Failed to deactivate agent card {card_id} due to a database error during update.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to deactivate agent card due to internal error.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- GET /agent-cards/id/{human_readable_id} ---
@router.get(
    "/id/{human_readable_id:path}", # Use path parameter to allow slashes
    response_model=schemas.AgentCardRead,
    summary="Get Agent Card by Human-Readable ID",
    description="Retrieves the details of a specific Agent Card by its humanReadableId (e.g., 'org/agent').",
    tags=["Agent Cards"] # Keep in the same group
)
async def get_agent_card_by_human_id(
    human_readable_id: str,
    # Dependency after path param
    db: AsyncSession = Depends(database.get_db),
) -> schemas.AgentCardRead:
    """
    Public endpoint to retrieve a specific Agent Card by its humanReadableId.
    """
    logger.info(f"=== ENDPOINT CALLED: get_agent_card_by_human_id with HRI: '{human_readable_id}' ===")
    
    # URL decoding for human_readable_id which might be sent URL-encoded
    import urllib.parse
    # Decode the human_readable_id in case it was URL-encoded by the client
    try:
        # Try to decode in case it was sent encoded with %2F for /, etc.
        decoded_id = urllib.parse.unquote(human_readable_id)
        logger.info(f"URL-decoded HRI: '{decoded_id}' (original input: '{human_readable_id}')")
    except Exception as e:
        logger.warning(f"Error decoding humanReadableId '{human_readable_id}': {e}, proceeding with original value")
        decoded_id = human_readable_id
    
    # Try a direct database lookup to verify if the card exists
    from sqlalchemy import text
    try:
        raw_query = text("SELECT COUNT(*) FROM agent_cards WHERE card_data->>'humanReadableId' = :decoded_id")
        result = await db.execute(raw_query, {"decoded_id": decoded_id})
        count = result.scalar_one()
        logger.info(f"Direct DB check: Found {count} cards with humanReadableId '{decoded_id}'")
        
        if count > 0:
            # Also show a sample of what's in the database
            sample_query = text("SELECT id, name, card_data->>'humanReadableId' AS hri FROM agent_cards LIMIT 3")
            sample_result = await db.execute(sample_query)
            sample_rows = sample_result.all()
            logger.info(f"Sample rows in database: {sample_rows}")
            
            # Since we confirmed it exists, retrieve it directly
            direct_query = text("SELECT * FROM agent_cards WHERE card_data->>'humanReadableId' = :hri")
            direct_result = await db.execute(direct_query, {"hri": decoded_id})
            row = direct_result.first()
            
            if row:
                # Get the UUID from the row (assuming it's the first column)
                card_id = row[0]
                
                # Use regular get_agent_card which we know works
                card = await agent_card.get_agent_card(db, card_id)
                
                if card:
                    response_dict = _build_agent_card_read_dict(card)
                    return schemas.AgentCardRead.model_validate(response_dict)
    except Exception as e:
        logger.warning(f"Error during direct DB check: {e}")
        
    # This CRUD function uses our enhanced query approaches
    logger.info(f"Calling CRUD function with humanReadableId: '{decoded_id}'")
    db_card = await agent_card.get_agent_card_by_human_readable_id(db=db, human_readable_id=decoded_id)
    
    if db_card is None:
        logger.warning(f"⚠️ Agent card with humanReadableId '{decoded_id}' not found via CRUD function.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Agent Card with humanReadableId '{decoded_id}' not found"
        )
    
    logger.info(f"✓ Successfully found agent card: {db_card.name} (ID: {db_card.id})")

    response_dict = _build_agent_card_read_dict(db_card) # Helper handles potential missing dev
    return schemas.AgentCardRead.model_validate(response_dict)
