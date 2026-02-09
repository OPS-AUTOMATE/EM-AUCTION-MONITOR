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
            
            # --- STATUS CHANGE MONITOR & AUTO-EXPIRATION ---
            try:
                now_utc = datetime.now(timezone.utc)
                all_items = await db.fetch_all_items_minimal()
                for item in all_items:
                    item_id, current_status = item['id'], item['status']
                    closing_time_str = item.get('closing_time')
                    prev_status = previous_states.get(item_id)
                    
                    # 1. AUTO-EXPIRATION CHECK (Works even if Paused)
                    if current_status != 'expired' and closing_time_str:
                        try:
                            ct = datetime.fromisoformat(closing_time_str.replace("Z", "+00:00"))
                            if ct < now_utc:
                                logger.info(f"Item {item_id[:8]} has EXPIRED based on clock. Updating status.")
                                supabase.table("auction_items").update({"status": "expired"}).eq("id", item_id).execute()
                                current_status = 'expired'
                        except: pass

                    # 2. STATUS CHANGED
                    if prev_status != current_status:
                        if prev_status is not None:
                            logger.info(f"Item {item_id[:8]} state: {prev_status} -> {current_status}")
                        
                        # If user toggled to active OR it's a new active item, force fetch
                        if current_status == 'active':
                            supabase.table("auction_items").update({
                                "next_fetch_at": now_utc.isoformat(),
                                "locked_until": None
                            }).eq("id", item_id).execute()
                    
                    previous_states[item_id] = current_status
            except Exception as e:
                logger.error(f"State Tracker Error: {e}")
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
                
                await asyncio.sleep(1) 
                continue

            # Reset heartbeat timer when activity starts
            last_heartbeat = now_ts
            logger.info(f"Detected {len(due_items)} items due for refresh. Processing batch...")

            # 3. Process batch
            tasks = [worker.process_item(item, f"worker-{i}") for i, item in enumerate(due_items)]
            await asyncio.gather(*tasks)

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
