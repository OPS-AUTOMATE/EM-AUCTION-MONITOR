import logging
import re
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter
from utils.browser import launch_browser

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
            }

            # GLOBAL PROXY (via BaseAdapter)
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_options["proxy"] = proxy_conf
                server_safe = proxy_conf['server'].split('@')[-1] if '@' in proxy_conf['server'] else proxy_conf['server']
                logger.info(f"[Centurion] Using Proxy: {server_safe}")

            browser = await launch_browser(p, **launch_options)
            
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
                
                # --- WAIT FOR DYNAMIC CONTENT ---
                # Centurion spans for price, time, and status often load via JS after the main DOM.
                await page.wait_for_timeout(3500)

                # --- EXPIRATION CHECK ---
                try:
                    # User provided selector for Lot Closed message
                    expired_selector = "#LotDetailsTimed > div > article > section.auc_show > div.auc_info.right > div.auc_info_bid > div:nth-child(4) > div > div"
                    expired_elem = page.locator(expired_selector).first
                    body_content = await page.content()
                    
                    if await expired_elem.count() > 0:
                        txt = await expired_elem.inner_text()
                        if "lot closed" in txt.lower():
                            status = "expired"
                            logger.info("[Centurion] Detected 'Lot Closed' via selector.")
                    
                    # Broad fallback for expiration keywords anywhere in the page
                    if status != "expired":
                        for indicator in ["lot closed", "sale has ended", "bidding has closed"]:
                            if indicator in body_content.lower():
                                status = "expired"
                                logger.info(f"[Centurion] Detected '{indicator}' via page content.")
                                break
                except: pass

                # --- STRATEGY 0: Ground Truth JSON ---
                try:
                    server_data = await page.evaluate("""() => {
                        const script = document.querySelector("script[data-server='server-data-json']");
                        return script ? JSON.parse(script.innerText) : null;
                    }""")
                    
                    if server_data and "default" in server_data:
                        d = server_data["default"]
                        if "currentBid" in d: current_bid = float(d["currentBid"])
                        elif "askingBid" in d: current_bid = float(d["askingBid"])
                        
                        # --- JSON LOCATION CHECK ---
                        if "location" in d and d["location"]:
                            m = re.search(r'\b([A-Z][A-Za-z\s]{2,20}),\s*([A-Z]{2}|[A-Z][a-z])\b', str(d["location"]))
                            if m:
                                c, s = m.group(1).strip(), m.group(2).strip()
                                valid_states = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
                                blacklist = ["Group", "LLC", "Ltd", "Inc", "Service", "MTIH"]
                                
                                if s.upper() in valid_states and c not in blacklist:
                                    city, state = c, s
                                    logger.info(f"[Centurion] Location found in JSON: {city}, {state}")

                        if "secondsLeft" in d:
                            seconds_left = float(d["secondsLeft"])
                            if seconds_left <= 0:
                                status = "expired"
                            elif not closing_time_iso and status != "expired":
                                now_utc = datetime.now(timezone.utc)
                                closing_time_iso = (now_utc + timedelta(seconds=seconds_left)).isoformat()
                except Exception as e:
                    logger.debug(f"[Centurion] JSON Strategy error: {e}")

                # 1. Title
                try:
                    title_selector = "#LotDetailsTimed > div > article > section.auctitle.auc_dtl_title.auc_mob_dis > div.tle.aucdttle > h1 > span"
                    title_elem = page.locator(title_selector).first
                    if await title_elem.count() > 0:
                        txt = await title_elem.inner_text()
                        if txt and len(txt.strip()) > 2:
                            item_name = txt.strip()
                            logger.info(f"[Centurion] Title extract Success: {item_name}")
                except: pass

                # 2. Current Bid
                try:
                    bid_selector = "#currentBid > span.exratetip.exratetip-current-bid"
                    bid_xpath = "xpath=/html/body/div[3]/form/div/article/section[3]/div[2]/div[2]/div[1]/div/span[2]"
                    bid_elem = page.locator(bid_selector).first
                    if await bid_elem.count() == 0:
                        bid_elem = page.locator(bid_xpath).first
                    
                    if await bid_elem.count() > 0:
                        bid_text = await bid_elem.inner_text()
                        price_match = re.search(r'[\d,.]+', bid_text)
                        if price_match:
                            current_bid = float(price_match.group(0).replace(",", ""))
                            logger.info(f"[Centurion] Bid extract Success: ${current_bid}")
                except: pass

                # 3. Timestamp / Closing Time Calculation
                try:
                    time_sel = "span.time-left"
                    time_xpath = "xpath=/html/body/div[3]/form/div/article/section[3]/div[2]/div[2]/div[1]/span"
                    time_elem = page.locator(time_sel).first
                    if await time_elem.count() == 0:
                        time_elem = page.locator(time_xpath).first
                    
                    if await time_elem.count() > 0:
                        time_text = (await time_elem.inner_text()).lower()
                        if "time left" in time_text:
                            # Standardize parsing across all adapters
                            days, hours, minutes, seconds = 0, 0, 0, 0
                            if m := re.search(r'(\d+)\s*d', time_text, re.I): days = int(m.group(1))
                            if m := re.search(r'(\d+)\s*h', time_text, re.I): hours = int(m.group(1))
                            if m := re.search(r'(\d+)\s*m', time_text, re.I): minutes = int(m.group(1))
                            if m := re.search(r'(\d+)\s*s', time_text, re.I): seconds = int(m.group(1))
                            
                            # Fallback for full words
                            if not days and (m := re.search(r'(\d+)\s*Days?', time_text, re.I)): days = int(m.group(1))
                            if not hours and (m := re.search(r'(\d+)\s*Hours?', time_text, re.I)): hours = int(m.group(1))
                            
                            total_s = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
                            if total_s > 0:
                                closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                                status = "active"
                except: pass

                # 4. Bidders (Forced 0 per user)
                total_bidders = 0

                # --- AGGRESSIVE LOCATION SEARCH ---
                if city == "Unknown":
                    try:
                        valid_states = {"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
                        loc_pattern = r'\b([A-Z][A-Za-z\s]{2,20}),\s*([A-Z]{2}|[A-Z][a-z])\b'
                        blacklist = ["Group", "LLC", "Ltd", "Inc", "Service", "MTIH", "Additionally", "Moreover", "However", "Note"]

                        # Priority A: Breadcrumbs
                        for sel in [".crumb-auctions", ".crumb-lotitem", ".crumb-home", ".breadcrumb", "h1"]:
                            elems = await page.locator(sel).all()
                            for elem in elems:
                                br_text = await elem.inner_text()
                                parts = re.split(r'[/>|]', br_text)
                                for p in parts:
                                    clean_p = p.strip()
                                    if not clean_p: continue
                                    
                                    matches = re.finditer(loc_pattern, clean_p)
                                    match_found = False
                                    for match in matches:
                                        match_found = True
                                        c, s = match.group(1).strip(), match.group(2).strip()
                                        if s.upper() in valid_states and c not in blacklist:
                                            city, state = c, s
                                            logger.info(f"[Centurion] Location set via Breadcrumbs: {city}, {state}")
                                            break
                                    
                                    # Fallback for common Centurion auction titles that lack City, ST format
                                    if city == "Unknown" and not match_found:
                                        if clean_p.startswith("Chicago"): 
                                            city, state = "Chicago", "IL"
                                            logger.info("[Centurion] Fallback: Set Chicago, IL from auction title.")
                                        elif clean_p.startswith("Phoenix"):
                                            city, state = "Phoenix", "Az"
                                            logger.info("[Centurion] Fallback: Set Phoenix, Az from auction title.")
                                        elif clean_p.startswith("Las Vegas"):
                                            city, state = "Las Vegas", "NV"
                                            logger.info("[Centurion] Fallback: Set Las Vegas, NV from auction title.")

                                    if city != "Unknown": break
                                if city != "Unknown": break
                            if city != "Unknown": break

                        # Priority B: Body Text Fallback
                        if city == "Unknown":
                            body_text = await page.inner_text("body")
                            matches = re.finditer(loc_pattern, body_text[:10000])
                            for match in matches:
                                c, s = match.group(1).strip(), match.group(2).strip()
                                if s.upper() in valid_states and c not in blacklist:
                                    city, state = c, s
                                    logger.info(f"[Centurion] Location set via Body Scan: {city}, {state}")
                                    break
                    except Exception as e:
                        logger.error(f"[Centurion] Location scan error: {e}")

                # Final Status Safety & Timestamp Override
                if item_name == "Unknown Item" or not item_name:
                    content_lower = (await page.content()).lower()
                    if "page not found" in content_lower or "listing removed" in content_lower:
                        status = "expired"

                if status == "expired":
                    closing_time_iso = datetime.now(timezone.utc).isoformat()
                    logger.info(f"[Centurion] Item expired. Set closing_time to {closing_time_iso}")

                # Prepare Result
                result = {
                    "item_name": item_name.strip(),
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": total_bidders,
                    "closing_time": closing_time_iso,
                    "website_name": "Centurion Service",
                    "status": status
                }
                
                logger.info(f"[Centurion] FINAL DATA: Title='{result['item_name']}', Bid={result['current_bid']}, Location='{result['city']}, {result['state']}', Status='{result['status']}', Closing={result['closing_time']}")

                return result





            except Exception as e:
                logger.error(f"[Centurion] Critical Error: {e}")
                return None
            finally:
                await browser.close()
