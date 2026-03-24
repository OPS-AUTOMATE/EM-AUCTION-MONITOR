import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter
from utils.browser import launch_browser

logger = logging.getLogger(__name__)

class PublicSurplusAdapter(BaseAuctionAdapter):
    """
    Hardened Public Surplus Adapter (Tier B - Playwright).
    Highly deterministic extraction for high-volume government auctions.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[PublicSurplus] Using Proxy: {proxy_conf['server']}")

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[PublicSurplus] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Public Surplus often has a lot of content, wait for the core auction title
                await page.wait_for_selector('.auction-title, h1, #auctionTitle', timeout=15000)
                await asyncio.sleep(4) # Stabilization

                # 1. Item Name
                item_name = "Unknown Item"
                name_selectors = ['.auction-title', 'h1', '#auctionTitle']
                for sel in name_selectors:
                    if await page.locator(sel).count() > 0:
                        item_name = await page.locator(sel).first.inner_text()
                        break
                
                # 2. Bid Extraction
                current_bid = 0.0
                price_selectors = ['.current-bid', '.amount', '#currentBid', '.price']
                for sel in price_selectors:
                    if await page.locator(sel).count() > 0:
                        bid_text = await page.locator(sel).first.inner_text()
                        try:
                            clean_bid = re.sub(r'[^\d.]', '', bid_text)
                            if clean_bid:
                                current_bid = float(clean_bid)
                                break
                        except: continue

                # 3. Location
                city, state = "Unknown", "Unknown"
                # Public Surplus usually has location labels
                loc_text_all = await page.content()
                loc_match = re.search(r"Location:\s*</b>\s*([^<,]+),\s*([A-Z]{2})", loc_text_all, re.I)
                if loc_match:
                    city, state = loc_match.group(1).strip(), loc_match.group(2).strip()

                # 4. Status Check
                status = "active"
                if "Auction Closed" in await page.content() or "Ended" in await page.content():
                    status = "expired"

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "website_name": "Public Surplus",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[PublicSurplus] Error: {e}")
                return None
            finally:
                await browser.close()
