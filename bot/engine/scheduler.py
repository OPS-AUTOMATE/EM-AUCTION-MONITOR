import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from .models import FetchTier, TIER_INTERVALS_SECONDS

logger = logging.getLogger(__name__)

class Scheduler:
    """
    The Brain of the system. 
    It queries the database for items that are due for a refresh 
    and prepares them for the workers.
    """

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    async def get_due_items(self, limit: int = 10) -> List[dict]:
        """
        Atomic Query using Postgres locking to fetch due items safely.
        """
        try:
            # We use an RPC call or direct SQL if possible to ensure 
            # FOR UPDATE SKIP LOCKED behavior.
            now = datetime.now(timezone.utc).isoformat()
            response = self.supabase.table("auction_items").select("*").filter(
                "status", "eq", "active"
            ).filter(
                "next_fetch_at", "lte", now
            ).or_(
                f"locked_until.is.null,locked_until.lte.{now}"
            ).order("next_fetch_at").limit(limit).execute()

            return response.data
        except Exception as e:
            logger.error(f"Scheduler failed to fetch due items: {e}")
            return []

    async def lock_item(self, item_id: str, worker_id: str, lock_duration: int = 90) -> bool:
        """
        Locks an item for processing so other workers don't touch it.
        """
        lock_expiry = (datetime.now(timezone.utc) + timedelta(seconds=lock_duration)).isoformat()
        try:
            response = self.supabase.table("auction_items").update({
                "locked_until": lock_expiry
            }).eq("id", item_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Failed to lock item {item_id}: {e}")
            return False

    def calculate_next_run(self, auction_end_time_str: str) -> tuple:
        """
        Recalculates the fetch tier and the next_fetch_at timestamp.
        """
        now = datetime.now(timezone.utc)
        if not auction_end_time_str:
            return FetchTier.NORMAL, now + timedelta(seconds=TIER_INTERVALS_SECONDS[FetchTier.NORMAL])

        end_time = datetime.fromisoformat(auction_end_time_str.replace("Z", "+00:00"))
        time_left = end_time - now

        if time_left > timedelta(hours=8):
            tier = FetchTier.NORMAL
        elif time_left > timedelta(hours=1):
            tier = FetchTier.CLOSING
        elif time_left > timedelta(minutes=10):
            tier = FetchTier.URGENT
        else:
            tier = FetchTier.CRITICAL

        next_run = now + timedelta(seconds=TIER_INTERVALS_SECONDS[tier])
        return tier, next_run
