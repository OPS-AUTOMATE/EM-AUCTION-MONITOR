import asyncio
import logging
import os
import sys

# Ensure the root Scraper directory is in the path for absolute imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db_client import get_supabase_client
from manager import ScraperManager

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence noisy third-party libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("realtime").setLevel(logging.WARNING)

class AuctionBotRunner:
    def __init__(self):
        self.supabase = get_supabase_client()
        self.manager = ScraperManager()
        self.stop_event = asyncio.Event()

    async def poll_database(self):
        """
        Periodically checks the database for items that should be scraped.
        In a production environment, this would ideally use Supabase Realtime 
        (via a python client) but for simplicity, we poll every 10 seconds.
        """
        while not self.stop_event.is_set():
            try:
                # Find all auctions with status 'pending' or 'active'
                response = self.supabase.table("auctions").select("*").in_("status", ["pending", "active"]).execute()
                active_auctions = response.data

                # Start scrapers for any items not already running
                for auction in active_auctions:
                    if auction['id'] not in self.manager.active_tasks:
                        logger.info(f"🚀 [NEW TASK] Resuming/Starting monitoring for: {auction['id']}")
                        await self.manager.start_scraping_item(auction['id'], auction['url'])

                # Cleanup: Stop scrapers for items no longer in 'active' or 'pending' state
                current_ids = [a['id'] for a in active_auctions]
                running_ids = list(self.manager.active_tasks.keys())
                for rid in running_ids:
                    if rid not in current_ids:
                        logger.info(f"Item {rid} removed or stopped. Killing scraper task.")
                        await self.manager.delete_item(rid)

            except Exception as e:
                logger.error(f"Polling error: {e}")
            
            await asyncio.sleep(10)

    async def run(self):
        logger.info("Starting Auction Bot Engine...")
        await self.poll_database()

if __name__ == "__main__":
    runner = AuctionBotRunner()
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Stopping Engine...")
        runner.stop_event.set()
        # Explicitly stop all tasks
        loop = asyncio.get_event_loop()
        loop.run_until_complete(runner.manager.stop_all())
        logger.info("Graceful shutdown complete. Goodbye!")
