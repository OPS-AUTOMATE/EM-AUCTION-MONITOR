"""
Global Med Auction Adapter Module.
Extracts listing details including countdowns, buyer premiums, and bidder counts.
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GlobalMedAdapter(BaseAuctionAdapter):
    """
    Hardened GlobalMed Adapter (Tier B - Playwright).
    Targeted extraction for medical equipment auctions.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[GlobalMed] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info("[GlobalMed] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                # Wait for core UI elements
                try:
                    await page.wait_for_selector('div[id^="lot-details-"]', timeout=15000)
                except (PlaywrightError, asyncio.TimeoutError):
                    logger.warning("[GlobalMed] Timeout waiting for lot details.")

                await asyncio.sleep(3) # Stabilization

                # 1. Item Name
                item_name = "Unknown Item"
                try:
                    title_elem = page.locator('div[id^="lot-details-"] .content a').first
                    if await title_elem.count() > 0:
                        item_name = (await title_elem.inner_text()).strip()
                    elif await page.locator('h1').count() > 0:
                        item_name = (await page.locator('h1').first.inner_text()).strip()
                except (PlaywrightError, Exception):
                    pass
                
                # 2. Current Bid
                current_bid = 0.0
                try:
                    bid_elem = page.locator('.next-minimum-bid-value, span.next-minimum-bid-value').first
                    if await bid_elem.count() > 0:
                        bid_text = await bid_elem.inner_text()
                        clean_bid = re.sub(r'[^\d.]', '', bid_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                except (PlaywrightError, Exception) as e:
                    logger.warning("[GlobalMed] Bid extraction failed: %s", e)

                # 3. Buyer Premium
                premium_percentage = 0
                try:
                    premium_elem = page.locator('.buyers-premium .field span').first
                    if await premium_elem.count() > 0:
                        premium_text = await premium_elem.inner_text()
                        premium_match = re.search(r'(\d+)', premium_text)
                        if premium_match:
                            premium_percentage = int(premium_match.group(1))
                except (PlaywrightError, Exception):
                    pass

                # 4. Time Remaining
                time_remaining_str = "Unknown"
                try:
                    countdown_elem = page.locator('.bidding-countdown span, .bidding-countdown').first
                    if await countdown_elem.count() > 0:
                        time_remaining_str = (await countdown_elem.inner_text()).strip()
                except (PlaywrightError, Exception):
                    pass

                # 5. Location
                city, state = "Unknown", "Unknown"
                try:
                    loc_elem = page.locator('div[id^="lot-details-"] .ui.segments .column').nth(3)
                    if await loc_elem.count() > 0:
                        loc_text = (await loc_elem.inner_text()).strip()
                        if "," in loc_text:
                            parts = loc_text.split(",")
                            city = parts[0].strip()
                            state = parts[1].strip() if len(parts) > 1 else "Unknown"
                except (PlaywrightError, Exception):
                    pass

                # 6. Total Bidders
                total_bidders = 0
                try:
                    bidders_elem = page.locator('.current-bid .field a').first
                    if await bidders_elem.count() > 0:
                        bidders_text = await bidders_elem.inner_text()
                        bidders_match = re.search(r'(\d+)', bidders_text)
                        if bidders_match:
                            total_bidders = int(bidders_match.group(1))
                except (PlaywrightError, Exception):
                    pass

                # Status Check
                status = "active"
                content_lower = (await page.content()).lower()
                if any(k in content_lower for k in ["closed", "lot ended", "bidding closed"]):
                    status = "expired"
                
                if time_remaining_str and any(char.isdigit() for char in time_remaining_str):
                    if "ended" not in time_remaining_str.lower():
                        status = "active"

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "premium_percentage": premium_percentage,
                    "time_remaining_str": time_remaining_str,
                    "city": city,
                    "state": state,
                    "total_bidders": total_bidders,
                    "website_name": "Global Med Auction",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[GlobalMed] Error: %s", e)
                return None
            finally:
                await browser.close()
