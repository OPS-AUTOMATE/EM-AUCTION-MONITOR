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
        self.playwright: Optional[Playwright] = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        async with self._lock:
            if not self.browser:
                logger.info("Initializing shared Playwright browser instance...")
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
                )

    async def stop_all(self):
        """Stops all active tasks gracefully and closes the browser."""
        ids = list(self.active_tasks.keys())
        for auction_id in ids:
            await self.stop_scraping_item(auction_id)
        
        async with self._lock:
            try:
                if self.browser:
                    await self.browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self.browser = None
                
            try:
                if self.playwright:
                    await self.playwright.stop()
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")
            finally:
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
        The actual loop that performs the scraping.
        """
        try:
            await self._ensure_browser()
            supabase = get_supabase_client()
            while True:
                try:
                    logger.info(f"--- [MONITORING CYCLE START] ---")
                    logger.info(f"ID: {auction_id} | URL: {url}")
                    
                    # 1. Perform the scrape using common browser
                    data = await get_auction_data(url, browser=self.browser)
                    
                    if data:
                        logger.info(f"Step 2: Successfully extracted data from {data.get('website_name', 'Unknown')}")
                        logger.info(f"       -> Item: {(data.get('item_name') or 'N/A')[:40]}...")
                        logger.info(f"       -> Bid: ${data.get('current_bid')}")
                        
                        # 2. Add Premium and timestamp
                        # Priority: Scraped Premium > Constant Map
                        # Treat 0 as "not found" if we have a constant available for the site
                        scraped_premium = data.get("premium_percentage")
                        if not scraped_premium:
                            data["premium_percentage"] = get_premium(url)
                            
                        data["last_scraped_at"] = "now()"
                        
                        # Only set to active if it's not already flagged as expired by the scraper
                        if data.get("status") != "expired":
                            data["status"] = "active"
                        
                        # 3. Update Supabase
                        logger.info(f"Step 3: Syncing results to Supabase...")
                        supabase.table("auctions").update(data).eq("id", auction_id).execute()
                        logger.info(f"✅ [SUCCESS] Auction synchronized.")
                    else:
                        logger.error(f"❌ [FAILED] Parser returned No Data for {url}")

                except Exception as inner_e:
                    logger.error(f"❌ [CRASH] Loop error for {auction_id}: {inner_e}")
                    import traceback
                    logger.error(traceback.format_exc())

                # Sleep before next refresh
                await asyncio.sleep(60) 
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
