"""
BMA (British Medical Auctions) Adapter.
This module provides the BmaAdapter class for scraping item details from 
the British Medical Auctions website using Playwright.
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

    IMPORTANT: BMA requires registration to access certain fields (number of bidders, location).
    This adapter only extracts publicly visible data:
    - Item Name (title)
    - Starting Price (current bid)
    - Time Left

    Placeholder values are used for restricted fields:
    - Total Bidders: 0
    - Location: "Unknown, UK"
    - Premium: 15% (standard BMA premium)
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
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

                # Wait for lot details container
                await page.wait_for_selector('#LotDetailsTimed', timeout=15000)
                await asyncio.sleep(2)  # Stabilization

                # 1. Item Name - using provided selector
                item_name = "Unknown Item"
                try:
                    # Selector: #LotDetailsTimed > div > article > section.auctitle.auc_dtl_title.auc_mob_dis > div.tle.aucdttle > h3 > span
                    title_elem = page.locator(
                        '#LotDetailsTimed .auc_dtl_title h3 span').first
                    if await title_elem.count() > 0:
                        item_name = await title_elem.inner_text()
                except AttributeError as e:
                    logger.warning("[BMA] Title extraction failed: %s", e)
                    # Fallback to h3
                    if await page.locator('h3').count() > 0:
                        item_name = await page.locator('h3').first.inner_text()

                # 2. Starting Price - using provided selector
                current_bid = 0.0
                try:
                    # Selector: #currentBid > span
                    bid_elem = page.locator('#currentBid > span').first
                    if await bid_elem.count() > 0:
                        bid_text = await bid_elem.inner_text()
                        # Clean currency symbols (£, $)
                        clean_bid = re.sub(r'[^\d.]', '', bid_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                except AttributeError as e:
                    logger.warning("[BMA] Bid extraction failed: %s", e)

                # 3. Time Left - using provided selector pattern
                time_remaining_str = "Unknown"
                try:
                    # Selector pattern: #lot-time{lotid}
                    # We'll look for any element with id starting with "lot-time"
                    time_elem = page.locator('[id^="lot-time"]').first
                    if await time_elem.count() > 0:
                        time_remaining_str = await time_elem.inner_text()
                except AttributeError as e:
                    logger.warning("[BMA] Time extraction failed: %s", e)

                # 4. Placeholder values for auth-restricted fields
                total_bidders = 0  # Requires login
                city = "Unknown"   # Requires login
                state = "UK"       # Default for British auctions
                premium_percentage = 15  # Standard BMA premium

                # 5. Status Check: Hardened
                status = "active"
                content_lower = (await page.content()).lower()

                if "closed" in content_lower or "lot ended" in content_lower:
                    status = "expired"

                # If time remaining is present and has numbers, it's active
                if time_remaining_str and any(char.isdigit() for char in time_remaining_str):
                    if "ended" not in time_remaining_str.lower():
                        status = "active"

                return {
                    "item_name": str(item_name).strip()[:200],
                    "current_bid": current_bid,
                    "time_remaining_str": time_remaining_str,
                    "total_bidders": total_bidders,
                    "city": city,
                    "state": state,
                    "premium_percentage": premium_percentage,
                    "website_name": "British Medical Auctions",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[BMA] Error: %s", e)
                return None
            finally:
                await browser.close()
