import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GovPlanetAdapter(BaseAuctionAdapter):
    """
    Hardened GovPlanet Adapter (Tier B - Playwright).
    Handles dynamic content and robust price extraction.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # We use a real browser here as GovPlanet uses significant JS for price/timer
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[GovPlanet] Fetching: {url}")
                # GovPlanet is slow to load, wait_until domcontentloaded is safer than networkidle
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Check for "Item is Not Available" or similar error states
                if "Not Available" in await page.title():
                    logger.warning(f"[GovPlanet] Item not available: {url}")
                    return {"status": "expired", "item_name": "Unavailable Item"}

                # Wait for core data to load
                await page.wait_for_selector('.item-title, h1', timeout=15000)
                await asyncio.sleep(5) # Stabilization

                # 1. Item Name
                item_name = await page.locator('.item-title, h1').first.inner_text()
                
                # 2. Bid Extraction
                current_bid = 0.0
                bid_selectors = ['.bid-price', '.current-bid', '.price', '#auction-price']
                for sel in bid_selectors:
                    if await page.locator(sel).count() > 0:
                        bid_text = await page.locator(sel).first.inner_text()
                        try:
                            clean_bid = re.sub(r'[^\d.]', '', bid_text)
                            if clean_bid:
                                current_bid = float(clean_bid)
                                break
                        except: continue

                # 3. Location (City, State)
                city, state = "Unknown", "Unknown"
                loc_selector = '.item-location, .location'
                if await page.locator(loc_selector).count() > 0:
                    loc_text = await page.locator(loc_selector).first.inner_text()
                    if "," in loc_text:
                        parts = loc_text.split(",")
                        city = parts[0].strip()
                        state = parts[1].strip()

                # 4. Closing Time / Status
                status = "active"
                if "Auction Closed" in await page.content():
                    status = "expired"

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "website_name": "GovPlanet",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[GovPlanet] Error: {e}")
                return None
            finally:
                await browser.close()
