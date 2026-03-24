"""
Mazree Adapter Module.
Handles heavy Angular-based auctions with session persistence and authenticated scraping.
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, cast

from playwright.async_api import async_playwright, Error as PlaywrightError
from playwright_stealth import Stealth
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
                logger.info("[Mazree] Loading existing session from: %s", STORAGE_PATH)
                context_args["storage_state"] = STORAGE_PATH
            else:
                logger.warning("[Mazree] No session file found at: %s", STORAGE_PATH)

            context = await browser.new_context(**context_args)
            page = await context.new_page()
            
            # Apply Stealth for bypass
            await Stealth().apply_stealth_async(page)

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
                    
                    # 1. Email Entry
                    email_field = page.locator("#email")
                    await email_field.wait_for(state="visible", timeout=15000)
                    await email_field.click()
                    await email_field.clear()
                    await email_field.type(email, delay=100)
                    await email_field.press("Tab") # Trigger Angular validation
                    await asyncio.sleep(1)
                    
                    # 2. Click Next
                    next_btn = page.locator('button:has-text("Next")')
                    await next_btn.wait_for(state="visible", timeout=10000)
                    
                    if await next_btn.is_disabled():
                        logger.warning("[Mazree] Next button disabled after typing, trying Enter key force...")
                        await email_field.focus()
                        await page.keyboard.press("Enter")
                    else:
                        await next_btn.click()
                    
                    # 3. Password Entry
                    pw_field = page.locator("#password")
                    try:
                        await pw_field.wait_for(state="visible", timeout=10000)
                        logger.info("[Mazree] Entering password...")
                        await pw_field.click()
                        await pw_field.clear()
                        await pw_field.type(pw, delay=100)
                        
                        # 4. Sign In
                        signin_btn = page.locator('button:has-text("Sign In")')
                        await signin_btn.wait_for(state="visible", timeout=10000)
                        await signin_btn.click()
                    except (PlaywrightError, Exception):
                        # Fallback if password field didn't show up
                        logger.warning("[Mazree] Password field transition delayed, checking if logged in or blocked...")
                        if await page.locator("text=Incorrect email").count() > 0:
                            logger.error("[Mazree] Invalid email provided.")
                            return False

                    # 5. Verify Success
                    await page.wait_for_selector('button:has-text("Sign Out"), .app-container', timeout=20000)
                    await context.storage_state(path=STORAGE_PATH)
                    logger.info("[Mazree] Login successful.")
                    return True
                except (PlaywrightError, Exception) as e:
                    logger.info("[Mazree] Login diagnostic: URL=%s", page.url)
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

                # Extraction logic
                async def get_text(sel: str) -> str:
                    try:
                        loc = page.locator(sel).first
                        return (await loc.inner_text()).strip() if await loc.count() > 0 else ""
                    except: return ""

                # Wait for the item title to be visible and not be the login title
                # This prevents "Login to Mazree" from being scraped during transitions
                max_retries = 3
                extracted_item_name = "Unknown Item"
                HOMEPAGE_TAGLINE = "The place to buy and sell used medical equipment."
                
                for attempt in range(max_retries):
                    # Try to wait for the actual item header
                    try:
                        await page.wait_for_selector("h3.text-4xl, h3, h1", timeout=15000)
                    except:
                        pass
                        
                    raw_name = await get_text("h3.text-4xl") or await get_text("h3") or await get_text("h1")
                    extracted_item_name = f"{raw_name or 'Unknown Item'}"
                    
                    # Ensure we are not on the login page or the homepage tagline
                    is_valid_title = (
                        "Login to Mazree" not in extracted_item_name and 
                        HOMEPAGE_TAGLINE not in extracted_item_name and 
                        extracted_item_name != "Unknown Item"
                    )
                    
                    # Also verify the URL pattern
                    is_item_page = "listing-detail" in page.url

                    if is_valid_title and is_item_page:
                        break
                    
                    if attempt < max_retries - 1:
                        logger.info(f"[Mazree] Attempt {attempt+1}: Title='{extracted_item_name[:50]}', URL={page.url}. Retrying navigation...")
                        await page.goto(url, wait_until="networkidle", timeout=60000)
                        await asyncio.sleep(8) # Heavier wait for Angular hydration on server
                
                # Bid/Price Extraction
                price_text = ""
                # Added 'Winning' and 'Final' to support concluded auctions
                price_el = await page.query_selector('xpath=//div[contains(text(), "Price") or contains(text(), "Bid") or contains(text(), "Winning") or contains(text(), "Final")]/following-sibling::div')
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

                # Targeted Status Badge Detection
                status_badge = await page.query_selector("span.badge, .inventory-status-active, .inventory-status-closed")
                if status_badge:
                    badge_text = (await status_badge.inner_text()).upper()
                    if any(x in badge_text for x in ["IN PROGRESS", "ACTIVE", "OPEN"]):
                        status = "active"
                    elif any(x in badge_text for x in ["ENDED", "CLOSED", "SOLD", "EXPIRED"]):
                        status = "expired"

                # Parse time_str to get closing_time and confirm ACTIVE status
                if time_str:
                    try:
                        d, h, m, s = 0, 0, 0, 0
                        if mt := re.search(r'(\d+)\s*D', time_str, re.I): d = int(mt.group(1))
                        if mt := re.search(r'(\d+)\s*H', time_str, re.I): h = int(mt.group(1))
                        if mt := re.search(r'(\d+)\s*M', time_str, re.I): m = int(mt.group(1))
                        if mt := re.search(r'(\d+)\s*S', time_str, re.I): s = int(mt.group(1))
                        
                        total_s = (d * 86400) + (h * 3600) + (m * 60) + s
                        if total_s > 0:
                            closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                            # If there's time remaining, it's definitively ACTIVE
                            status = "active"
                            logger.info("[Mazree] Confirmed ACTIVE status via countdown: %s", time_str)
                    except Exception as e:
                        logger.warning("[Mazree] Could not parse time string '%s': %s", time_str, e)

                return {
                    "item_name": f"{extracted_item_name or 'Unknown Item'}"[:200],
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
