import asyncio
from typing import Dict, List
import logging
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
    """
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}  # auction_id -> asyncio.Task

    async def stop_all(self):
        """Stops all active tasks gracefully."""
        ids = list(self.active_tasks.keys())
        for auction_id in ids:
            await self.stop_scraping_item(auction_id)
        logger.info("All scraper tasks terminated.")

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
        In a real app, this would also trigger a database soft-delete/remove.
        """
        await self.stop_scraping_item(auction_id)
        logger.info(f"Item {auction_id} purged from memory.")

    async def _scraping_loop(self, auction_id: str, url: str):
        """
        The actual loop that performs the scraping.
        """
        try:
            supabase = get_supabase_client()
            while True:
                try:
                    logger.info(f"--- [MONITORING CYCLE START] ---")
                    logger.info(f"Target URL: {url}")
                    
                    # 1. Perform the scrape
                    logger.info(f"Step 1: Initalizing Playwright browser and navigating...")
                    data = await get_auction_data(url)
                    
                    if data:
                        logger.info(f"Step 2: Successfully extracted data from {data.get('website_name', 'Unknown')}")
                        logger.info(f"       -> Item: {data.get('item_name')}")
                        logger.info(f"       -> Bid: ${data.get('current_bid')}")
                        
                        # 2. Add Premium and timestamp
                        data["premium_percentage"] = get_premium(url)
                        data["last_scraped_at"] = "now()"
                        data["status"] = "active"
                        
                        # 3. Update Supabase
                        logger.info(f"Step 3: Syncing results to Supabase Database...")
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
