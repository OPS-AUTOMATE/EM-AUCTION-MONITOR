import asyncio
from typing import Dict, List, Optional
import logging
from playwright.async_api import async_playwright, Browser, Playwright
from parsers.router import get_auction_data
from db_client import get_supabase_client
from constants import get_premium

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ScraperManager:
    """
    Manages a pool of active scraping tasks. 
    Handles task lifecycle: Start, Stop, Delete, and Clean Cleanup.
    Uses a shared Playwright browser instance for efficiency.
    """
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}  # auction_id -> asyncio.Task
        self.browser: Optional[Browser] = None
        self.context = None # Shared Context for Caching
        self.playwright: Optional[Playwright] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        async with self._lock:
            # 1. Check if browser is healthy
            is_healthy = self.browser and self.browser.is_connected()
            
            if not is_healthy:
                if self.browser:
                    logger.warning("Shared browser disconnected. Resetting...")
                    self.browser = None
                    self.context = None

                logger.info("Initializing shared Playwright browser instance...")
                try:
                    self.playwright = await async_playwright().start()
                    self.browser = await self.playwright.chromium.launch(
                        headless=True,
                        args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
                    )
                    # Create a persistent-like context that caches data
                    self.context = await self.browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080}
                    )
                    logger.info("Shared Context initialized (Caching Enabled).")
                except Exception as e:
                    logger.error(f"Failed to initialize browser: {e}")
                    self.browser = None
                    self.context = None
                    raise

    async def stop_all(self):
        """Stops all active tasks gracefully and closes the browser."""
        ids = list(self.active_tasks.keys())
        for auction_id in ids:
            await self.stop_scraping_item(auction_id)
        
        async with self._lock:
            try:
                # 1. Close Context first
                if self.context:
                    try:
                        await self.context.close()
                    except: pass
                
                # 2. Close Browser
                if self.browser:
                    try:
                        await self.browser.close()
                    except: pass
                
                # 3. CRITICAL: Stop the Playwright bridge itself
                if self.playwright:
                    try:
                        await self.playwright.stop()
                    except: pass

            except Exception as e:
                logger.warning(f"Shutdown cleanup: {e}")
            finally:
                self.context = None
                self.browser = None
                self.playwright = None
                
        
        logger.info("All scraper tasks terminated and browser shutdown.")

    async def start_scraping_item(self, auction_id: str, url: str):
        """Starts a background scraping task for a specific item if not already running."""
        if auction_id in self.active_tasks:
            logger.info(f"Task for item {auction_id} is already running.")
            return

        # Create the task
        task = asyncio.create_task(self._scraping_loop(auction_id, url))
        self.active_tasks[auction_id] = task
        logger.info(f"Started scraper for item {auction_id}")

    async def stop_scraping_item(self, auction_id: str):
        """Kills the background task for a specific item."""
        if auction_id in self.active_tasks:
            task = self.active_tasks.pop(auction_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"Successfully stopped/cancelled task for item {auction_id}")
        else:
            logger.warning(f"No active task found for item {auction_id} to stop.")

    async def delete_item(self, auction_id: str):
        """
        Stops the task and ensures no traces are left. 
        """
        await self.stop_scraping_item(auction_id)
        logger.info(f"Item {auction_id} purged from memory.")

    async def _scraping_loop(self, auction_id: str, url: str):
        """
        The actual loop that performs the scraping with Smart Refresh logic.
        """
        last_closing_time = None
        
        try:
            await self._ensure_browser()
            supabase = get_supabase_client()
            
            while True:
                try:
                    logger.info(f"--- [MONITORING CYCLE START] ---")
                    logger.info(f"ID: {auction_id} | URL: {url}")
                    
                    # 1. Perform the scrape using shared context for caching
                    data = await get_auction_data(url, browser=self.browser, context=self.context)
                    
                    if data:
                        logger.info(f"Step 2: Successfully extracted data from {data.get('website_name', 'Unknown')}")
                        logger.info(f"       -> Item: {(data.get('item_name') or 'N/A')[:40]}...")
                        logger.info(f"       -> Bid: ${data.get('current_bid')}")
                        
                        # Store closing time for interval calculation
                        if data.get("closing_time"):
                            last_closing_time = data.get("closing_time")

                        # 2. Add Premium and timestamp
                        scraped_premium = data.get("premium_percentage")
                        if not scraped_premium:
                            data["premium_percentage"] = get_premium(url)
                            
                        data["last_scraped_at"] = "now()"
                        
                        if data.get("status") != "expired":
                            data["status"] = "active"
                        
                        # 3. Update Supabase (Filter out None values and handle closing_time persistence)
                        update_payload = {k: v for k, v in data.items() if v is not None}
                        
                        # If a new closing_time wasn't found, keep using the last valid one we had
                        if "closing_time" not in update_payload and last_closing_time:
                            update_payload["closing_time"] = last_closing_time
                        
                        logger.info(f"Step 3: Syncing results to Supabase...")
                        supabase.table("auctions").update(update_payload).eq("id", auction_id).execute()
                        logger.info(f"✅ [SUCCESS] Auction synchronized: {data.get('item_name', '')}")
                    else:
                        logger.error(f"❌ [FAILED] Parser returned No Data for {url}")

                except Exception as inner_e:
                    logger.error(f"❌ [CRASH] Loop error for {auction_id}: {inner_e}")
                    # Signal that the browser needs a restart on the next ensure_browser call
                    if "closed" in str(inner_e).lower() or "disconnected" in str(inner_e).lower():
                        logger.warning(f"Browser crash detected by {auction_id}. Scheduling re-init.")
                        async with self._lock:
                            self.browser = None
                            self.context = None

                # --- SMART REFRESH LOGIC ---
                # Default: 3 hours (10,800s)
                interval = 10800 
                
                if last_closing_time:
                    try:
                        from datetime import datetime, timezone
                        # Handle ISO format from parsers
                        closing_dt = datetime.fromisoformat(last_closing_time.replace('Z', '+00:00'))
                        now = datetime.now(timezone.utc)
                        remaining = (closing_dt - now).total_seconds()

                        if remaining <= 0:
                            logger.info(f"🏁 Auction ended. Setting long sleep for {auction_id}.")
                            interval = 86400 # Check once a day if it somehow stayed active
                        elif remaining <= 600: # 10 minutes
                            interval = 30
                            logger.info(f"🔥 CRITICAL: < 10m left. Refreshing every 30s.")
                        elif remaining <= 3600: # 1 hour
                            interval = 120
                            logger.info(f"⚡ URGENT: < 1h left. Refreshing every 2m.")
                        elif remaining <= 28800: # 8 hours
                            interval = 3600
                            logger.info(f"⏳ CLOSING SOON: < 8h left. Refreshing every 1h.")
                        else:
                            interval = 10800
                            logger.info(f"💤 NORMAL: > 8h left. Refreshing every 3h.")
                    except Exception as e:
                        logger.warning(f"Interval calculation error: {e}. Defaulting to 1h.")
                        interval = 3600
                else:
                    # If we have no data yet (first scrape failed), retry sooner
                    interval = 300 # 5 minutes
                    logger.info(f"⚠️ No auction data yet. Retrying in 5m.")

                logger.info(f"Next refresh in {interval} seconds...")
                await asyncio.sleep(interval) 
        except asyncio.CancelledError:
            logger.info(f"Stopping monitor for {auction_id}...")
            raise
        except Exception as outer_e:
            logger.error(f"❌ [FATAL] Scraper task died for {auction_id}: {outer_e}")

async def main_demo():
    manager = ScraperManager()
    
    # Simulate adding an item
    await manager.start_scraping_item("auc_123", "https://gsaauctions.gov/...")
    
    await asyncio.sleep(5)
    
    # Simulate deleting an item
    await manager.delete_item("auc_123")
    
    await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main_demo())
