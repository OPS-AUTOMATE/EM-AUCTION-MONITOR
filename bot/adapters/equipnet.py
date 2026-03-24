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

from dateutil import parser as date_parser
import pytz

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

                # Extract Location (Improved selector for both types)
                location_text = "See Website"
                # Search for label "Location:" in any tag, then get the text after it
                location_elem = await page.query_selector("text=Location:")
                if location_elem:
                    parent = await location_elem.evaluate_handle("el => el.parentElement")
                    if parent:
                        full_loc_text = await parent.inner_text()
                        if "Location:" in full_loc_text:
                            location_text = full_loc_text.split("Location:")[1].strip()

                # Extract Closing Time (Specific for Auction Events)
                closing_time_iso = None
                closing_elem = await page.query_selector("text=Lots Begin Closing:")
                if closing_elem:
                    closing_full_text = await closing_elem.inner_text()
                    # Use regex to be more flexible with whitespace/labels
                    match = re.search(r"Lots Begin Closing:\s*(.*)", closing_full_text, re.I)
                    if match:
                        raw_date_str = match.group(1).strip()
                        if raw_date_str:
                            # Parse EquipNet date (e.g., "March 26, 2026 4:00 PM EST") into standardized UTC
                            try:
                                tz_map = {
                                    "EST": pytz.timezone("America/New_York"),
                                    "EDT": pytz.timezone("America/New_York"),
                                    "BST": pytz.timezone("Europe/London"),
                                    "GMT": pytz.UTC
                                }
                                dt = date_parser.parse(raw_date_str, fuzzy=True)
                                
                                # Detect if string ends with common codes
                                for code, tz in tz_map.items():
                                    if code in raw_date_str:
                                        dt = tz.normalize(tz.localize(dt.replace(tzinfo=None)))
                                        break
                                
                                closing_time_iso = dt.astimezone(pytz.UTC).isoformat()
                            except Exception as e:
                                logger.error("[EquipNet] Failed to parse date %s: %s", raw_date_str, e)
                                # Only set if valid string, otherwise None
                                closing_time_iso = None


                # Extract Price (Primary for Marketplace / Individual Lots)
                price_text = ""
                price_elem = await page.query_selector(".greybox h3, .price h3")
                if price_elem:
                    price_text = await price_elem.inner_text()
                
                # Fallback to general price selectors
                if not price_text:
                    price_elem = await page.query_selector(".price-box, .product-price, .listing-price")
                    if not price_elem:
                        price_elem = await page.query_selector("text=Price") or await page.query_selector("text=Asking Price")
                        if price_elem:
                            parent = await price_elem.query_selector("xpath=..")
                            if parent:
                                price_text = await parent.inner_text()

                current_bid = 0.0
                if price_text:
                    clean_price = price_text.replace(",", "")
                    price_match = re.search(r"([\d]+\.?\d*)", clean_price)
                    if price_match:
                        current_bid = float(price_match.group(1))

                # Status Logic
                content = (await page.content()).lower()
                status = "active"
                if any(x in content for x in ["closed", "ended", "sold"]):
                    status = "expired"

                # Standardized Return
                return {
                    "item_name": item_name,
                    "current_bid": current_bid,
                    "closing_time": closing_time_iso,
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
