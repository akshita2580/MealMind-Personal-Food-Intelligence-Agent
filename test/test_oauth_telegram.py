import asyncio
import httpx
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlmodel import select
from src.main import app
from src.database import get_session, create_db_and_tables
from src.models import OAuthState, User, SwiggyConnection
from src.telegram_bot import generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge

client = TestClient(app)

def test_full_oauth_lifecycle(monkeypatch):
    create_db_and_tables()
    
    # 1. Generate state like Telegram
    telegram_id = "test_user_123"
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    
    with get_session() as session:
        # Simulate telegram_bot.py
        oauth_state = OAuthState(
            state=state,
            telegram_id=telegram_id,
            code_verifier=verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
        )
        session.add(oauth_state)
        session.commit()

    # Verify it exists
    with get_session() as session:
        st = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
        assert st is not None
        
    # Mock DCR and httpx
    async def mock_get_client(): return "mock_client"
    monkeypatch.setattr("src.dcr.get_or_register_client", mock_get_client)
    
    class MockResponse:
        status_code = 200
        def json(self): return {"access_token": "mock_token", "expires_in": 3600}
    
    async def mock_post(*args, **kwargs):
        return MockResponse()
        
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # 4. Simulate OAuth callback
    response = client.get(f"/api/auth/swiggy/callback?code=valid_code&state={state}")
    
    # 5. Verify state is accepted
    assert response.status_code == 200
    assert "Swiggy connected successfully!" in response.text
    
    # 8. Verify successful callback consumes state
    with get_session() as session:
        st = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
        assert st is None
        
        # Verify connection created
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        assert user is not None
        conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
        assert conn is not None
        assert conn.status == "CONNECTED"

def test_expired_callback(monkeypatch):
    create_db_and_tables()
    
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    
    with get_session() as session:
        # Simulate expired state
        oauth_state = OAuthState(
            state=state,
            telegram_id="test_user_456",
            code_verifier=verifier,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        session.add(oauth_state)
        session.commit()

    response = client.get(f"/api/auth/swiggy/callback?code=valid_code&state={state}")
    
    # 7. Verify state is rejected
    assert response.status_code == 400
    assert "State expired" in response.text
