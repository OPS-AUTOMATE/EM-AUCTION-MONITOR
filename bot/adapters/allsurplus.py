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
                # Handle Sold Amount first (for closed items), then Current Bid
                bid_text = await get_text("text=Sold Amount")
                if not bid_text:
                    bid_text = await get_text(".bidding-box .price") or await get_text(".asset-current-bid") or await get_text(".sold-amount")
                
                current_bid = 0.0
                if bid_text:
                    # If it's "Sold Amount", we might need to get the actual value from the sibling or parent
                    if "Sold Amount" in bid_text:
                        parent = await page.locator("text=Sold Amount").locator("xpath=..").inner_text()
                        bid_text = parent
                    
                    clean_bid = re.sub(r'[^\d.]', '', bid_text.replace(",", ""))
                    if clean_bid:
                        current_bid = float(clean_bid)

                # 3. Location
                city, state = "Unknown", "Unknown"
                loc_text = await get_text(".location-label + span") or await get_text(".asset-location") or await get_text("text=Location:")
                if loc_text:
                    if "Location:" in loc_text:
                        parent = await page.locator("text=Location:").locator("xpath=..").inner_text()
                        loc_text = parent.split("Location:")[1].strip()
                    
                    parts = loc_text.split(",")
                    if len(parts) >= 2:
                        city, state = parts[0].strip(), parts[1].strip()
                    else:
                        city = loc_text.strip()

                # 4. Closing Time
                closing_time_iso = None
                time_text = await get_text(".time-left") or await get_text(".asset-ends") or await get_text("text=Closed:")
                if not time_text:
                    # Try to find the (Mar 18, 2026 ...) pattern directly
                    page_content = await page.content()
                    time_match = re.search(r"\(([A-Z][a-z]{2}\s\d{1,2},\s\d{4}\s\d{1,2}:\d{2}\s[AP]M\s[A-Z]{2,4})\)", page_content)
                    if time_match:
                        time_text = time_match.group(1)

                if time_text:
                    # Support for dateutil + pytz (Standardized across adapters)
                    from dateutil import parser as date_parser
                    import pytz
                    
                    try:
                        # Extract the part inside parentheses if present
                        inner_match = re.search(r"\((.*?)\)", time_text)
                        date_str = inner_match.group(1) if inner_match else time_text
                        
                        tz_map = {
                            "EST": pytz.timezone("America/New_York"),
                            "EDT": pytz.timezone("America/New_York"),
                            "CST": pytz.timezone("America/Chicago"),
                            "CDT": pytz.timezone("America/Chicago"),
                            "PST": pytz.timezone("America/Los_Angeles"),
                            "PDT": pytz.timezone("America/Los_Angeles"),
                            "BST": pytz.timezone("Europe/London"),
                            "GMT": pytz.UTC
                        }
                        
                        dt = date_parser.parse(date_str, fuzzy=True)
                        for code, tz in tz_map.items():
                            if code in date_str:
                                dt = tz.normalize(tz.localize(dt.replace(tzinfo=None)))
                                break
                        
                        closing_time_iso = dt.astimezone(pytz.UTC).isoformat()
                    except: 
                        logger.error("[AllSurplus] Date parse failed for: %s", time_text)

                # Status Logic: Use word boundaries to avoid matching "closing" or "end times"
                page_content_lower = (await page.content()).lower()
                status = "active"
                if re.search(r"\b(closed|ended|sold|expired)\b", page_content_lower) or "no longer available" in page_content_lower:
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

