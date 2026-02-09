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

    last_heartbeat = 0
    last_cleanup = 0
    
    # Simple State Tracker: {item_id: status}
    previous_states = {}

    while True:
        try:
            now_ts = datetime.now().timestamp()
            
            # --- STATUS CHANGE MONITOR ---
            # Explicitly check for Paused/Resumed items to log specific messages
            # and to FORCE fetch resumed items immediately.
            try:
                current_states = await db.get_all_item_statuses()
                for item_id, current_status in current_states.items():
                    prev_status = previous_states.get(item_id)
                    
                    # 1. NEW ITEM DETECTED -> Force Fetch
                    if prev_status is None:
                        if current_status == 'active':
                            logger.info(f"New Active Item {item_id[:8]} detected. Forcing immediate fetch.")
                            try:
                                supabase.table("auction_items").update({
                                    "next_fetch_at": datetime.now(timezone.utc).isoformat(),
                                    "locked_until": None
                                }).eq("id", item_id).execute()
                            except Exception as db_err:
                                logger.error(f"Failed to force-fetch new item {item_id}: {db_err}")

                    # 2. STATUS CHANGED
                    elif prev_status != current_status:
                        if current_status == 'paused':
                            logger.info(f"Item {item_id[:8]} PAUSED by user.")
                        elif current_status == 'active' and prev_status == 'paused':
                            logger.info(f"Item {item_id[:8]} RESUMED by user. Forcing immediate fetch.")
                            # Force update next_fetch_at to NOW so it gets picked up immediately
                            try:
                                supabase.table("auction_items").update({
                                    "next_fetch_at": datetime.now(timezone.utc).isoformat(),
                                    "locked_until": None
                                }).eq("id", item_id).execute()
                            except Exception as db_err:
                                logger.error(f"Failed to force-fetch item {item_id}: {db_err}")
                            
                previous_states = current_states
            except Exception as e:
                logger.error(f"State Tracker Loop Error: {e}")
            # -----------------------------

            # 1. Periodic Cleanup (Every 1 hour)
            if now_ts - last_cleanup > 3600:
                await db.cleanup_expired_items()
                last_cleanup = now_ts

            # 2. Adaptive Polling: Check what's due
            due_items = await db.fetch_due_items(limit=10)

            if not due_items:
                # Log heartbeat summary every 1 minute for snappier feedback
                if now_ts - last_heartbeat > 60:
                    logger.debug("System Heartbeat: Engine Healthy.")
                    last_heartbeat = now_ts
                
                # SLEEP VERY SHORT: To react "instantly" to frontend changes (e.g. paused -> active),
                # we sleep for only 1 second instead of 5.
                await asyncio.sleep(1) 
                continue

            # Reset heartbeat timer when activity starts
            last_heartbeat = now_ts
            logger.info(f"Detected {len(due_items)} items due for refresh. Processing batch...")

            # 3. Process batch
            tasks = [worker.process_item(item, f"worker-{i}") for i, item in enumerate(due_items)]
            await asyncio.gather(*tasks)

            # If we just processed items, check immediately for the next batch
            # otherwise, wait a tiny bit to avoid hammering
            await asyncio.sleep(2)

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
