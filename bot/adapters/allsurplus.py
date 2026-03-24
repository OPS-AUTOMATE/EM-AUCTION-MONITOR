"""
AllSurplus Adapter Module.
Extracts listing details for government and commercial surplus auctions.
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class AllSurplusAdapter(BaseAuctionAdapter):
    """
    Hardened AllSurplus Adapter (Tier B - Playwright).
    Standardizes extraction for industrial and vehicle auctions.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy & Browser Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[AllSurplus] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info("[AllSurplus] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)

                async def get_text(sel: str) -> str:
                    try:
                        loc = page.locator(sel).first
                        return (await loc.inner_text()).strip() if await loc.count() > 0 else ""
                    except: return ""

                # 1. Item Name
                item_name = await get_text("h1") or "Unknown AllSurplus Item"
                
                # 2. Bid Extraction
                bid_text = await get_text(".bidding-box .price") or await get_text(".asset-current-bid")
                current_bid = 0.0
                if bid_text:
                    clean_bid = re.sub(r'[^\d.]', '', bid_text.replace(",", ""))
                    if clean_bid:
                        current_bid = float(clean_bid)

                # 3. Location (Attempt extraction)
                city, state = "Unknown", "Unknown"
                loc_text = await get_text(".location-label + span") or await get_text(".asset-location")
                if loc_text:
                    parts = loc_text.split(",")
                    if len(parts) >= 2:
                        city, state = parts[0].strip(), parts[1].strip()
                    else:
                        city = loc_text.strip()

                # 4. Closing Time
                closing_time_iso = None
                time_text = await get_text(".time-left") or await get_text(".asset-ends")
                if time_text:
                    date_match = re.search(r"\((.*?)\)", time_text)
                    if date_match:
                        try:
                            clean_date = re.sub(r"\s[A-Z]{3,4}$", "", date_match.group(1))
                            dt = datetime.strptime(clean_date, "%b %d, %Y %I:%M %p")
                            closing_time_iso = dt.isoformat()
                        except: pass

                # 5. Status
                status = "active"
                if any(x in (await page.content()).lower() for x in ["closed", "sold", "ended"]):
                    status = "expired"

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "closing_time": closing_time_iso,
                    "website_name": "AllSurplus",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[AllSurplus] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
