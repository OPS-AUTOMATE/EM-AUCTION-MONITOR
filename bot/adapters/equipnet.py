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

                # Extract Price
                price_text = ""
                price_elem = await page.query_selector(".price-box, .product-price, .listing-price")
                if not price_elem:
                    price_elem = await page.query_selector("text=Price") or await page.query_selector("text=Asking Price")
                    if price_elem:
                        parent = await price_elem.query_selector("xpath=..")
                        if parent:
                            price_text = await parent.inner_text()

                if not price_text and price_elem:
                    price_text = await price_elem.inner_text()

                # Fallback for marketplace prices
                if not price_text:
                    h_elems = await page.query_selector_all("h2, h3")
                    for h in h_elems:
                        text = await h.inner_text()
                        if any(c in text for c in ["€", "$", "£", "EUR", "USD", "GBP"]):
                            price_text = text
                            break

                current_bid = 0.0
                if price_text:
                    price_match = re.search(r"([\d,]+\.?\d*)", price_text.replace(",", ""))
                    if price_match:
                        current_bid = float(price_match.group(1))

                return {
                    "item_name": item_name,
                    "current_bid": current_bid,
                    "closing_time": None,
                    "city": "See Website",
                    "url": url,
                    "site_key": "equipnet"
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[EquipNet] Fetch error: %s", e)
                return None
            finally:
                await browser.close()
