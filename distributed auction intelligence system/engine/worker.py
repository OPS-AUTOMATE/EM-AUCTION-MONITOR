import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

from .models import FetchMethod
from adapters.adapter_factory import get_adapter
from utils.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)

class Worker:
    """
    Stateless Worker that executes exactly one fetch cycle per item.
    All scheduling and backoff logic is deferred to the Scheduler/DB layer.
    """

    def __init__(self, db, scheduler):
        self.db = db
        self.scheduler = scheduler

    async def process_item(self, item: Dict[str, Any], worker_id: str):
        """
        Executes exactly one deterministic fetch cycle for the given item.
        """
        item_id = item['id']
        url = item['url']
        site_key = item['site_key'] or "mock"
        
        # 1. LOCK: Prevent other workers from touching this item
        locked = await self.db.lock_item(item_id, worker_id)
        if not locked:
            logger.warning(f"[WORKER] {worker_id} -> Failed to lock {item_id}, skipping.")
            return

        # 2. Resolve Proxy & session_id
        # If the item already has a session_id, reuse it. Otherwise, get a new one.
        session_id = item.get('session_id') or ProxyManager.get_session_id(item_id, site_key)
        
        # 3. Resolve Adapter
        adapter_class = get_adapter(site_key)
        if not adapter_class:
            logger.error(f"[WORKER] {worker_id} -> No hardened adapter found for site_key: {site_key}")
            await self.db.update_item_failure(item_id, f"MISSING_DRIVER: {site_key}")
            return
        
        # 4. Strategy Retrieval
        fetch_method = item.get('fetch_method') or FetchMethod.HTTP
        
        adapter = adapter_class(session_id=session_id)
        logger.info(f"[WORKER] {worker_id} -> Item {item_id[:8]} ({site_key}) using session {session_id[:6]}")

        try:
            # 5. Standardized Fetch
            scraped_data = await adapter.fetch(url, preferred_method=fetch_method)
            
            if scraped_data:
                # SUCCESS: Save the data AND the session_id we used
                await self.db.update_item_success(item_id, scraped_data, session_id=session_id)
                logger.info(f"[WORKER] {worker_id} -> Success for {item_id[:8]}")
            else:
                await self.db.update_item_failure(item_id, "EMPTY_RESULT")
                logger.warning(f"[WORKER] {worker_id} -> Empty result for {item_id[:8]}")

        except Exception as e:
            # FATAL: Parser or Network error
            error_msg = str(e)[:200]
            await self.db.update_item_failure(item_id, error_msg)
            logger.error(f"[WORKER] {worker_id} -> Fatal error for {item_id}: {error_msg}")
        
        finally:
            # Deterministic lock release
            await self.db.release_lock(item_id, worker_id)
