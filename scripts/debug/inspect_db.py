"""Inspect the real database to see what OAuthState rows exist."""
import hashlib
from pathlib import Path
from sqlmodel import select
from src.database import get_session, create_db_and_tables, get_engine, _PROJECT_ROOT
from src.models import OAuthState

create_db_and_tables()
engine = get_engine()
print(f"Engine URL: {engine.url}")
print(f"PROJECT_ROOT: {_PROJECT_ROOT}")

db_file = str(engine.url).replace("sqlite:///", "")
print(f"DB file path: {db_file}")
print(f"DB file exists: {Path(db_file).exists()}")
if Path(db_file).exists():
    print(f"DB file size: {Path(db_file).stat().st_size} bytes")
print()

with get_session() as session:
    states = session.exec(select(OAuthState)).all()
    print(f"Total OAuthState rows: {len(states)}")
    for s in states:
        h = hashlib.sha256(s.state.encode("utf-8")).hexdigest()[:12]
        print(f"  hash={h}  length={len(s.state)}  telegram_id={s.telegram_id}  created_at={s.created_at}  expires_at={s.expires_at}")
