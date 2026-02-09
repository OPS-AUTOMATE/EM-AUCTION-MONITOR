import logging
import re
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class CenturionAdapter(BaseAuctionAdapter):
    """
    Hardened Centurion Adapter (Tier B).
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Prepare Launch Options
            launch_options = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-browser-side-navigation",
                    "--disable-gpu"
                ]
            }

            # GLOBAL PROXY (via BaseAdapter)
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_options["proxy"] = proxy_conf
                server_safe = proxy_conf['server'].split('@')[-1] if '@' in proxy_conf['server'] else proxy_conf['server']
                logger.info(f"[Centurion] Using Proxy: {server_safe}")

            browser = await p.chromium.launch(**launch_options)
            
            # Default values
            item_name = "Unknown Item"
            current_bid = 0.0
            total_bidders = 0
            closing_time_iso = None
            city, state = "Unknown", "Unknown"
            status = "active"
            lot_id = "" # Fix: Initialize early to avoid unbound error
            
            # --- SESSION PERSISTENCE ---
            storage_path = "centurion_session.json"
            context_args = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "has_touch": False,
                "is_mobile": False,
                "java_script_enabled": True,
            }
            
            # Use storage state if it exists
            if os.path.exists(storage_path):
                context_args["storage_state"] = storage_path
                logger.debug("[Centurion] Using saved session state.")

            context = await browser.new_context(**context_args)
            
            # Stealth: Inject script to hide webdriver property
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = await context.new_page()

            # OPTIMIZATION: Block heavy resources to save bandwidth and speed up login
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font"] 
                else route.continue_())

            # Helper for login
            async def perform_login():
                username = os.getenv("CENTURION_USERNAME")
                password = os.getenv("CENTURION_PASSWORD")
                if not username or not password:
                    logger.warning("[Centurion] Login required but credentials missing in .env")
                    return False
                
                logger.info("[Centurion] Attempting login...")
                try:
                    await page.goto("https://bid.centurionservice.com/login", wait_until="domcontentloaded", timeout=60000)
                    
                    # Full XPath for Email input box
                    email_xpath = "/html/body/div[3]/form/div/article/div[2]/section[2]/ul/li[1]/span/input"
                    await page.wait_for_selector(f"xpath={email_xpath}", timeout=20000)
                    await page.fill(f"xpath={email_xpath}", username)
                    
                    # Full XPath for password input box
                    pass_xpath = "/html/body/div[3]/form/div/article/div[2]/section[2]/ul/li[2]/span/input"
                    await page.fill(f"xpath={pass_xpath}", password)
                    
                    # Full XPath for Sign in button
                    submit_xpath = "/html/body/div[3]/form/div/article/div[2]/section[2]/ul/li[3]/div[1]/span[1]/input"
                    await page.locator(f"xpath={submit_xpath}").first.click()
                    
                    await page.wait_for_load_state("networkidle")
                    
                    # Verify login by checking for absence of login button or presence of logout
                    if await page.locator("text='Sign Out'").count() > 0 or await page.locator("text='My Items'").count() > 0:
                        logger.info("[Centurion] Login successful.")
                        await context.storage_state(path=storage_path)
                        return True
                    else:
                        logger.error("[Centurion] Login failed - could not find Post-Login indicators.")
                        return False
                except Exception as e:
                    logger.error(f"[Centurion] Login error: {e}")
                    return False
            
            
            try:
                logger.info(f"[Centurion] Fetching: {url}")
                # USE 'domcontentloaded' + explicit waits instead of 'networkidle' to avoid proxy timeouts
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for at least the body or a key element to ensure we are truly on the page
                try:
                    await page.wait_for_selector("body", timeout=10000)
                except: pass

                # --- LOGIN CHECK ---
                # Use provided XPath for "Sign in to bid" button to detect if login is needed
                signin_xpath = "/html/body/div[3]/form/div/article/section[3]/div[2]/div[2]/div[4]/div/fieldset/ul/li/div/span/input"
                try:
                    # Short wait to see if the sign-in button appears
                    if await page.locator(f"xpath={signin_xpath}").count() > 0:
                        logger.info("[Centurion] Detected 'Sign in to bid' button. Starting login flow.")
                        login_success = await perform_login()
                        if login_success:
                            # Re-navigate to the item page after login
                            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except: pass
                
                # --- STRATEGY 0: Ground Truth JSON (Fastest & Most Reliable) ---
                try:
                    server_data = await page.evaluate("""() => {
                        const script = document.querySelector("script[data-server='server-data-json']");
                        return script ? JSON.parse(script.innerText) : null;
                    }""")
                    
                    if server_data and "default" in server_data:
                        d = server_data["default"]
                        
                        # 1. Price
                        if "currentBid" in d:
                            current_bid = float(d["currentBid"])
                        elif "askingBid" in d: # Fallback if no bids yet
                            current_bid = float(d["askingBid"])
                        
                        # 2. Time
                        if "secondsLeft" in d:
                            seconds_left = float(d["secondsLeft"])
                            if seconds_left > 0:
                                now_utc = datetime.now(timezone.utc)
                                closing_time_iso = (now_utc + timedelta(seconds=seconds_left)).isoformat()
                            else:
                                # Negative means closed
                                status = "expired"
                                logger.info(f"[Centurion] Lot detected as CLOSED (secondsLeft: {seconds_left})")
                        
                        # 3. Lot ID (For Strategy 1)
                        if "auctionLotId" in d:
                            lot_id = str(d["auctionLotId"])
                            logger.info(f"[Centurion] Found internal Lot ID: {lot_id}")

                        logger.info(f"[Centurion] Strategy 0 Success: ${current_bid}")

                except Exception as e:
                    logger.warning(f"[Centurion] Strategy 0 failed: {e}")

                # --- EXTRACTION FALLBACKS (Visual/Dynamic) ---
                # Strategy 0 & 1 rely on JSON. If they fail (common after login), we use visual scraping
                if status == "expired" or not closing_time_iso or current_bid == 0.0:
                    try:
                        # Use inner_text to strip HTML tags for cleaner regex matching
                        plain_text = await page.inner_text("body")
                        
                        # 1. Visual Time Scrape (e.g. "Time left: 21h 5m 21s")
                        if not closing_time_iso or status == "expired":
                            # Use a more flexible regex on clean text
                            time_match = re.search(r'Time\s*left:\s*([\d\s\w]+)', plain_text, re.IGNORECASE)
                            if time_match:
                                time_str = time_match.group(1).strip()
                                logger.info(f"[Centurion DEBUG] Found visual time string: '{time_str}'")
                                
                                days, hours, minutes, seconds = 0, 0, 0, 0
                                if m := re.search(r'(\d+)\s*d', time_str): days = int(m.group(1))
                                if m := re.search(r'(\d+)\s*h', time_str): hours = int(m.group(1))
                                if m := re.search(r'(\d+)\s*m', time_str): minutes = int(m.group(1))
                                if m := re.search(r'(\d+)\s*s', time_str): seconds = int(m.group(1))
                                
                                total_s = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
                                if total_s > 0:
                                    closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                                    status = "active"
                                    logger.info(f"[Centurion] Visual Time Scrape Success: {time_str} -> {total_s}s")
                        
                        # 2. Visual Price Detection (e.g. "Enter $5 or more")
                        if current_bid == 0.0:
                             price_match = re.search(r'Enter\s*\$([\d,.]+)', plain_text, re.IGNORECASE)
                             if price_match:
                                 # This is the starting bid (asking bid)
                                 current_bid = float(price_match.group(1).replace(",", ""))
                                 logger.info(f"[Centurion] Visual Price Detection: Starting at ${current_bid}")

                    except Exception as e:
                        logger.warning(f"[Centurion] Visual Fallback error: {e}")

                # --- TITLE & LOCATION (Always Scrape) ---
                try:
                    # 1. Title (Try Breadcrumb first, then Heading)
                    title_found = False
                    try:
                        breadcrumb_lot = await page.locator(".crumb-lotitem").first.inner_text()
                        if breadcrumb_lot and len(breadcrumb_lot.strip()) > 3: 
                            item_name = breadcrumb_lot.strip()
                            title_found = True
                    except: pass
                    
                    if not title_found:
                        try:
                            h1_title = await page.locator("h1.lot-details-title, h1").first.inner_text()
                            if h1_title: item_name = h1_title.strip()
                        except: pass
                except: pass
                
                try:
                    # 2. Location (City/State Inference from Auction Breadcrumb)
                    auc_name = await page.locator(".crumb-auctions").first.inner_text()
                    if auc_name:
                        # Direct City, State match (e.g. "Chicago, IL" or "Phoenix, AZ")
                        city_state_match = re.search(r'([A-Z][a-z\s]+),\s*([A-Z]{2})', auc_name)
                        if city_state_match:
                            city, state = city_state_match.group(1).strip(), city_state_match.group(2).strip()
                        else:
                            # Keyword matching for known locations if no strict pattern
                            if "Chicago" in auc_name: city, state = "Chicago", "IL"
                            elif "Charlotte" in auc_name: city, state = "Charlotte", "NC"
                            elif "Dallas" in auc_name: city, state = "Dallas", "TX"
                            elif "Phoenix" in auc_name: city, state = "Phoenix", "AZ"
                            elif "Los Angeles" in auc_name: city, state = "Los Angeles", "CA"
                            elif "Miami" in auc_name: city, state = "Miami", "FL"
                except: pass

                # Final Status Safety: If we still don't have a name, something is wrong
                if item_name == "Unknown Item" or not item_name:
                    content = await page.content()
                    if "Page Not Found" in content or "Listing Removed" in content:
                        status = "expired"

                return {
                    "item_name": item_name.strip(),
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": total_bidders,
                    "closing_time": closing_time_iso,
                    "website_name": "Centurion Service",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[Centurion] Critical Error: {e}")
                return None
            finally:
                await browser.close()
