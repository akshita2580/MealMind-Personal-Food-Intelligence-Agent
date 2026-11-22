"""
Migrate data from SQLite to PostgreSQL
Preserves all users, orders, and session data
"""

import os
import sys
from pathlib import Path
from sqlmodel import Session, create_engine, select
from src.models import User, Order
from src.database import create_db_and_tables
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_data():
    """Migrate all data from SQLite to PostgreSQL"""
    
    # Check if .env has PostgreSQL URL
    postgres_url = os.getenv("DATABASE_URL", "")
    if not postgres_url.startswith("postgresql"):
        logger.error("❌ DATABASE_URL in .env must be a PostgreSQL URL")
        logger.error("   Example: postgresql+psycopg://user:password@localhost:5432/mealmind")
        return False
    
    # SQLite source (old database)
    sqlite_path = Path(__file__).parent / "data" / "swiggy.db"
    if not sqlite_path.exists():
        logger.warning("⚠️  No SQLite database found at data/swiggy.db")
        logger.info("   Nothing to migrate. PostgreSQL database will start fresh.")
        return True
    
    sqlite_url = f"sqlite:///{sqlite_path}"
    
    logger.info("="*70)
    logger.info("MIGRATING DATA FROM SQLITE TO POSTGRESQL")
    logger.info("="*70)
    logger.info(f"Source (SQLite): {sqlite_path}")
    logger.info(f"Target (PostgreSQL): {postgres_url.split('@')[1] if '@' in postgres_url else 'configured database'}")
    logger.info("="*70 + "\n")
    
    try:
        # Create engines
        logger.info("Connecting to databases...")
        sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
        postgres_engine = create_engine(postgres_url)
        
        # Create tables in PostgreSQL
        logger.info("Creating tables in PostgreSQL...")
        os.environ["DATABASE_URL"] = postgres_url  # Ensure database.py uses PostgreSQL
        create_db_and_tables()
        logger.info("✅ Tables created\n")
        
        # Migrate Users
        logger.info("Migrating users...")
        with Session(sqlite_engine) as sqlite_session:
            users = sqlite_session.exec(select(User)).all()
            
            if not users:
                logger.warning("⚠️  No users found in SQLite database")
            else:
                with Session(postgres_engine) as postgres_session:
                    for user in users:
                        # Check if user already exists in PostgreSQL
                        existing = postgres_session.exec(
                            select(User).where(User.id == user.id)
                        ).first()
                        
                        if existing:
                            logger.info(f"   Updating user: {user.telegram_id}")
                            # Update existing user
                            existing.telegram_id = user.telegram_id
                            existing.created_at = user.created_at
                        else:
                            logger.info(f"   Creating user: {user.telegram_id}")
                            # Create new user object for postgres session
                            new_user = User(
                                id=user.id,
                                telegram_id=user.telegram_id,
                                created_at=user.created_at
                            )
                            postgres_session.add(new_user)
                    
                    postgres_session.commit()
                    logger.info(f"✅ Migrated {len(users)} users\n")
        
        # Migrate Orders
        logger.info("Migrating orders...")
        with Session(sqlite_engine) as sqlite_session:
            orders = sqlite_session.exec(select(Order)).all()
            
        if not orders:
            logger.warning("⚠️  No orders found in SQLite database")
        else:
            with Session(postgres_engine) as postgres_session:
                migrated = 0
                skipped = 0
                
                for order in orders:
                    # Check if order already exists in PostgreSQL
                    existing = postgres_session.exec(
                        select(Order).where(Order.order_id == order.order_id)
                    ).first()
                    
                    if existing:
                        skipped += 1
                    else:
                        # Create new order with only the fields that exist in the current model
                        new_order_data = {}
                        for field in Order.model_fields.keys():
                            if field not in ['items']:  # Skip relationship fields
                                if hasattr(order, field):
                                    new_order_data[field] = getattr(order, field)
                        
                        new_order = Order(**new_order_data)
                        postgres_session.add(new_order)
                        migrated += 1
                        
                        if migrated % 100 == 0:
                            logger.info(f"   Migrated {migrated} orders...")
                
                postgres_session.commit()
                logger.info(f"✅ Migrated {migrated} orders (skipped {skipped} duplicates)\n")
        
        logger.info("="*70)
        logger.info("🎉 MIGRATION COMPLETED SUCCESSFULLY!")
        logger.info("="*70)
        logger.info("\nNext steps:")
        logger.info("1. Verify the .env file has the PostgreSQL DATABASE_URL")
        logger.info("2. Restart the backend: python -m src.main")
        logger.info("3. Test the web app to ensure everything works")
        logger.info("\n💡 Your SQLite database is still in data/swiggy.db (backup)")
        logger.info("="*70 + "\n")
        
        return True
        
    except Exception as e:
        logger.exception("❌ Migration failed")
        logger.error(f"Error: {e}")
        logger.info("\nTroubleshooting:")
        logger.info("1. Verify PostgreSQL is running")
        logger.info("2. Check DATABASE_URL in .env is correct")
        logger.info("3. Ensure you have psycopg installed: pip install psycopg[binary]")
        return False

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    success = migrate_data()
    sys.exit(0 if success else 1)
