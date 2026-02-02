import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GCSurplusAdapter(BaseAuctionAdapter):
    """
    Hardened GC Surplus Adapter (Tier B - Playwright).
    Handles bilingual (EN/FR) state and dynamic pricing.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[GCSurplus] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Wait for title to appear
                await page.wait_for_selector('h1, .item-name', timeout=15000)
                await asyncio.sleep(4) # Stabilization

                # 1. Item Name
                item_name = "Unknown Item"
                name_selectors = ['h1', '.item-name', '#item-title']
                for sel in name_selectors:
                    if await page.locator(sel).count() > 0:
                        item_name = await page.locator(sel).first.inner_text()
                        break
                
                # 2. Bid Extraction
                current_bid = 0.0
                price_selectors = ['.current-bid-amount', '.bid', '.price', '.amount']
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
                loc_selector = '.location, .item-location'
                if await page.locator(loc_selector).count() > 0:
                    loc_text = await page.locator(loc_selector).first.inner_text()
                    if "," in loc_text:
                        parts = loc_text.split(",")
                        city = parts[0].strip()
                        state = parts[1].strip()

                # 4. Status Check
                status = "active"
                if "Closed" in await page.content() or "Fermé" in await page.content():
                    status = "expired"

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "website_name": "GC Surplus",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[GCSurplus] Error: {e}")
                return None
            finally:
                await browser.close()
