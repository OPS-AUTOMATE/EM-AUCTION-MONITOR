import asyncio
import logging
from datetime import datetime, timedelta, timezone
from db_client import get_supabase_client

logger = logging.getLogger(__name__)

async def run_lifecycle_manager():
    """
    Background worker that handles the cleanup of expired items.
    Rules:
    - Items are deleted 48 hours after they expire.
    - Auction is considered expired if 'closing_time' < now.
    """
    supabase = get_supabase_client()
    
    while True:
        try:
            logger.info("--- [LIFECYCLE CHECK] Running cleanup for expired items ---")
            
            # 1. Fetch all items (or just active/expired ones)
            # For efficiency in a large DB we would filter by date in the query
            response = supabase.table("auctions").select("id, closing_time, status").execute()
            auctions = response.data
            
            now = datetime.now(timezone.utc)
            deletion_threshold = timedelta(hours=48)
            
            for auction in auctions:
                closing_time_str = auction.get("closing_time")
                if not closing_time_str:
                    continue
                
                try:
                    # Supabase stores as ISO string: 2026-01-27T13:15:00+00:00
                    closing_time = datetime.fromisoformat(closing_time_str.replace("Z", "+00:00"))
                    
                    # Check if expired
                    if closing_time < now:
                        # It is expired. Now check if it's been more than 48 hours
                        time_since_expiry = now - closing_time
                        
                        if time_since_expiry > deletion_threshold:
                            logger.info(f"🗑️ [CLEANUP] Deleting item {auction['id']} (Expired {time_since_expiry.total_seconds()/3600:.1f} hours ago)")
                            supabase.table("auctions").delete().eq("id", auction["id"]).execute()
                        else:
                            # Just mark as expired if not already
                            if auction.get("status") != "expired":
                                logger.info(f"⌛ [STATUS Update] Marking item {auction['id']} as expired.")
                                supabase.table("auctions").update({"status": "expired"}).eq("id", auction["id"]).execute()
                
                except Exception as parse_e:
                    logger.warning(f"Error parsing closing time for {auction['id']}: {parse_e}")

        except Exception as e:
            logger.error(f"Lifecycle Manager Error: {e}")
            
        # Run cleanup every hour (or adjust as needed)
        await asyncio.sleep(3600) 
