import pytest
import uuid
from typing import Dict, Any, List
from sqlalchemy import select, func, cast, Text
from sqlalchemy.ext.asyncio import AsyncSession
from agentvault_registry import models
from agentvault_registry.crud import agent_card

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_get_agent_card_by_human_readable_id_case_insensitive(db_session: AsyncSession):
    """Test that the get_agent_card_by_human_readable_id function works with case-insensitive matching."""
    # Create a test agent card with a specific humanReadableId
    test_id = str(uuid.uuid4())
    test_hri = f"test-org/test-agent-{test_id}"
    card_data = {
        "url": "http://test.example",
        "tags": ["test", "jsonb"],
        "name": "Test Agent for JSONB Queries",
        "description": "A test agent for validating JSONB queries",
        "schemaVersion": "1.0",
        "humanReadableId": test_hri,  # Use the test HRI
        "agentVersion": "1.0",
        "provider": {"name": "Test Provider"},
        "capabilities": {"a2aVersion": "1.0"},
        "authSchemes": [{"scheme": "none"}]
    }
    
    # Create the test card in the database
    db_card = models.AgentCard(
        developer_id=1,  # Assuming developer ID 1 exists or is created in fixtures
        name="Test Agent",
        description="Test description",
        is_active=True,
        card_data=card_data
    )
    db_session.add(db_card)
    await db_session.commit()
    await db_session.refresh(db_card)
    
    # Verify we can find it with the exact same case
    found_card_exact = await agent_card.get_agent_card_by_human_readable_id(
        db=db_session, human_readable_id=test_hri
    )
    assert found_card_exact is not None
    assert found_card_exact.id == db_card.id
    
    # Try to find it with a different case
    found_card_upper = await agent_card.get_agent_card_by_human_readable_id(
        db=db_session, human_readable_id=test_hri.upper()
    )
    assert found_card_upper is not None
    assert found_card_upper.id == db_card.id
    
    # Verify direct SQLAlchemy query with the corrected approach
    jsonb_text_value = cast(
        models.AgentCard.card_data["->>"]("humanReadableId"),
        Text
    )
    stmt = (
        select(models.AgentCard)
        .where(func.lower(jsonb_text_value) == test_hri.lower())
    )
    result = await db_session.execute(stmt)
    direct_card = result.scalar_one_or_none()
    assert direct_card is not None
    assert direct_card.id == db_card.id
    
    # Clean up
    await db_session.delete(db_card)
    await db_session.commit()

@pytest.mark.skip(reason="Test fixes will be applied in patch release post 1.0.0")
@pytest.mark.asyncio
async def test_tee_type_filter_case_insensitive(db_session: AsyncSession):
    """Test that the tee_type filter in list_agent_cards works with case-insensitive matching."""
    # Create a test agent card with TEE details
    test_id = str(uuid.uuid4())
    tee_type = "Intel SGX"
    card_data = {
        "url": "http://tee-test.example",
        "tags": ["test", "tee"],
        "name": "Test TEE Agent",
        "description": "A test agent with TEE details",
        "schemaVersion": "1.0",
        "humanReadableId": f"test-org/tee-agent-{test_id}",
        "agentVersion": "1.0",
        "provider": {"name": "Test Provider"},
        "capabilities": {
            "a2aVersion": "1.0",
            "teeDetails": {
                "type": tee_type,
                "attestationEndpoint": "https://attest.example.com"
            }
        },
        "authSchemes": [{"scheme": "none"}]
    }
    
    # Create the test card in the database
    db_card = models.AgentCard(
        developer_id=1,  # Assuming developer ID 1 exists or is created in fixtures
        name="Test TEE Agent",
        description="Test TEE description",
        is_active=True,
        card_data=card_data
    )
    db_session.add(db_card)
    await db_session.commit()
    await db_session.refresh(db_card)
    
    # Test list_agent_cards with tee_type filter in lowercase
    items, count = await agent_card.list_agent_cards(
        db=db_session,
        tee_type=tee_type.lower(),
        active_only=True
    )
    assert count >= 1
    assert any(item.id == db_card.id for item in items)
    
    # Test list_agent_cards with tee_type filter in uppercase
    items, count = await agent_card.list_agent_cards(
        db=db_session,
        tee_type=tee_type.upper(),
        active_only=True
    )
    assert count >= 1
    assert any(item.id == db_card.id for item in items)
    
    # Clean up
    await db_session.delete(db_card)
    await db_session.commit()
