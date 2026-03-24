"""
Troostwijk Adapter Module.
Handles international auctions with localized pricing and complex React-based layouts.
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

class TroostwijkAdapter(BaseAuctionAdapter):
    """
    Hardened Troostwijk Adapter (Tier B - Playwright).
    Manages international currency (Euro) and complex dynamic layouts.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy & Browser Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[Troostwijk] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info("[Troostwijk] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4) # Wait for React hydration

                async def get_text(sel: str, use_xpath: bool = False) -> str:
                    try:
                        loc = page.locator(f"xpath={sel}" if use_xpath else sel).first
                        return (await loc.inner_text()).strip() if await loc.count() > 0 else ""
                    except: return ""

                # 1. Item Name (Complex Selectors)
                item_name = await get_text("#__next h1") or await get_text("//h1", use_xpath=True) or "Unknown Item"
                
                # 2. Location
                location = await get_text("//aside//dd/a", use_xpath=True)
                city, state = "Unknown", "Unknown"
                if location:
                    location = location.strip().rstrip(",")
                    if "," in location:
                        parts = location.split(",")
                        city, state = parts[0].strip(), parts[1].strip()
                    else:
                        city = location

                # 3. Bid Extraction
                current_bid_text = await get_text("//dl/dd[contains(@class, 'flex')]/span", use_xpath=True)
                current_bid = 0.0
                if current_bid_text:
                    clean_bid = current_bid_text.replace("€", "").replace(" ", "").replace(",", ".")
                    clean_bid = re.sub(r'[^\d.]', '', clean_bid)
                    if clean_bid:
                        current_bid = float(clean_bid)

                # 4. Status & Time
                status = "active"
                time_str = await get_text("//div[contains(@class, 'flex')]//div/p", use_xpath=True)
                closing_time_iso = None
                
                content = (await page.content()).lower()
                if any(x in content for x in ["closed", "sold", "ended"]):
                    status = "expired"
                elif time_str:
                    d, h, m, s = 0, 0, 0, 0
                    if mt := re.search(r'(\d+)\s*d', time_str): d = int(mt.group(1))
                    if mt := re.search(r'(\d+)\s*h', time_str): h = int(mt.group(1))
                    if mt := re.search(r'(\d+)\s*m', time_str): m = int(mt.group(1))
                    total_s = (d * 86400) + (h * 3600) + (m * 60)
                    closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "closing_time": closing_time_iso,
                    "time_remaining_str": time_str or "Syncing...",
                    "website_name": "Troostwijk Auctions",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[Troostwijk] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
