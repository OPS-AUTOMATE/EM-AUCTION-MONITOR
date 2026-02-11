import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GCSurplusAdapter(BaseAuctionAdapter):
    """
    Hardened GC Surplus Adapter (Tier B - Playwright).
    Handles bilingual (EN/FR) state and dynamic pricing.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[GCSurplus] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[GCSurplus] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                # Wait for title to appear
                try:
                    await page.wait_for_selector('h1, #bidPanelId', timeout=15000)
                except:
                    logger.warning("[GCSurplus] Timeout waiting for selectors.")

                await asyncio.sleep(3) # Stabilization

                # Helper to safely get text content
                async def get_text_safe(selector: str, use_xpath: bool = False) -> str:
                   try:
                       loc = page.locator(f"xpath={selector}" if use_xpath else selector)
                       if await loc.count() > 0:
                           return await loc.first.inner_text()
                   except: pass
                   return ""

                # 1. Item Name
                item_name = await get_text_safe("#bidPanelId > section > div > div.col-sp-12.fontSize120.blueBold.bPad10")
                if not item_name:
                    item_name = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/div[1]", use_xpath=True)
                if not item_name:
                    item_name = await get_text_safe("h1")

                # 2. Bid Extraction
                current_bid_text = await get_text_safe("#currentBid")
                if not current_bid_text:
                    current_bid_text = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[1]/span[1]", use_xpath=True)
                
                current_bid = 0.0
                if current_bid_text:
                    try:
                        clean_bid = re.sub(r'[^\d.]', '', current_bid_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                    except: pass

                # 3. Time Remaining
                time_remaining = await get_text_safe("#timeRemaining")
                if not time_remaining:
                    time_remaining = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[3]/span[1]", use_xpath=True)

                # 4. Location
                location = await get_text_safe("#bidPanelId > section > div > dl > dd:nth-child(12)")
                if not location:
                    location = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[6]", use_xpath=True)

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

                # 5. Closing Date
                closing_date = await get_text_safe("#closingDateId")
                if not closing_date:
                    closing_date = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[8]/span", use_xpath=True)

                # Status Check: Hardened
                status = "active"
                content_lower = (await page.content()).lower()
                if "closed" in content_lower or "fermé" in content_lower:
                    status = "expired"
                
                if time_remaining and any(char.isdigit() for char in time_remaining):
                    if "closed" not in time_remaining.lower() and "fermé" not in time_remaining.lower():
                        status = "active"

                # 6. Calculate ISO closing time for active auctions
                closing_time_iso = None
                if status == "active" and time_remaining:
                    try:
                        days, hours, minutes, seconds = 0, 0, 0, 0
                        # Try to handle formats like "3 Days 5 Hours" or "3 Jours 5 Heures"
                        if m := re.search(r'(\d+)\s*(Days?|Jours?)', time_remaining, re.I): days = int(m.group(1))
                        if m := re.search(r'(\d+)\s*(Hours?|Heures?)', time_remaining, re.I): hours = int(m.group(1))
                        if m := re.search(r'(\d+)\s*(Minutes?|Minutes?)', time_remaining, re.I): minutes = int(m.group(1))
                        if m := re.search(r'(\d+)\s*(Seconds?|Secondes?)', time_remaining, re.I): seconds = int(m.group(1))
                        
                        total_s = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
                        if total_s > 0:
                            closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                        
                        # Fallback: Parse absolute closing_date (e.g., February 11, 2026, 3:20 p.m. EST)
                        if not closing_time_iso and closing_date:
                            try:
                                # Clean common noise
                                clean_dt = re.sub(r'\s+', ' ', closing_date).strip()
                                # Simple format match (Month Day, Year, Time)
                                # Handles: "February 11, 2026, 3:20 p.m."
                                m = re.search(r'([a-zA-Z]+)\s+(\d+),\s+(\d{4}),\s+(\d+):(\d+)', clean_dt)
                                if m:
                                    mon_name, day, year, hr, mn = m.groups()
                                    # Month mapping
                                    mon_map = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
                                    mon = mon_map.get(mon_name.lower(), 1)
                                    
                                    # Check for PM
                                    is_pm = "p.m." in clean_dt.lower() or "pm" in clean_dt.lower()
                                    hr_24 = int(hr)
                                    if is_pm and hr_24 < 12: hr_24 += 12
                                    if not is_pm and hr_24 == 12: hr_24 = 0
                                    
                                    dt = datetime(int(year), mon, int(day), hr_24, int(mn), tzinfo=timezone.utc)
                                    closing_time_iso = dt.isoformat()
                            except: pass
                    except: pass
                elif status == "expired":
                    closing_time_iso = datetime.now(timezone.utc).isoformat()

                return {
                    "item_name": item_name.strip()[:200] if item_name else "Unknown Item",
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "closing_time": closing_time_iso,
                    "time_remaining_str": time_remaining.strip() if time_remaining else "",
                    "website_name": "GC Surplus",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[GCSurplus] Error: {e}")
                return None
            finally:
                await browser.close()
