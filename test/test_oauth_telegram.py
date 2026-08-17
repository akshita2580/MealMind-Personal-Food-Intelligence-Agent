"""
OAuth state lifecycle tests.

Tests the REAL flow: create state → commit → build auth URL → extract state
from URL → call callback with exactly that state → verify success/failure.
"""
import hashlib
import urllib.parse

import httpx
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlmodel import select

from src.main import app
from src.database import get_session, create_db_and_tables
from src.models import OAuthState, User, SwiggyConnection
from src.security import generate_oauth_state, generate_pkce_verifier, generate_pkce_challenge

client = TestClient(app)


def _mock_token_exchange(monkeypatch):
    """Set up mocks for DCR and Swiggy token exchange."""
    async def mock_get_client():
        return "mock_client"
    monkeypatch.setattr("src.dcr.get_or_register_client", mock_get_client)

    class MockResponse:
        status_code = 200
        def json(self):
            return {"access_token": "mock_token_value", "expires_in": 3600}

    async def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)


def test_full_oauth_lifecycle_via_auth_url(monkeypatch):
    """
    Reproduce the REAL flow end-to-end:
    1. Create state exactly like telegram_bot.py does
    2. Commit to DB
    3. Build the authorization URL with urlencode
    4. Extract state from the URL (as Swiggy would pass it back)
    5. Call the callback with EXACTLY that extracted state
    6. Verify success
    """
    create_db_and_tables()
    _mock_token_exchange(monkeypatch)

    telegram_id = "test_url_lifecycle_user"
    state = generate_oauth_state()
    verifier = generate_pkce_verifier()
    challenge = generate_pkce_challenge(verifier)

    # 1 & 2: Create and commit state (exactly as telegram_bot does)
    with get_session() as session:
        oauth_state = OAuthState(
            state=state,
            telegram_id=telegram_id,
            code_verifier=verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        session.add(oauth_state)
        session.commit()

    # Hash for verification
    creation_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()[:12]

    # 3: Build authorization URL (exactly as telegram_bot does)
    params = {
        "client_id": "mock_client",
        "response_type": "code",
        "redirect_uri": "http://127.0.0.1:8000/api/auth/swiggy/callback",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "mcp:tools",
    }
    auth_url = f"https://mcp.swiggy.com/auth/authorize?{urllib.parse.urlencode(params)}"

    # 4: Extract state from URL (simulating what Swiggy sends back)
    parsed = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed.query)
    extracted_state = qs["state"][0]

    authorize_hash = hashlib.sha256(extracted_state.encode("utf-8")).hexdigest()[:12]

    # Verify hashes match
    assert creation_hash == authorize_hash, (
        f"State mismatch: creation={creation_hash} authorize={authorize_hash}"
    )
    assert extracted_state == state, "Extracted state differs from original"
    assert len(extracted_state) == len(state)

    # 5: Call callback with the extracted state
    callback_hash = hashlib.sha256(extracted_state.encode("utf-8")).hexdigest()[:12]
    assert callback_hash == creation_hash

    response = client.get(
        f"/api/auth/swiggy/callback?code=test_auth_code&state={urllib.parse.quote(extracted_state, safe='')}"
    )

    # 6: Verify success
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    assert "Swiggy connected successfully!" in response.text

    # 7: Verify state consumed
    with get_session() as session:
        st = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
        assert st is None, "State should be deleted after successful callback"

    # 8: Verify SwiggyConnection created with encrypted token
    with get_session() as session:
        user = session.exec(select(User).where(User.telegram_id == telegram_id)).first()
        assert user is not None
        conn = session.exec(
            select(SwiggyConnection).where(SwiggyConnection.user_id == user.id)
        ).first()
        assert conn is not None
        assert conn.status == "CONNECTED"
        assert conn.expires_at is not None
        # Token must be ciphertext, not the raw mock value
        assert conn.access_token != "mock_token_value", "Token should be encrypted"
        assert len(conn.access_token) > 50, "Encrypted token should be long"


def test_wrong_state_rejected(monkeypatch):
    """A completely fabricated state should be rejected."""
    create_db_and_tables()
    response = client.get(
        "/api/auth/swiggy/callback?code=some_code&state=totally_wrong_state_value"
    )
    assert response.status_code == 400
    assert "Invalid or missing state" in response.text


def test_expired_state_rejected(monkeypatch):
    """A genuinely expired state must be rejected."""
    create_db_and_tables()

    state = generate_oauth_state()
    verifier = generate_pkce_verifier()

    with get_session() as session:
        oauth_state = OAuthState(
            state=state,
            telegram_id="test_expired_user",
            code_verifier=verifier,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        session.add(oauth_state)
        session.commit()

    response = client.get(
        f"/api/auth/swiggy/callback?code=some_code&state={state}"
    )
    assert response.status_code == 400
    assert "State expired" in response.text


def test_reused_state_rejected(monkeypatch):
    """After a successful callback, the same state must not work again."""
    create_db_and_tables()
    _mock_token_exchange(monkeypatch)

    state = generate_oauth_state()
    verifier = generate_pkce_verifier()

    with get_session() as session:
        oauth_state = OAuthState(
            state=state,
            telegram_id="test_reuse_user",
            code_verifier=verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        session.add(oauth_state)
        session.commit()

    # First use: should succeed
    response = client.get(f"/api/auth/swiggy/callback?code=auth_code&state={state}")
    assert response.status_code == 200

    # Second use: should fail
    response = client.get(f"/api/auth/swiggy/callback?code=auth_code&state={state}")
    assert response.status_code == 400
    assert "Invalid or missing state" in response.text


def test_token_exchange_failure_still_consumes_state(monkeypatch):
    """Even if token exchange fails, the state must be consumed."""
    create_db_and_tables()

    async def mock_get_client():
        return "mock_client"
    monkeypatch.setattr("src.dcr.get_or_register_client", mock_get_client)

    class FailResponse:
        status_code = 401
        text = "unauthorized"

    async def mock_post(*args, **kwargs):
        return FailResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    state = generate_oauth_state()
    verifier = generate_pkce_verifier()

    with get_session() as session:
        oauth_state = OAuthState(
            state=state,
            telegram_id="test_fail_exchange_user",
            code_verifier=verifier,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        session.add(oauth_state)
        session.commit()

    response = client.get(f"/api/auth/swiggy/callback?code=auth_code&state={state}")
    assert response.status_code == 400
    assert "Token exchange failed" in response.text

    # State must still be consumed
    with get_session() as session:
        st = session.exec(select(OAuthState).where(OAuthState.state == state)).first()
        assert st is None, "State should be deleted even after failed token exchange"


def test_multiple_states_coexist():
    """Clicking 'Connect Swiggy' twice creates two valid states; both remain valid."""
    create_db_and_tables()

    state_a = generate_oauth_state()
    state_b = generate_oauth_state()

    with get_session() as session:
        for s in [state_a, state_b]:
            oauth_state = OAuthState(
                state=s,
                telegram_id="test_multi_user",
                code_verifier=generate_pkce_verifier(),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
            session.add(oauth_state)
        session.commit()

    # Both should exist
    with get_session() as session:
        a = session.exec(select(OAuthState).where(OAuthState.state == state_a)).first()
        b = session.exec(select(OAuthState).where(OAuthState.state == state_b)).first()
        assert a is not None, "State A should exist"
        assert b is not None, "State B should exist"
