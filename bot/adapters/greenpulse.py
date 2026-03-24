"""
Green Pulse Adapter Module.
Extracts listing details for medical asset remarketing.
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GreenPulseAdapter(BaseAuctionAdapter):
    """
    Hardened Green Pulse Adapter (Tier B - Playwright).
    Specialized for medical asset remarketing sites.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[GreenPulse] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info("[GreenPulse] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                # Wait for core UI elements
                try:
                    await page.wait_for_selector('h1, .product-title, .item-name', timeout=15000)
                except (PlaywrightError, asyncio.TimeoutError):
                    logger.warning("[GreenPulse] Timeout waiting for content selectors.")

                await asyncio.sleep(2) # Stabilization

                # 1. Item Name
                item_name = "Unknown Item"
                name_selectors = ['h1', '.product-title', '.item-name']
                for sel in name_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0:
                            item_name = (await loc.inner_text()).strip()
                            break
                    except (PlaywrightError, Exception):
                        continue
                
                # 2. Bid Extraction
                current_bid = 0.0
                price_selectors = ['.current-price', '.amount', '.bid-amount', '.price']
                for sel in price_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0:
                            bid_text = await loc.inner_text()
                            clean_bid = re.sub(r'[^\d.]', '', bid_text)
                            if clean_bid:
                                current_bid = float(clean_bid)
                                break
                    except (PlaywrightError, Exception):
                        continue

                # 3. Status Check
                status = "active"
                content_lower = (await page.content()).lower()
                if any(k in content_lower for k in ["sold", "not available", "expired"]):
                    status = "expired"

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "website_name": "Green Pulse",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[GreenPulse] Error: %s", e)
                return None
            finally:
                await browser.close()
