import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from engine.models import TIER_INTERVALS_SECONDS, FetchTier

logger = logging.getLogger(__name__)

class DatabaseLayer:
    """
    Thin adapter for Supabase/Postgres. 
    Contains explicit queries only.
    """

    def __init__(self, supabase_client):
        self.supabase = supabase_client

    async def fetch_due_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieves items that are due for a refresh. 
        Fetches both 'active' items reaching their threshold and new 'pending_sync' items.
        """
        now = datetime.now(timezone.utc).isoformat()
        response = await asyncio.to_thread(
            self.supabase.table("auction_items").select("*")
            .or_("status.eq.active,status.eq.pending_sync")
            .or_(f"next_fetch_at.is.null,next_fetch_at.lte.{now}")
            .or_(f"locked_until.is.null,locked_until.lte.{now}")
            .order("next_fetch_at")
            .limit(limit)
            .execute
        )
        return response.data

    async def get_all_item_statuses(self) -> Dict[str, str]:
        """
        Retrieves status map for all relevant items (id -> status).
        Used for detecting manual Pause/Resume toggles.
        """
        response = await asyncio.to_thread(
            self.supabase.table("auction_items").select("id, status").execute
        )
        return {item['id']: item['status'] for item in response.data}

    async def fetch_all_items_minimal(self) -> List[Dict[str, Any]]:
        """
        Fetches id, status, closing_time, and locked_until for all items to check for auto-expirations.
        """
        response = await asyncio.to_thread(
            self.supabase.table("auction_items").select("id, status, closing_time, locked_until").execute
        )
        return response.data


    async def lock_item(self, item_id: str, worker_id: str, duration_seconds: int = 90) -> bool:
        """
        Locks an item using a simple timestamp-based lock.
        """
        now = datetime.now(timezone.utc)
        lock_until = (now + timedelta(seconds=duration_seconds)).isoformat()
        
        response = await asyncio.to_thread(
            self.supabase.table("auction_items").update({
                "locked_until": lock_until
            }).eq("id", item_id).execute
        )
        
        return len(response.data) > 0

    async def release_lock(self, item_id: str, worker_id: str):
        """
        Deterministic release of the item lock.
        """
        await asyncio.to_thread(
            self.supabase.table("auction_items").update({
                "locked_until": None
            }).eq("id", item_id).execute
        )

    async def update_item_success(self, item_id: str, scraped_data: Dict[str, Any], session_id: str = None):
        """
        Persists successful fetch results and calculates next run time.
        """
        now = datetime.now(timezone.utc)
        
        # Scheduling logic
        closing_time_str = scraped_data.get("closing_time")
        status = scraped_data.get("status", "active")
        
        # Automatic expiration check (Secondary safety)
        if closing_time_str:
            try:
                ct = datetime.fromisoformat(closing_time_str.replace("Z", "+00:00"))
                if ct < now: status = "expired"
            except: pass

        tier, next_fetch = self._calculate_next_run(closing_time_str) or (FetchTier.NORMAL, now + timedelta(hours=3))
        
        if status == "expired":
            next_fetch = now + timedelta(days=7) 
        
        interval_secs = int((next_fetch - now).total_seconds())
        logger.info(f"[DB] Item {item_id[:8]}: Tier={FetchTier(tier).name}, Refresh in {interval_secs}s")

        # --- CRITICAL: Do not overwrite 'paused' status from user ---
        try:
            current_db_resp = await asyncio.to_thread(
                self.supabase.table("auction_items").select("status").eq("id", item_id).execute
            )
            if current_db_resp.data:
                db_status = current_db_resp.data[0].get("status")
                # If user paused it while we were scraping, keep it paused.
                # Unless the new status is 'expired' (priority over paused).
                if db_status == "paused" and status != "expired":
                    status = "paused"
        except Exception as e:
            logger.warning(f"[DB] Could not verify current status for {item_id}: {e}")

        payload = {
            **scraped_data,
            "session_id": session_id,
            "fetch_tier": tier,
            "next_fetch_at": next_fetch.isoformat(),
            "last_scraped_at": now.isoformat(),
            "status": status,
            "error_message": None,
            "retry_count": 0,
            "locked_until": None  # Always release lock
        }
        
        await asyncio.to_thread(
            self.supabase.table("auction_items").update(payload).eq("id", item_id).execute
        )

    async def update_item_failure(self, item_id: str, error_message: str):
        """
        Persists failure state and handles backoff.
        """
        now = datetime.now(timezone.utc)
        
        try:
            current_db_resp = await asyncio.to_thread(
                self.supabase.table("auction_items").select("retry_count").eq("id", item_id).execute
            )
            if current_db_resp.data:
                current_retries = current_db_resp.data[0].get("retry_count") or 0
            else:
                current_retries = 0
        except Exception as e:
            logger.warning(f"[DB] Could not verify current retries for {item_id}: {e}")
            current_retries = 0
            
        new_retries = current_retries + 1

        # If the item was previously in 'error' state and the user manually re-activated it,
        # the retry_count was never reset. Detect this by checking if retries already exceeded
        # the limit — if so, treat this as a fresh cycle (reset to 1).
        if current_retries >= 3:
            logger.info(f"[DB] Item {item_id[:8]} was re-activated after error. Resetting retry counter.")
            new_retries = 1
        
        payload = {
            "error_message": error_message,
            "retry_count": new_retries,
            "locked_until": None
        }

        if new_retries >= 3:
            logger.error(f"[DB] Failure for {item_id[:8]} reached max retries ({new_retries}). Marking as error.")
            payload["status"] = "error"
        else:
            next_fetch = now + timedelta(minutes=5)
            logger.warning(f"[DB] Failure for {item_id[:8]}: {error_message}. Retry {new_retries}/3 in 300s.")
            payload["next_fetch_at"] = next_fetch.isoformat()
        
        await asyncio.to_thread(
            self.supabase.table("auction_items").update(payload).eq("id", item_id).execute
        )

    async def cleanup_expired_items(self):
        """
        Removes items that have been expired for more than 48 hours.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        try:
            await asyncio.to_thread(
                self.supabase.table("auction_items")
                .delete()
                .eq("status", "expired")
                .lt("closing_time", cutoff)
                .execute
            )
            logger.info(f"Ran cleanup for expired items older than {cutoff}")
        except Exception as e:
            logger.error(f"Cleanup Error: {e}")

    def _calculate_next_run(self, closing_time_iso: Optional[str]) -> tuple:
        """
        Smart Refresh Logic (Synchronized with USER strategy).
        Scales polling frequency based on proximity to auction close.
        """
        now = datetime.now(timezone.utc)
        
        if not closing_time_iso:
            # Marketplace/Persistent Listing Mode: Since there's no countdown timer,
            # we refresh every 6 hours (21,600s) to catch infrequent price or status updates.
            return FetchTier.NORMAL, now + timedelta(hours=6)
            
        try:
            # Force timezone awareness to prevent naive/aware subtraction crashes
            clean_iso = closing_time_iso.replace("Z", "+00:00")
            if "+" not in clean_iso and "-" not in clean_iso[10:]:
                clean_iso += "+00:00"
                
            closing_time = datetime.fromisoformat(clean_iso)
            remaining = (closing_time - now).total_seconds()
            
            if remaining <= 0:
                # ENDED: Once-a-day check to ensure it's cleared eventually
                tier = FetchTier.NORMAL
                interval = 86400 
            elif remaining <= 600: # 10 minutes
                tier = FetchTier.CRITICAL
                interval = 30
            elif remaining <= 3600: # 1 hour
                tier = FetchTier.URGENT
                interval = 120
            elif remaining <= 28800: # 8 hours
                tier = FetchTier.CLOSING
                interval = 3600
            else: # NORMAL (> 8 hours)
                tier = FetchTier.NORMAL
                interval = 10800
                
            return tier, now + timedelta(seconds=interval)
        except Exception as e:
            logger.warning(f"[DB] Interval calculation error: {e}")
            return FetchTier.NORMAL, now + timedelta(hours=1)
