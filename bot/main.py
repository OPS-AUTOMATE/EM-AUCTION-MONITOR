import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add current directory to path for clean imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import DatabaseLayer
from engine.scheduler import Scheduler
from engine.worker import Worker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence deep library logs (GET/PATCH requests)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)

async def run_monitoring_engine(poll_interval: int = 5):
    """
    The Heartbeat of the system. 
    Optimized to reduce DB load and log noise.
    """
    # Auth & Client Initialization
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        logger.error("Missing SUPABASE_URL or SUPABASE_KEY environment variables.")
        return

    supabase = create_client(url, key)
    db = DatabaseLayer(supabase)
    scheduler = Scheduler(supabase)
    worker = Worker(db, scheduler)

    last_heartbeat_log = 0
    last_cleanup = 0
    
    # Simple State Tracker: {item_id: status}
    previous_states = {}

    while True:
        try:
            now_ts = datetime.now().timestamp()
            
            try:
                now_utc = datetime.now(timezone.utc)
                # fetch_all_items_minimal is already threaded now
                all_items = await db.fetch_all_items_minimal()
                current_ids = {item['id'] for item in all_items}
                
                # 1. Detect and log DELETIONS
                deleted_ids = set(previous_states.keys()) - current_ids
                for d_id in deleted_ids:
                    logger.info(f"Item {d_id[:8]} DELETED from system. Stopping monitor.")
                    del previous_states[d_id]

                for item in all_items:
                    item_id, current_status = item['id'], item['status']
                    closing_time_str = item.get('closing_time')
                    prev_status = previous_states.get(item_id)
                    
                    # 2. AUTO-EXPIRATION CHECK (Works even if Paused)
                    locked_until = item.get('locked_until')
                    is_locked = False
                    if locked_until:
                        try:
                            if datetime.fromisoformat(locked_until.replace("Z", "+00:00")) > now_utc:
                                is_locked = True
                        except: pass

                    if current_status != 'expired' and closing_time_str and not is_locked:
                        try:
                            ct = datetime.fromisoformat(closing_time_str.replace("Z", "+00:00"))
                            if ct < now_utc:
                                logger.info(f"Item {item_id[:8]} has EXPIRED based on clock. Updating status.")
                                # Use threaded update
                                await asyncio.to_thread(
                                    supabase.table("auction_items").update({"status": "expired"}).eq("id", item_id).execute
                                )
                                current_status = 'expired'
                        except: pass
                    
                    # 3. STATUS CHANGED (or NEW ITEM)
                    if prev_status != current_status:
                        if prev_status is not None:
                            logger.info(f"Item {item_id[:8]} state: {prev_status} -> {current_status}")
                        else:
                            logger.info(f"Item {item_id[:8]} ADDED to monitor.")
                        
                        # If user toggled to active OR it's a new active item, force fetch
                        if current_status == 'active':
                            await asyncio.to_thread(
                                supabase.table("auction_items").update({
                                    "next_fetch_at": now_utc.isoformat(),
                                    "locked_until": None
                                }).eq("id", item_id).execute
                            )
                    
                    previous_states[item_id] = current_status
            except Exception as e:
                if "ConnectionTerminated" in str(e) or "SSL" in str(e):
                    logger.warning(f"Database connection hiccup in State Tracker: {e}. Retrying in 5s...")
                else:
                    logger.error(f"State Tracker Error: {e}")
                await asyncio.sleep(5)

            # 1. Periodic Cleanup (Every 1 hour)
            if now_ts - last_cleanup > 3600:
                await db.cleanup_expired_items()
                last_cleanup = now_ts

            # 2. Adaptive Polling: Check what's due (already threaded in db.py)
            due_items = await db.fetch_due_items(limit=10)

            if not due_items:
                # Log heartbeat info every 10 minutes to show engine is spinning
                if now_ts - last_heartbeat_log > 600:
                    logger.info("System Heartbeat: Engine Spinning (No items due).")
                    last_heartbeat_log = now_ts
                
                await asyncio.sleep(2) 
                continue

            # Reset heartbeat log timer if we're actually processing
            last_heartbeat_log = now_ts
            logger.info(f"Detected {len(due_items)} items due for refresh. Processing batch...")

            # 3. Process batch with total batch timeout protection
            tasks = [worker.process_item(item, f"worker-{i}") for i, item in enumerate(due_items)]
            try:
                # Allow 5 minutes total for a batch of 10 items (generous)
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=300)
            except asyncio.TimeoutError:
                logger.error("Engine Block: Batch processing timed out after 5 minutes! Forcing next loop.")

            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Engine Loop Error: {e}")
            await asyncio.sleep(poll_interval)

if __name__ == "__main__":
    try:
        logger.info("Initializing IAMS Monitoring Engine...")
        asyncio.run(run_monitoring_engine())
    except KeyboardInterrupt:
        logger.info("Engine stopped by user.")
    except Exception as e:
        logger.critical(f"System crash: {e}")
