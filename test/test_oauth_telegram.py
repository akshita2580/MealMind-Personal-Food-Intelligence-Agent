import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import app
from src.database import get_session, create_db_and_tables
from src.models import User, SwiggyConnection, OAuthState
from sqlmodel import Session, SQLModel, create_engine, select
from datetime import datetime, timedelta, timezone
import asyncio

from sqlalchemy.pool import StaticPool
from src.api import _session

@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()

@pytest.fixture(name="client")
def client_fixture(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    
def test_oauth_callback_success(engine, client):
    # Insert a valid state
    with Session(engine) as session:
        state = OAuthState(
            state="test_state",
            telegram_id="123456789",
            code_verifier="test_verifier",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
        )
        session.add(state)
        session.commit()
        
    with patch("src.api.httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600
        }
        # mock async context manager and post method
        mock_instance.__aenter__.return_value = mock_instance
        from unittest.mock import AsyncMock
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_instance
        
        response = client.get("/api/auth/swiggy/callback?state=test_state&code=test_code")
        assert response.status_code == 200
        assert "Swiggy connected successfully" in response.text
        
    # verify user and connection were created
    with Session(engine) as session:
        user = session.exec(select(User).where(User.telegram_id == "123456789")).first()
        assert user is not None
        conn = session.exec(select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)).first()
        assert conn is not None
        assert conn.status == "CONNECTED"
        assert conn.access_token != ""
        assert "test_access_token" not in conn.access_token # should be encrypted
        
        # verify state was deleted
        state_check = session.exec(select(OAuthState).where(OAuthState.state == "test_state")).first()
        assert state_check is None

def test_oauth_callback_invalid_state(client):
    response = client.get("/api/auth/swiggy/callback?state=invalid_state&code=test_code")
    assert response.status_code == 400
    assert "Invalid or missing state" in response.text

def test_oauth_callback_expired_state(engine, client):
    with Session(engine) as session:
        state = OAuthState(
            state="expired_state",
            telegram_id="123456789",
            code_verifier="test_verifier",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=15)
        )
        session.add(state)
        session.commit()
        
    response = client.get("/api/auth/swiggy/callback?state=expired_state&code=test_code")
    assert response.status_code == 400
    assert "State expired" in response.text
    
    # verify state was deleted
    with Session(engine) as session:
        state_check = session.exec(select(OAuthState).where(OAuthState.state == "expired_state")).first()
        assert state_check is None
