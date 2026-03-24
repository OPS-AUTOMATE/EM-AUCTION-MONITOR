"""
Public Surplus Adapter Module.
Extracts listing details for government and surplus auctions.
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class PublicSurplusAdapter(BaseAuctionAdapter):
    """
    Hardened Public Surplus Adapter (Tier B - Playwright).
    Handles government surplus auctions with standardized extraction patterns.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy & Browser Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[PublicSurplus] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info("[PublicSurplus] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                async def get_text(sel: str) -> str:
                    try:
                        loc = page.locator(sel).first
                        return (await loc.inner_text()).strip() if await loc.count() > 0 else ""
                    except: return ""

                # 1. Item Name
                item_name = await get_text(".auction-title") or await get_text("h1") or "Unknown Item"
                
                # 2. Bid Extraction
                bid_text = await get_text(".current-bid") or await get_text("#currentBid")
                current_bid = float(re.sub(r'[^\d.]', '', bid_text)) if bid_text and re.sub(r'[^\d.]', '', bid_text) else 0.0

                # 3. Location (Regex from HTML content)
                city, state = "Unknown", "Unknown"
                content = await page.content()
                match = re.search(r"Location:\s*</b>\s*([^<,]+),\s*([A-Z]{2})", content, re.I)
                if match:
                    city, state = match.group(1).strip(), match.group(2).strip()

                # 4. Status Check
                status = "active"
                if any(x in content for x in ["Auction Closed", "Ended", "Sold"]):
                    status = "expired"

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "website_name": "Public Surplus",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[PublicSurplus] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
