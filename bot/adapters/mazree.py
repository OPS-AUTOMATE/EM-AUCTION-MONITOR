"""
Mazree Adapter Module.
Handles heavy Angular-based auctions with session persistence and authenticated scraping.
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

# SESSION PERSISTENCE
SESSION_DIR = os.path.join(os.path.dirname(__file__), "..", ".sessions")
os.makedirs(SESSION_DIR, exist_ok=True)
STORAGE_PATH = os.path.join(SESSION_DIR, "mazree_session.json")

class MazreeAdapter(BaseAuctionAdapter):
    """
    Hardened Mazree Adapter (Tier B - Playwright).
    Maintains session state and handles Angular-specific hydration delays.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy & Browser Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[Mazree] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            
            context_args = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            }
            if os.path.exists(STORAGE_PATH):
                context_args["storage_state"] = STORAGE_PATH

            context = await browser.new_context(**context_args)
            page = await context.new_page()

            # Optimization: Block heavy media
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font"] 
                else route.continue_())

            async def perform_login():
                email = os.getenv("MAZREE_EMAIL", "").strip()
                pw = os.getenv("MAZREE_PASSWORD", "").strip()
                
                if not email or not pw:
                    logger.error("[Mazree] Missing credentials for login.")
                    return False
                
                try:
                    logger.info("[Mazree] Attempting login flow with: %s", email)
                    await page.goto("https://www.mazree.com/SignIn", wait_until="networkidle")
                    
                    email_field = page.locator("#email")
                    await email_field.wait_for(state="visible", timeout=15000)
                    
                    # Human-like typing
                    await email_field.click()
                    await email_field.clear()
                    await email_field.type(email, delay=100)
                    
                    # Trigger validation by tabbing or blurring
                    await email_field.press("Tab")
                    await asyncio.sleep(2)
                    
                    next_btn = page.locator('button:has-text("Next"), button[label="Next"]')
                    await next_btn.wait_for(state="visible", timeout=10000)

                    # Check if disabled and try to force if needed
                    is_disabled = await next_btn.get_attribute("disabled") is not None
                    if is_disabled:
                        logger.warning("[Mazree] Next button disabled after typing, attempting Enter key press...")
                        await email_field.focus()
                        await page.keyboard.press("Enter")
                    else:
                        await next_btn.click()
                    
                    # Wait for password field
                    try:
                        pw_field = page.locator('input[type="password"]')
                        await pw_field.wait_for(state="visible", timeout=15000)
                        logger.info("[Mazree] Email accepted, entering password...")
                        await pw_field.fill(pw)
                        await pw_field.press("Enter")
                    except (PlaywrightError, Exception):
                        # Maybe we are already on password page or it failed
                        if await page.locator("text=Incorrect email or password").count() > 0:
                            logger.error("[Mazree] Login validation failed (email likely invalid)")
                            return False
                        # Try one more click on next if still on email page
                        if await next_btn.is_visible():
                            await next_btn.click(force=True)
                            await asyncio.sleep(2)
                            pw_field = page.locator('input[type="password"]')
                            if await pw_field.count() > 0:
                                await pw_field.fill(pw)
                                await pw_field.press("Enter")

                    await page.wait_for_selector('button:has-text("Sign Out"), .app-container', timeout=20000)
                    await context.storage_state(path=STORAGE_PATH)
                    logger.info("[Mazree] Login successful.")
                    return True
                except (PlaywrightError, Exception) as e:
                    logger.error("[Mazree] Login failed during flow: %s", e)
                return False

            try:
                logger.info("[Mazree] Fetching: %s", url)
                await page.goto(url, wait_until="commit", timeout=60000)
                await asyncio.sleep(5) # Wait for Angular hydration

                # Check if we need to log in
                is_logged_in = await page.locator('button:has-text("Sign Out")').count() > 0
                if not is_logged_in and ("/SignIn" in page.url or await page.locator("#email").count() > 0):
                    if await perform_login():
                        await page.goto(url, wait_until="commit")
                        await asyncio.sleep(5)

                # Extraction logic (rest of the code)
                async def get_text(sel: str) -> str:
                    try:
                        loc = page.locator(sel).first
                        return (await loc.inner_text()).strip() if await loc.count() > 0 else ""
                    except: return ""

                # Item Name extraction
                raw_name = await get_text("h3.text-4xl") or await get_text("h3") or await get_text("h1")
                extracted_item_name: str = str(raw_name or "Unknown Item")
                
                # Bid/Price Extraction
                price_text = ""
                price_el = await page.query_selector('xpath=//div[contains(text(), "Price") or contains(text(), "Bid")]/following-sibling::div')
                if price_el:
                    price_text = await price_el.inner_text()
                else:
                    h3s = await page.locator("h3").all()
                    for h3 in h3s:
                        text = await h3.inner_text()
                        if "$" in text:
                            price_text = text
                            break
                
                current_bid = float(re.sub(r'[^\d.]', '', price_text)) if price_text and re.sub(r'[^\d.]', '', price_text) else 0.0

                # Bidders Count
                total_bidders = 0
                bids_el = await page.query_selector('xpath=//span[contains(text(), "BID")]')
                if bids_el:
                    bids_text = await bids_el.inner_text()
                    if match := re.search(r'(\d+)', bids_text):
                        total_bidders = int(match.group(1))

                # Location (City, State)
                city, state = "Unknown", "Unknown"
                pick_from = page.locator("span:has-text('Pick From') + span, div:has-text('Pick From') + div")
                if await pick_from.count() > 0:
                    raw_loc = await pick_from.first.inner_text()
                    match = re.search(r"([^,]+),\s*([A-Z]{2}|[a-zA-Z]+)", raw_loc)
                    if match:
                        city, state = match.group(1).strip(), match.group(2).strip()
                
                if city == "Unknown":
                    loc_el = await page.query_selector('xpath=//div[contains(text(), "Pick From")]/following-sibling::div')
                    if loc_el:
                        raw_loc = await loc_el.inner_text()
                        match = re.search(r"([^,]+),\s*([A-Z]{2}|[a-zA-Z]+)", raw_loc)
                        if match:
                            city, state = match.group(1).strip(), match.group(2).strip()

                # Status & Time
                status = "active"
                time_str = await get_text("i.fa-clock + *") or await get_text("span:has-text('Ends In') + span")
                closing_time_iso = None
                
                page_content_lower = (await page.content()).lower()
                if re.search(r'\b(closed|sold|ended|expired)\b', page_content_lower):
                    status = "expired"

                elif time_str:
                    d, h, m, s = 0, 0, 0, 0
                    if mt := re.search(r'(\d+)\s*D', time_str, re.I): d = int(mt.group(1))
                    if mt := re.search(r'(\d+)\s*H', time_str, re.I): h = int(mt.group(1))
                    if mt := re.search(r'(\d+)\s*M', time_str, re.I): m = int(mt.group(1))
                    total_s = (d * 86400) + (h * 3600) + (m * 60)
                    closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()

                return {
                    "item_name": extracted_item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": total_bidders,
                    "closing_time": closing_time_iso,
                    "time_remaining_str": time_str or "Syncing...",
                    "website_name": "Mazree",
                    "status": status
                }




            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[Mazree] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
