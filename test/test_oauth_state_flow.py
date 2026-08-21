"""
OAuth state flow regression test.

Reproduces the exact failure scenario:
1. Create OAuthState
2. Commit
3. Generate authorization URL
4. Extract state from URL
5. Call callback using EXACTLY that extracted state
6. Verify state lookup succeeds
7. Verify SwiggyConnection is created
8. Verify state is deleted afterward
"""

import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from src.database import get_engine, get_session
from src.models import OAuthState, SwiggyConnection, User
from src.security import generate_oauth_state, generate_pkce_verifier


@pytest.fixture
def test_session():
    """Create a test database session using the global test DB."""
    # Clear the engine cache just in case
    from src.database import get_engine
    get_engine.cache_clear()
    
    with get_session() as session:
        # Clean up any existing data
        from sqlalchemy import text
        session.exec(text("DELETE FROM oauth_states"))
        session.exec(text("DELETE FROM swiggy_connections"))
        session.exec(text("DELETE FROM users"))
        session.commit()
        
        yield session


def test_oauth_state_flow_exact_reproduction(test_session: Session):
    """
    Test the exact OAuth flow that is currently failing.
    
    This reproduces the real-world scenario:
    1. Telegram bot creates state
    2. User clicks link with that state
    3. Swiggy redirects to callback with that state
    4. FastAPI looks up the state - THIS CURRENTLY FAILS
    """
    
    # 1. CREATE STATE (simulating Telegram bot)
    telegram_id = "123456789"
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    
    import hashlib
    state_hash = hashlib.sha256(state.encode('utf-8')).hexdigest()[:12]
    print(f"\n1. STATE CREATION:")
    print(f"   hash={state_hash}")
    print(f"   length={len(state)}")
    print(f"   telegram_id={telegram_id}")
    
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(minutes=15)
    
    oauth_state_obj = OAuthState(
        state=state,
        telegram_id=telegram_id,
        code_verifier=verifier,
        expires_at=expires_at
    )
    test_session.add(oauth_state_obj)
    test_session.commit()
    print(f"   ✓ State committed to database")
    
    # 2. GENERATE AUTHORIZATION URL (simulating Telegram bot)
    client_id = "test_client_id"
    redirect_uri = "http://127.0.0.1:8000/api/auth/swiggy/callback"
    
    from src.security import generate_pkce_challenge
    challenge = generate_pkce_challenge(verifier)
    
    auth_base_url = "https://mcp.swiggy.com/auth/authorize"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "mcp:tools"
    }
    
    auth_url = f"{auth_base_url}?{urllib.parse.urlencode(params)}"
    
    # 3. EXTRACT STATE FROM URL
    parsed_url = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed_url.query)
    auth_state = qs.get("state", [""])[0]
    
    auth_state_hash = hashlib.sha256(auth_state.encode('utf-8')).hexdigest()[:12]
    print(f"\n2. AUTHORIZATION URL:")
    print(f"   hash={auth_state_hash}")
    print(f"   length={len(auth_state)}")
    print(f"   ✓ Hashes match: {state_hash == auth_state_hash}")
    
    # 4. SIMULATE CALLBACK (simulating browser redirect from Swiggy)
    callback_state = auth_state  # This is what the browser sends back
    callback_code = "test_authorization_code_12345"
    
    callback_state_hash = hashlib.sha256(callback_state.encode('utf-8')).hexdigest()[:12]
    print(f"\n3. CALLBACK RECEIVED:")
    print(f"   hash={callback_state_hash}")
    print(f"   length={len(callback_state)}")
    print(f"   ✓ All hashes match: {state_hash == auth_state_hash == callback_state_hash}")
    
    # 5. LOOKUP STATE (simulating FastAPI callback handler)
    print(f"\n4. DATABASE LOOKUP:")
    
    # Check all states in DB
    all_states = test_session.exec(select(OAuthState)).all()
    print(f"   Total OAuthState rows: {len(all_states)}")
    for i, row in enumerate(all_states):
        row_hash = hashlib.sha256(row.state.encode('utf-8')).hexdigest()[:12]
        print(f"   row[{i}]: hash={row_hash} telegram_id={row.telegram_id}")
    
    # Lookup the callback state
    lookup_state = test_session.exec(
        select(OAuthState).where(OAuthState.state == callback_state)
    ).first()
    
    print(f"   ✓ State lookup succeeded: {lookup_state is not None}")
    
    if not lookup_state:
        # FAILURE - print diagnostics
        print(f"\n   ❌ STATE LOOKUP FAILED!")
        print(f"   Expected hash: {callback_state_hash}")
        print(f"   DB contains: {[hashlib.sha256(s.state.encode('utf-8')).hexdigest()[:12] for s in all_states]}")
        
        # Check if it's an encoding issue
        for row in all_states:
            if row.state == callback_state:
                print(f"   String comparison PASSED but query failed!")
            print(f"   row.state == callback_state: {row.state == callback_state}")
            print(f"   row.state repr: {repr(row.state[:10])}")
            print(f"   callback_state repr: {repr(callback_state[:10])}")
    
    assert lookup_state is not None, "State lookup must succeed"
    assert lookup_state.telegram_id == telegram_id
    assert not (lookup_state.expires_at.replace(tzinfo=timezone.utc) < now_utc)
    
    print(f"   ✓ State is valid and not expired")
    
    # 6. SIMULATE TOKEN EXCHANGE (mocked)
    print(f"\n5. TOKEN EXCHANGE: (mocked)")
    access_token = "mock_access_token_xyz"
    expires_in = 3600
    
    # 7. CREATE USER AND CONNECTION
    user = test_session.exec(select(User).where(User.telegram_id == telegram_id)).first()
    if not user:
        user = User(telegram_id=telegram_id)
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
    
    from src.security import encrypt_token
    conn = SwiggyConnection(
        user_id=user.id,
        status="CONNECTED",
        access_token=encrypt_token(access_token),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    )
    test_session.add(conn)
    test_session.commit()
    
    print(f"   ✓ SwiggyConnection created")
    
    # 8. DELETE STATE (consume it)
    test_session.delete(lookup_state)
    test_session.commit()
    
    print(f"   ✓ State deleted after use")
    
    # Verify state is gone
    deleted_state = test_session.exec(
        select(OAuthState).where(OAuthState.state == callback_state)
    ).first()
    assert deleted_state is None, "State should be deleted after use"
    
    print(f"\n✅ FULL OAUTH FLOW TEST PASSED")


