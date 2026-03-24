"""
Bidspotter Adapter Module.
Extracts listing details for industrial auctions, handling heavy SPAs and complex date formats.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class BidspotterAdapter(BaseAuctionAdapter):
    """
    Hardened Bidspotter Adapter (Tier B - SSR/SPA).
    Uses multiple fallback strategies for title, price, and location extraction.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[Bidspotter] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # Optimization: Block heavy media
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font"] 
                else route.continue_())
            
            try:
                logger.info("[Bidspotter] Fetching: %s", url)
                await page.goto(url, wait_until="load", timeout=60000)
                await asyncio.sleep(3) # Wait for JS hydration

                async def get_text_safe(selector: str) -> str:
                    try:
                        loc = page.locator(selector).first
                        if await loc.count() > 0:
                            return (await loc.inner_text()).strip()
                    except (PlaywrightError, Exception):
                        pass
                    return ""

                # 1. Title Extraction
                item_name = await get_text_safe("xpath=/html/body/div[1]/main/div/div[1]/div/div[2]/div/h1")
                if not item_name:
                    item_name = await get_text_safe("h1")
                if not item_name:
                    item_name = await get_text_safe(".lot-name, .lot-title, h1.lot-details__title")
                
                item_name = item_name or "Unknown Item"

                # 2. Current Bid / Price
                price_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[1]/span/strong"
                price_text = await get_text_safe(f"xpath={price_xpath}")
                if not price_text:
                    price_text = await get_text_safe(".current-bid, .lot-price, .price-value")
                
                current_bid = 0.0
                if price_text:
                    clean_text = re.sub(r'[^\d.]', '', price_text)
                    if clean_text:
                        current_bid = float(clean_text)

                # 3. Location
                loc_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[2]/div[2]/strong/span"
                loc_text = await get_text_safe(f"xpath={loc_xpath}")
                if not loc_text:
                    loc_text = await get_text_safe(".lot-location, .location-text, address")
                
                city, state = "Unknown", "Unknown"
                if loc_text and "VAT REFUND" not in loc_text.upper():
                    parts = loc_text.split(",")
                    if len(parts) >= 2:
                        city, state = parts[0].strip(), parts[1].strip()
                    else:
                        city = loc_text.strip()

                # 4. Bidders & Premium
                bid_text = await get_text_safe("#lotDetailsBids > span")
                total_bidders = int(re.sub(r'\D', '', bid_text)) if bid_text and re.sub(r'\D', '', bid_text) else 0

                premium_text = await get_text_safe("xpath=/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[4]/div[2]/div[2]/div")
                premium_val = 0.0
                if premium_text:
                    if mt := re.search(r'(\d+(?:\.\d+)?)', premium_text):
                        premium_val = float(mt.group(1))

                # 5. End Time Parsing
                raw_time_str = await get_text_safe("time, .time-remaining, .countdown")
                end_time_iso = None
                if raw_time_str:
                    try:
                        # Attempt countdown parsing
                        d, h, m, s = 0, 0, 0, 0
                        if mt := re.search(r'(\d+)\s*d', raw_time_str, re.I): d = int(mt.group(1))
                        if mt := re.search(r'(\d+)\s*h', raw_time_str, re.I): h = int(mt.group(1))
                        if mt := re.search(r'(\d+)\s*m', raw_time_str, re.I): m = int(mt.group(1))
                        if mt := re.search(r'(\d+)\s*s', raw_time_str, re.I): s = int(mt.group(1))
                        total_s = (d * 86400) + (h * 3600) + (m * 60) + s
                        if total_s > 0:
                            end_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                    except ValueError:
                        pass

                # 6. Status Check
                status = "active"
                area_text = (await get_text_safe(".lot-details__bidding, .bidding-container")).lower()
                if any(x in area_text for x in ["lot closed", "sold for", "bidding has ended"]):
                    status = "expired"

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "premium_percentage": premium_val,
                    "total_bidders": total_bidders,
                    "closing_time": end_time_iso,
                    "time_remaining_str": raw_time_str or "Syncing...",
                    "website_name": "BidSpotter",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[Bidspotter] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
