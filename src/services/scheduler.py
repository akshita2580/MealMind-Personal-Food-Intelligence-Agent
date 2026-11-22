"""
Background scheduler for automatic Swiggy synchronization.

Uses APScheduler for reliable periodic tasks.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session, select, func

from src.database import get_session
from src.models import User, SwiggyConnection, SwiggySyncLog, WebSession
from src.services.sync_service import SwiggySyncService

logger = logging.getLogger(__name__)

# Configuration from environment
SYNC_INTERVAL_MINUTES = int(os.getenv("SWIGGY_AUTO_SYNC_INTERVAL_MINUTES", "5"))
MAX_ACTIVE_USERS_PER_RUN = int(os.getenv("SWIGGY_MAX_ACTIVE_USERS_PER_RUN", "10"))
USER_ACTIVITY_WINDOW_MINUTES = int(os.getenv("SWIGGY_USER_ACTIVITY_WINDOW_MINUTES", "30"))


class SwiggyAutoSyncScheduler:
    """Manages automatic synchronization for active users."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running = False
    
    def start(self) -> None:
        """Start the scheduler with periodic sync job."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        # Add periodic sync job
        self.scheduler.add_job(
            self._run_sync_for_active_users,
            trigger=IntervalTrigger(minutes=SYNC_INTERVAL_MINUTES),
            id="swiggy_auto_sync",
            name="Swiggy Automatic Order Sync",
            replace_existing=True,
            max_instances=1,  # Prevent overlapping runs
            coalesce=True,    # Skip missed runs
        )
        
        self.scheduler.start()
        self._running = True
        logger.info(f"Swiggy auto-sync scheduler started (interval: {SYNC_INTERVAL_MINUTES}min)")
    
    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return
        
        self.scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Swiggy auto-sync scheduler stopped")
    
    def _run_sync_for_active_users(self) -> None:
        """Run sync for all recently active users with valid Swiggy connections."""
        logger.info("Starting scheduled Swiggy sync for active users")
        
        try:
            with get_session() as db:
                # Find users with active web sessions in the activity window
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=USER_ACTIVITY_WINDOW_MINUTES)
                
                active_users = db.exec(
                    select(User).join(WebSession).where(
                        WebSession.last_used_at >= cutoff,
                        WebSession.expires_at > datetime.now(timezone.utc),
                    ).distinct().limit(MAX_ACTIVE_USERS_PER_RUN)
                ).all()
                
                logger.info(f"Found {len(active_users)} active users for auto-sync")
                
                for user in active_users:
                    try:
                        self._sync_user_orders(db, user.id)
                    except Exception as e:
                        logger.error(f"Auto-sync failed for user {user.id}: {e}", exc_info=True)
                        
        except Exception as e:
            logger.error(f"Scheduled sync job failed: {e}", exc_info=True)
    
    def _sync_user_orders(self, db: Session, user_id: int) -> None:
        """Sync orders for a single user."""
        # Check if user has valid Swiggy connection
        conn = db.exec(
            select(SwiggyConnection).where(
                SwiggyConnection.user_id == user_id,
                SwiggyConnection.status == "CONNECTED",
            )
        ).first()
        
        if not conn:
            logger.debug(f"User {user_id} has no active Swiggy connection")
            return
        
        if conn.expires_at and conn.expires_at < datetime.now(timezone.utc):
            logger.info(f"User {user_id} Swiggy token expired")
            return
        
        # Check if we synced recently (avoid too frequent syncs)
        recent_sync = db.exec(
            select(SwiggySyncLog).where(
                SwiggySyncLog.user_id == user_id,
                SwiggySyncLog.sync_type == "orders_from_swiggy",
                SwiggySyncLog.status.in_(["success", "partial"]),
                SwiggySyncLog.started_at >= datetime.now(timezone.utc) - timedelta(minutes=SYNC_INTERVAL_MINUTES * 2),
            ).order_by(SwiggySyncLog.started_at.desc())
        ).first()
        
        if recent_sync:
            logger.debug(f"User {user_id} synced recently, skipping")
            return
        
        # Get default address
        # Note: We can't call async MCP from sync context easily
        # For now, we'll skip auto-sync if no default address
        # In production, you might want to store default address in user preferences
        
        logger.info(f"Auto-sync triggered for user {user_id}")
        # The actual async sync would need to be handled differently
        # For now, we just log and rely on manual sync from UI
        # A full implementation would use a task queue (Celery/RQ) for async work
    
    def trigger_sync_for_user(self, user_id: int) -> bool:
        """Manually trigger sync for a specific user (called from API)."""
        try:
            with get_session() as db:
                self._sync_user_orders(db, user_id)
            return True
        except Exception as e:
            logger.error(f"Manual trigger failed for user {user_id}: {e}")
            return False


# Global scheduler instance
_scheduler: Optional[SwiggyAutoSyncScheduler] = None


def get_scheduler() -> SwiggyAutoSyncScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SwiggyAutoSyncScheduler()
    return _scheduler


def start_scheduler() -> None:
    """Start the global scheduler."""
    get_scheduler().start()


def stop_scheduler() -> None:
    """Stop the global scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None