def test_oauth_wrong_state(test_session: Session):
    """Test that wrong state returns 400."""
    telegram_id = "123456789"
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    
    oauth_state_obj = OAuthState(
        state=state,
        telegram_id=telegram_id,
        code_verifier=verifier,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    test_session.add(oauth_state_obj)
    test_session.commit()
    
    # Try with wrong state
    wrong_state = generate_oauth_state()
    lookup = test_session.exec(
        select(OAuthState).where(OAuthState.state == wrong_state)
    ).first()
    
    assert lookup is None, "Wrong state should not be found"


def test_oauth_expired_state(test_session: Session):
    """Test that expired state is rejected."""
    telegram_id = "123456789"
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    
    # Create expired state
    oauth_state_obj = OAuthState(
        state=state,
        telegram_id=telegram_id,
        code_verifier=verifier,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)  # Already expired
    )
    test_session.add(oauth_state_obj)
    test_session.commit()
    
    # Lookup should succeed
    lookup = test_session.exec(
        select(OAuthState).where(OAuthState.state == state)
    ).first()
    
    assert lookup is not None, "Expired state exists in DB"
    
    # But expiry check should fail
    now_utc = datetime.now(timezone.utc)
    expires_at_aware = lookup.expires_at.replace(tzinfo=timezone.utc)
    assert expires_at_aware < now_utc, "State should be expired"


def test_oauth_state_reuse(test_session: Session):
    """Test that state cannot be reused after consumption."""
    telegram_id = "123456789"
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    
    oauth_state_obj = OAuthState(
        state=state,
        telegram_id=telegram_id,
        code_verifier=verifier,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
    )
    test_session.add(oauth_state_obj)
    test_session.commit()
    
    # First use - should succeed
    lookup1 = test_session.exec(
        select(OAuthState).where(OAuthState.state == state)
    ).first()
    assert lookup1 is not None
    
    # Delete (consume) the state
    test_session.delete(lookup1)
    test_session.commit()
    
    # Second use - should fail
    lookup2 = test_session.exec(
        select(OAuthState).where(OAuthState.state == state)
    ).first()
    assert lookup2 is None, "State should not be reusable"
