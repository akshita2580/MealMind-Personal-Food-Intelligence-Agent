"""Add user_id column to orders table."""
from sqlalchemy import text
from src.database import get_engine

engine = get_engine()

with engine.connect() as conn:
    # Check if column exists
    result = conn.execute(text("PRAGMA table_info(orders)"))
    columns = [row[1] for row in result]
    
    if 'user_id' not in columns:
        print("Adding user_id column to orders table...")
        conn.execute(text("ALTER TABLE orders ADD COLUMN user_id INTEGER"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id)"))
        conn.commit()
        print("✓ Migration complete")
    else:
        print("✓ user_id column already exists")
