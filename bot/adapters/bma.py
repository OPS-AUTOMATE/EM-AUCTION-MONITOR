"""
BMA (British Medical Auctions) Adapter.
Handles medical equipment auctions in the UK with standardized Playwright extraction.
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class BmaAdapter(BaseAuctionAdapter):
    """
    Hardened BMA (British Medical Auctions) Adapter (Tier B - Playwright).
    Extracts publicly visible data for international medical equipment listings.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy & Browser Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[BMA] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            try:
                logger.info("[BMA] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                async def get_text(sel: str) -> str:
                    try:
                        loc = page.locator(sel).first
                        return (await loc.inner_text()).strip() if await loc.count() > 0 else ""
                    except: return ""

                # 1. Item Name
                item_name = await get_text('#LotDetailsTimed .auc_dtl_title h3 span') or await get_text('h3') or "Unknown Item"
                
                # 2. Bid Extraction
                bid_text = await get_text('#currentBid > span')
                current_bid = float(re.sub(r'[^\d.]', '', bid_text)) if bid_text and re.sub(r'[^\d.]', '', bid_text) else 0.0

                # 3. Status & Time
                time_str = await get_text('[id^="lot-time"]')
                status = "active"
                content = (await page.content()).lower()
                
                if any(x in content for x in ["closed", "lot ended"]):
                    status = "expired"
                elif time_str and any(char.isdigit() for char in time_str):
                    if "ended" not in time_str.lower():
                        status = "active"

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "time_remaining_str": time_str or "Unknown",
                    "total_bidders": 0,
                    "city": "Unknown",
                    "state": "UK",
                    "premium_percentage": 15,
                    "website_name": "British Medical Auctions",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[BMA] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
