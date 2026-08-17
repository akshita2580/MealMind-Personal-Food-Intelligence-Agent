"""
Check what's actually in the database right now.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

from src.database import get_engine, get_session, _PROJECT_ROOT
from src.models import OAuthState
from sqlmodel import select
import hashlib

engine = get_engine()
print(f"DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}")
print(f"PROJECT_ROOT: {_PROJECT_ROOT}")
print(f"Engine URL: {engine.url}")
print(f"DB file: {engine.url.database}")
print()

with get_session() as session:
    all_states = session.exec(select(OAuthState)).all()
    print(f"Total OAuthState rows: {len(all_states)}")
    
    if all_states:
        print("\nStates in database:")
        for i, state in enumerate(all_states):
            state_hash = hashlib.sha256(state.state.encode('utf-8')).hexdigest()[:12]
            print(f"  [{i}] hash={state_hash}")
            print(f"      telegram_id={state.telegram_id}")
            print(f"      expires_at={state.expires_at}")
            print(f"      created_at={state.created_at}")
            print()
    else:
        print("\n❌ NO STATES IN DATABASE")
