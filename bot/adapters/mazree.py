import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

import os

logger = logging.getLogger(__name__)

storage_path = "mazree_session.json"

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
            
            # SESSION PERSISTENCE
            context_args = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            }
            if os.path.exists(storage_path):
                context_args["storage_state"] = storage_path
                logger.debug("[Mazree] Using saved session state.")

            context = await browser.new_context(**context_args)
            page = await context.new_page()

            # OPTIMIZATION: Block heavy assets but allow stylesheets (safer for SPA)
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font"] 
                else route.continue_())

            # Helper for login
            async def perform_login():
                email = os.getenv("MAZREE_EMAIL")
                password = os.getenv("MAZREE_PASSWORD")
                if not email or not password:
                    logger.warning("[Mazree] Login required but credentials missing in .env (MAZREE_EMAIL/PASSWORD)")
                    return False
                
                logger.info("[Mazree] Attempting login flow...")
                try:
                    await page.goto("https://www.mazree.com/SignIn", wait_until="domcontentloaded", timeout=60000)
                    
                    # 1. Fill Email
                    await page.wait_for_selector("#email", timeout=15000)
                    await page.fill("#email", email)
                    
                    # 2. Click Next
                    await page.click('button:has-text("Next")')
                    
                    # 3. Wait for Password field
                    await page.wait_for_selector('input[type="password"]', timeout=15000)
                    await page.fill('input[type="password"]', password)
                    
                    # 4. Final Click (Sign In)
                    await page.click('button:has-text("Sign In"), button:has-text("Next")')
                    
                    # Wait for redirect
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    
                    # Verify login by checking for "Sign Out"
                    if "Sign Out" in (await page.content()):
                        logger.info("[Mazree] Login successful. Saving session.")
                        await context.storage_state(path=storage_path)
                        return True
                    else:
                        logger.error("[Mazree] Login failed - 'Sign Out' link not found.")
                        return False
                except Exception as e:
                    logger.error(f"[Mazree] Login internal error: {e}")
                    return False

            try:
                logger.info(f"[Mazree] Fetching: {url} (Long Timeout)")
                # 'commit' is safer for sites that might have heavy background tracking
                await page.goto(url, wait_until="commit", timeout=90000)
                
                # Check for redirect to Login
                current_url = page.url
                if "/SignIn" in current_url or "login" in current_url.lower():
                    logger.info(f"[Mazree] Redirected to Login Page! Starting login flow.")
                    if await perform_login():
                        # Re-navigate to the item page after login
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    else:
                        logger.warning("[Mazree] Proceeding without login (content may be restricted).")
                
                # Manual wait for content to appear (Listing detail or at least the app container)
                try:
                    await page.wait_for_selector('h3, .listing-detail, .app-container, body', timeout=60000)
                except:
                    logger.warning("[Mazree] Content selector timeout.")

                await asyncio.sleep(8) # Shortened slightly since we have login verification

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
