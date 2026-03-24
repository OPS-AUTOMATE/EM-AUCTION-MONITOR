import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter
from utils.browser import launch_browser

logger = logging.getLogger(__name__)

class EquipNetAdapter(BaseAuctionAdapter):
    """
    EquipNet Adapter (Tier B - Playwright).
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            browser = await launch_browser(p)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"Fetching EquipNet URL: {url}")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Extract Title
                title_elem = await page.query_selector("h1")
                item_name = await title_elem.inner_text() if title_elem else "Unknown EquipNet Item"
                item_name = item_name.strip()

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

                # Robust fallback for marketplace prices (e.g. h3 containing € or $)
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

                closing_time = None

                return {
                    "item_name": item_name,
                    "current_bid": current_bid,
                    "closing_time": closing_time,
                    "city": "See Website",
                    "url": url,
                    "site_key": "equipnet"
                }

            except Exception as e:
                logger.error(f"Error fetching EquipNet: {e}")
                return None
            finally:
                await browser.close()
