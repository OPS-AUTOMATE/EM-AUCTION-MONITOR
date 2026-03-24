"""
EquipNet Adapter Module.
Extracts listing details including title and asking price from EquipNet.
"""
import asyncio
import logging
import re
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class EquipNetAdapter(BaseAuctionAdapter):
    """
    EquipNet Adapter (Tier B - Playwright).
    Handles extraction for laboratory and manufacturing equipment listings.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[EquipNet] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info("[EquipNet] Fetching: %s", url)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Extract Title
                item_name = "Unknown EquipNet Item"
                title_elem = await page.query_selector("h1")
                if title_elem:
                    item_name = (await title_elem.inner_text()).strip()

                # Extract Location (New Strategy)
                location_text = "See Website"
                location_elem = await page.query_selector("p:has-text('Location:')")
                if location_elem:
                    location_full_text = await location_elem.inner_text()
                    if "Location:" in location_full_text:
                        location_text = location_full_text.split("Location:")[1].strip()

                # Extract Price (New Strategy)
                price_text = ""
                # Specific selector for EquipNet's greybox price
                price_elem = await page.query_selector(".greybox h3")
                if price_elem:
                    price_text = await price_elem.inner_text()
                
                # Fallback to old selectors
                if not price_text:
                    price_elem = await page.query_selector(".price-box, .product-price, .listing-price")
                    if not price_elem:
                        price_elem = await page.query_selector("text=Price") or await page.query_selector("text=Asking Price")
                        if price_elem:
                            parent = await price_elem.query_selector("xpath=..")
                            if parent:
                                price_text = await parent.inner_text()

                if not price_text and price_elem:
                    price_text = await price_elem.inner_text()

                # Fallback for marketplace prices (Gradients/H-tags)
                if not price_text:
                    h_elems = await page.query_selector_all("h2, h3")
                    for h in h_elems:
                        text = await h.inner_text()
                        if any(c in text for c in ["€", "$", "£", "EUR", "USD", "GBP"]):
                            price_text = text
                            break

                current_bid = 0.0
                if price_text:
                    # Clean currency/commas to extract pure number
                    clean_price = price_text.replace(",", "")
                    price_match = re.search(r"([\d]+\.?\d*)", clean_price)
                    if price_match:
                        current_bid = float(price_match.group(1))

                # Status Logic (Custom for EquipNet)
                # Toggles to 'expired' if the page indicates it's closed or ended.
                content = (await page.content()).lower()
                status = "active"
                if any(x in content for x in ["closed", "ended", "sold"]):
                    status = "expired"

                return {
                    "item_name": item_name,
                    "current_bid": current_bid,
                    "closing_time": None, # EquipNet listings are often persistent marketplaces
                    "city": location_text,
                    "url": url,
                    "site_key": "equipnet",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[EquipNet] Fetch error: %s", e)
                return None
            finally:
                await browser.close()
