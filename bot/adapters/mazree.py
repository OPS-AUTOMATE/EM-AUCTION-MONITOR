import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

import os

logger = logging.getLogger(__name__)

# SESSION PERSISTENCE
SESSION_DIR = os.path.join(os.path.dirname(__file__), "..", ".sessions")
os.makedirs(SESSION_DIR, exist_ok=True)
storage_path = os.path.join(SESSION_DIR, "mazree_session.json")

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
                    await page.goto("https://www.mazree.com/SignIn", wait_until="commit", timeout=60000)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=20000)
                    except: pass
                    await asyncio.sleep(2)
                    
                    # 1. Fill Email
                    await page.wait_for_selector("#email", timeout=15000)
                    await page.fill("#email", email)
                    await asyncio.sleep(1)
                    
                    # 2. Click Next
                    next_btn = page.locator('button:has-text("Next")')
                    await next_btn.wait_for(state="visible", timeout=15000)
                    # Angular enablement check
                    for _ in range(10):
                        if await next_btn.is_enabled(): break
                        await asyncio.sleep(0.5)
                    await next_btn.click()
                    
                    # 3. Wait for Password field
                    pw_field = page.locator('input[type="password"]')
                    await pw_field.wait_for(state="visible", timeout=15000)
                    await pw_field.fill(password)
                    await asyncio.sleep(1)
                    
                    # 4. Final Submission (Enter is more reliable for triggering Angular form submission)
                    await pw_field.press("Enter")
                    
                    # Wait for redirect or success markers
                    try:
                        # Success markers: User menu, "Sign Out", or dashboard app-container
                        await page.wait_for_selector('button:has-text("Sign Out"), .app-container, .listing-detail', timeout=20000)
                        logger.info(f"[Mazree] Login successful. Current URL: {page.url}")
                        await context.storage_state(path=storage_path)
                        return True
                    except:
                        # Fallback: check if the "Sign In" button is still there
                        logger.warning("[Mazree] Post-login marker timeout, checking current state.")
                        if "/SignIn" in page.url:
                            # Try explicit button click as last resort
                            signin_btn = page.locator('button:has-text("Sign In"), button:has-text("Next")').first
                            if await signin_btn.is_visible() and await signin_btn.is_enabled():
                                await signin_btn.click(force=True)
                                await asyncio.sleep(5)
                        
                        content = await page.content()
                        if "Sign Out" in content or ".app-container" in content:
                            logger.info("[Mazree] Login successful (detected via content).")
                            await context.storage_state(path=storage_path)
                            return True
                        
                        logger.error(f"[Mazree] Login failed. URL: {page.url}")
                        return False

                except Exception as e:
                    logger.error(f"[Mazree] Login internal error: {e}")
                    return False

            try:
                logger.info(f"[Mazree] Fetching: {url}")
                await page.goto(url, wait_until="commit", timeout=60000)
                
                # Check for login redirection or presence of login fields early
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                except:
                    logger.debug("[Mazree] domcontentloaded timeout, continuing to check content...")

                if "/SignIn" in page.url or await page.locator("#email").count() > 0:
                    logger.info("[Mazree] Login required for this listing.")
                    if await perform_login():
                        logger.info(f"[Mazree] Login success, re-navigating to: {url}")
                        await page.goto(url, wait_until="commit", timeout=60000)
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=20000)
                        except: pass
                        await asyncio.sleep(5)
                
                # Final wait for listing content
                try:
                    await page.wait_for_selector("h3, .listing-detail", timeout=20000)
                except:
                    logger.warning("[Mazree] Listing content not found within timeout.")

                await asyncio.sleep(10) # Heavy Angular wait for dynamic prices/timers

                # Extraction logic
                content = await page.content()
                
                # 1. Item Name
                item_name = "Unknown Item"
                h3s = await page.locator("h3").all()
                for h3 in h3s:
                    cls = await h3.get_attribute("class") or ""
                    if "text-4xl" in cls: # Pattern from debug
                        item_name = (await h3.inner_text()).strip()
                        break
                if item_name == "Unknown Item" and h3s:
                    # Fallback to the first H3 that isn't a price
                    for h3 in h3s:
                        text = (await h3.inner_text()).strip()
                        if text and "$" not in text and "mazree" not in text.lower():
                            item_name = text
                            break

                # 2. Current Bid
                current_bid = 0.0
                price_text = ""
                for h3 in h3s:
                    text = (await h3.inner_text()).strip()
                    if "$" in text:
                        price_text = text
                        break
                if price_text:
                    try:
                        clean_bid = re.sub(r'[^\d.]', '', price_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                    except: pass

                # 3. Location (City, State)
                location_text = ""
                try:
                    # Search for the span containing "Pick From" and get the next sibling text
                    pick_from = page.locator("span:has-text('Pick From') + span")
                    if await pick_from.count() > 0:
                        raw_html = await pick_from.first.inner_html()
                        location_text = raw_html.replace("<br>", "\n").replace("<br/>", "\n").replace("<BR>", "\n")
                        # Strip any other remaining tags
                        location_text = re.sub(r"<[^>]+>", "", location_text).strip()
                except: pass

                city, state = "Unknown", ""
                if location_text:
                    # Parse "West Valley City, Utah, United States\n84120"
                    lines = [l.strip() for l in location_text.split("\n") if l.strip()]
                    target_line = lines[0]
                    if len(lines) > 1:
                        # If first line looks like a street address (e.g., contains numbers), skip to the next
                        if any(c.isdigit() for c in lines[0]) and "," not in lines[0]:
                            target_line = lines[1]
                    
                    # Remove country
                    target_line = re.sub(r",?\s*(United States|USA)$", "", target_line, flags=re.I).strip()
                    
                    # Look for City, State pattern
                    match = re.search(r"([^,]+),\s*([^,]+?)(?:,\s*|$)", target_line)
                    if match:
                        city = match.group(1).strip()
                        state = match.group(2).strip()
                    else:
                        city = target_line

                # 4. Seller (Internal extraction without saving to DB yet)
                try:
                    seller_el = page.locator("a.font-poppins-medium.text-lg").first
                    if await seller_el.count() > 0:
                        _ = (await seller_el.inner_text()).strip()
                except: pass

                # 5. Time Remaining / Closing Time
                time_remaining_str = ""
                closing_time_iso = None
                try:
                    timer_el = page.locator("i.fa-clock + *")
                    if await timer_el.count() > 0:
                        time_remaining_str = (await timer_el.first.inner_text()).strip()
                    else:
                        ends_in = page.locator("span:has-text('Ends In') + span")
                        if await ends_in.count() > 0:
                            time_remaining_str = (await ends_in.first.inner_text()).strip()
                except: pass

                status = "active"
                
                # Check for explicit status badge (high priority)
                try:
                    status_badge = page.locator("p-tag span.p-tag-label")
                    if await status_badge.count() > 0:
                        badge_text = (await status_badge.first.inner_text()).lower()
                        if any(x in badge_text for x in ["closed", "sold", "ended", "expired"]):
                            status = "expired"
                except: pass

                if status == "active" and ("closed" in content.lower() or "sold" in content.lower() or "ended" in content.lower()):
                    status = "expired"

                if time_remaining_str and any(char.isdigit() for char in time_remaining_str):
                    if "ended" not in time_remaining_str.lower():
                        status = "active"
                        try:
                            d, h, m, s = 0, 0, 0, 0
                            if "Day" in time_remaining_str: d = int(re.search(r'(\d+)\s*Day', time_remaining_str, re.I).group(1))
                            if "Hour" in time_remaining_str: h = int(re.search(r'(\d+)\s*Hour', time_remaining_str, re.I).group(1))
                            if "Minute" in time_remaining_str: m = int(re.search(r'(\d+)\s*Minute', time_remaining_str, re.I).group(1))
                            if "Second" in time_remaining_str: s = int(re.search(r'(\d+)\s*Second', time_remaining_str, re.I).group(1))
                            
                            total_s = (d * 86400) + (h * 3600) + (m * 60) + s
                            if total_s > 0:
                                closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                        except: pass

                if status == "expired":
                    closing_time_iso = datetime.now(timezone.utc).isoformat()

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "closing_time": closing_time_iso,
                    "time_remaining_str": time_remaining_str,
                    "website_name": "Mazree",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[Mazree] Error: {e}")
                return None
            finally:
                await browser.close()
