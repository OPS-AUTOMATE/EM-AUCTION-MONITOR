import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class DirectBidsAdapter(BaseAuctionAdapter):
    """
    Hardened Direct Bids Adapter (Tier B - Playwright).
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[DirectBids] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[DirectBids] Fetching: {url}")
                await page.goto(url, wait_until="commit", timeout=60000)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)
                except:
                    logger.debug("[DirectBids] domcontentloaded timeout, continuing...")
                
                # Wait for main content to load
                try:
                    await page.wait_for_selector('h4, #item-main', timeout=15000)
                except:
                    logger.warning("[DirectBids] Timeout waiting for selectors.")

                await asyncio.sleep(2) # Stabilization

                # Helper to safely get text content
                async def get_text_safe(selector: str, use_xpath: bool = False) -> str:
                   try:
                       loc = page.locator(f"xpath={selector}" if use_xpath else selector)
                       if await loc.count() > 0:
                           return await loc.first.inner_text()
                   except: pass
                   return ""

                # 1. Item Name
                item_name = await get_text_safe("#item-main > div.row.gx-3.mb-3 > div > h4")
                if not item_name:
                    item_name = await get_text_safe("/html/body/div[2]/main/div[1]/div[2]/div/div[1]/div/h4", use_xpath=True)
                
                # 2. Location
                location = await get_text_safe("#item-main > div:nth-child(2) > div:nth-child(2) > div.col > div > div.col-auto > div:nth-child(1)")
                if not location:
                    location = await get_text_safe("/html/body/div[2]/main/div[1]/div[2]/div/div[2]/div[2]/div[1]/div/div[1]/div[1]", use_xpath=True)

                city, state = "Unknown", ""
                if location:
                    # Clean trailing commas
                    location = location.strip().rstrip(",")
                    if "," in location:
                        parts = location.split(",")
                        city = parts[0].strip()
                        state = parts[1].strip()
                    else:
                        city = location

                # 3. Time Left & Ends On
                time_left = await get_text_safe("/html/body/div[2]/main/div[1]/div[2]/div/div[3]/div[1]", use_xpath=True)
                ends_on = await get_text_safe("/html/body/div[2]/main/div[1]/div[2]/div/div[3]/div[2]/em", use_xpath=True)

                # 4. Bid Extraction
                current_bid_text = await get_text_safe("/html/body/div[2]/main/div[1]/div[2]/div/div[4]/div/span[1]/strong", use_xpath=True)
                current_bid = 0.0
                if current_bid_text:
                    try:
                        clean_bid = re.sub(r'[^\d.]', '', current_bid_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                    except: pass

                # 5. No. of Bids
                bid_count_text = await get_text_safe("#current-bid > span.align-middle.ms-3 > span")
                if not bid_count_text:
                    bid_count_text = await get_text_safe("/html/body/div[2]/main/div[1]/div[2]/div/div[4]/div/span[2]/span", use_xpath=True)

                # Status Check: Hardened
                status = "active"
                if not item_name or item_name == "Unknown Item":
                     content_lower = (await page.content()).lower()
                     if "closed" in content_lower or "sold" in content_lower:
                         status = "expired"
                
                # If we have time left or an end date, it's active
                if (time_left and any(char.isdigit() for char in time_left)) or (ends_on and len(ends_on) > 5):
                    if "closed" not in time_left.lower() and "sold" not in time_left.lower():
                        status = "active"

                # 6. Calculate ISO closing time for active auctions
                closing_time_iso = None
                if status == "active" and time_left:
                    try:
                        days, hours, minutes, seconds = 0, 0, 0, 0
                        if m := re.search(r'(\d+)\s*Days?', time_left, re.I): days = int(m.group(1))
                        if m := re.search(r'(\d+)\s*Hours?', time_left, re.I): hours = int(m.group(1))
                        if m := re.search(r'(\d+)\s*Minutes?', time_left, re.I): minutes = int(m.group(1))
                        if m := re.search(r'(\d+)\s*Seconds?', time_left, re.I): seconds = int(m.group(1))
                        
                        total_s = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
                        if total_s > 0:
                            closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                    except: pass
                elif status == "expired":
                    closing_time_iso = datetime.now(timezone.utc).isoformat()

                return {
                    "item_name": item_name.strip()[:200] if item_name else "Unknown Item",
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": int(re.sub(r'\D', '', bid_count_text)) if bid_count_text and re.sub(r'\D', '', bid_count_text) else 0,
                    "time_remaining_str": time_left.strip() if time_left else "",
                    "closing_time": closing_time_iso,
                    "website_name": "Direct Bids",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[DirectBids] Error: {e}")
                return None
            finally:
                await browser.close()
