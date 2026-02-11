import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class MazreeAdapter(BaseAuctionAdapter):
    """
    Hardened Mazree Adapter (Tier B - Playwright).
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[Mazree] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[Mazree] Fetching: {url}")
                await page.goto(url, wait_until="networkidle", timeout=45000)
                
                # Wait for main content or title
                try:
                    await page.wait_for_selector('h3, app-buyer-listing-detail, app-guest-listing-detail', timeout=30000)
                except:
                    logger.warning("[Mazree] Timeout waiting for content.")

                await asyncio.sleep(5) # Stabilization

                # Helper to safely get text content
                async def get_text_safe(selector: str, use_xpath: bool = False) -> str:
                   try:
                       loc = page.locator(f"xpath={selector}" if use_xpath else selector)
                       if await loc.count() > 0:
                           return await loc.first.inner_text()
                   except: pass
                   return ""

                # 1. Item Name
                item_name = await get_text_safe("#child-of-buyer-center-section > div.flex.flex-col.align-items-center\\.\\.text-surface-800.dark\\:text-surface-50.gap-3.ng-tns-c700949049-12 > h3")
                if not item_name:
                    item_name = await get_text_safe("/html/body/app-root/div/div/app-user-layout/div/div/div/div/div[2]/div/app-buyer-listing-detail/div/main/section[2]/div/div[1]/h3", use_xpath=True)
                if not item_name:
                    item_name = await get_text_safe("#child-of-buyer-center-section h3")

                # 2. Price
                price_text = await get_text_safe("#child-of-buyer-center-section > div.flex.flex-wrap.sm\\:items-center.justify-between.gap-4.sm\\:gap-0.pb-6.border-b.border-surface-200.dark\\:border-surface-600.font-poppins-regular.leading-none.ng-tns-c700949049-12 > div:nth-child(1) > div.flex.flex-col.gap-1.ml-5\\..ng-tns-c700949049-12.ng-star-inserted > h3")
                if not price_text:
                    price_text = await get_text_safe("/html/body/app-root/div/div/app-user-layout/div/div/div/div/div[2]/div/app-buyer-listing-detail/div/main/section[2]/div/div[3]/div[1]/div[2]/h3", use_xpath=True)
                
                if not price_text or "$" not in price_text:
                    h3s = await page.locator("h3").all()
                    for h3 in h3s:
                        text = await h3.inner_text()
                        if "$" in text:
                            price_text = text
                            break
                
                current_bid = 0.0
                if price_text:
                    try:
                        clean_bid = re.sub(r'[^\d.]', '', price_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                    except: pass

                # 3. Location (Improved to handle 'Pick From')
                location = "Unknown"
                try:
                    # Try specific labels first
                    labels = ["Location", "Pick From", "Item Location"]
                    for label in labels:
                        loc_el = page.locator(f"span:has-text('{label}') + span").first
                        if await loc_el.count() > 0:
                            possible_loc = await loc_el.inner_text()
                            if possible_loc and "Parts" not in possible_loc and "Working" not in possible_loc:
                                location = possible_loc
                                break
                    
                    if location == "Unknown":
                        # Fallback to broad cards
                        location = await get_text_safe("#description-parent-div > div > div > div > div:nth-child(1) > span:nth-child(2)")
                    
                    # Sanity check: If location contains "Parts", it's probably wrong
                    if location and ("Parts" in location or "Working" in location):
                        location = "Unknown"
                except: pass
                
                if not location or location == "Unknown":
                    # Try to find "City, ST" pattern in the whole page
                    page_text = (await page.inner_text("body"))
                    loc_match = re.search(r"\b([A-Z][a-z]+,\s*[A-Z]{2})\b", page_text)
                    if loc_match:
                        location = loc_match.group(1).strip()

                # Clean location
                city, state = "Unknown", ""
                if location and location != "Unknown":
                    # Remove trailing punctuation
                    location = location.strip().rstrip(",.")
                    # Remove country if present
                    location = re.sub(r",?\s*(United States|USA)$", "", location, flags=re.I).strip().rstrip(",")
                    
                    if "," in location:
                        parts = location.split(",")
                        city = parts[0].strip()
                        state = parts[1].strip()
                    else:
                        city = location

                # 4. Time Remaining (Smart Parse)
                time_remaining = await get_text_safe("#child-of-buyer-center-section > div.flex.flex-wrap.items-center.justify-between.gap-2.md\\:gap-0.pb-6.border-b.border-surface-200.dark\\:border-surface-600.font-poppins-regular.ng-tns-c700949049-12.ng-star-inserted > span.font-poppins-regular.ng-tns-c700949049-12")
                if not time_remaining:
                    time_remaining = await get_text_safe("/html/body/app-root/div/div/app-guest-layout/div/div/main/app-guest-listing-detail/div/main/section[2]/div/div[2]/span[2]", use_xpath=True)
                if not time_remaining:
                    time_remaining = await get_text_safe("/html/body/app-root/div/div/app-user-layout/div/div/div/div/div[2]/div/app-buyer-listing-detail/div/main/section[2]/div/div[2]/span[2]", use_xpath=True)

                # Status Check: Hardened
                status = "active"
                content_lower = (await page.content()).lower()
                
                if "closed" in content_lower or "sold" in content_lower or "ended" in content_lower:
                    status = "expired"

                # If we have any parsed time, it MUST be active
                if time_remaining and any(char.isdigit() for char in time_remaining):
                    if "ended" not in time_remaining.lower():
                        status = "active"

                # 5. Handle "Ends In" format for closing_time calculation
                closing_time_iso = None
                if time_remaining and status == "active":
                    try:
                        # Format: "3 Days : 17 Hours : 51 Minutes : 55 Seconds"
                        days, hours, minutes, seconds = 0, 0, 0, 0
                        if m := re.search(r'(\d+)\s*Days?', time_remaining, re.I): days = int(m.group(1))
                        if m := re.search(r'(\d+)\s*Hours?', time_remaining, re.I): hours = int(m.group(1))
                        if m := re.search(r'(\d+)\s*Minutes?', time_remaining, re.I): minutes = int(m.group(1))
                        if m := re.search(r'(\d+)\s*Seconds?', time_remaining, re.I): seconds = int(m.group(1))
                        
                        total_s = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
                        if total_s > 0:
                            closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                    except: pass
                
                # If expired, set closing time to now to stop any residual timers
                if status == "expired":
                    closing_time_iso = datetime.now(timezone.utc).isoformat()

                return {
                    "item_name": item_name.strip()[:200] if item_name else "Unknown Item",
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "closing_time": closing_time_iso,
                    "time_remaining_str": time_remaining.strip() if time_remaining else "",
                    "website_name": "Mazree",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[Mazree] Error: {e}")
                return None
            finally:
                await browser.close()
