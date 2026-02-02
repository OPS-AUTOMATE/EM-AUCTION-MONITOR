import logging
import re
import asyncio
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
            
            # Stealth: Context with realistic User-Agent and Viewport
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York", # US Timezone common for scraping
                has_touch=False,
                is_mobile=False,
                java_script_enabled=True,
            )
            
            # Stealth: Inject script to hide webdriver property
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = await context.new_page()

            # OPTIMIZATION: Block heavy resources to save bandwidth (Essential for proxies)
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
                else route.continue_())
            
            # Default values
            item_name = "Unknown Item"
            current_bid = 0.0
            total_bidders = 0
            closing_time_iso = None
            city, state = "Unknown", "Unknown"
            
            
            try:
                logger.info(f"[Centurion] Fetching: {url}")
                # Wait for Network Idle to ensure JS is loaded
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Check if we are on mobile layout or need to wait for a specific element
                try:
                    await page.wait_for_selector("h1", timeout=10000)
                except:
                    logger.warning("[Centurion] Main h1 not found, page might rely on heavy JS.")

                # --- STRATEGY 1: Internal API (Fast & Precise) ---
                api_success = False
                try:
                    # 1. Extract Lot ID
                    lot_id = ""
                    match = re.search(r'/lot/(\d+)', url)
                    if match:
                        lot_id = match.group(1)
                    
                    # 2. Extract CSRF (Try multiple sources)
                    csrf_token = await page.evaluate("""() => {
                        // Try Hidden Input
                        const input = document.querySelector("input[name='csrf_token']");
                        if (input) return input.value;
                        // Try Global Variable (common in PHP apps)
                        if (window.csrf_token) return window.csrf_token;
                        return '';
                    }""")

                    if lot_id and csrf_token:
                        # 3. Execute Fetch via Browser Context
                        api_response = await page.evaluate(f"""
                            async () => {{
                                const formData = new FormData();
                                formData.append('auc-lots', '{lot_id}');
                                formData.append('authenticated', 'false');
                                formData.append('csrf_token', '{csrf_token}');
                                
                                const response = await fetch('/sync/lot', {{
                                    method: 'POST',
                                    headers: {{
                                        'X-Requested-With': 'XMLHttpRequest',
                                        'Accept': 'application/json' 
                                    }},
                                    body: formData
                                }});
                                return await response.json();
                            }}
                        """)
                        
                        if "auctionLotItems" in api_response and lot_id in api_response["auctionLotItems"]:
                            data = api_response["auctionLotItems"][lot_id]
                            
                            # Price
                            if "currentBid" in data:
                                current_bid = float(data["currentBid"])
                            
                            # Bidders
                            if "bidCount" in data:
                                total_bidders = int(data["bidCount"])
                                
                            # Time (Seconds Left -> ISO)
                            if "secondsLeft" in data:
                                seconds_left = float(data["secondsLeft"])
                                if seconds_left > 0:
                                    now_utc = datetime.now(timezone.utc)
                                    closing_time_iso = (now_utc + timedelta(seconds=seconds_left)).isoformat()
                            
                            logger.info(f"[Centurion] API Fetch Success: ${current_bid}, {total_bidders} bidders")
                            api_success = True
                            
                except Exception as api_err:
                    logger.warning(f"[Centurion] API Strategy failed: {api_err}")

                # --- STRATEGY 2: HTML Fallbacks (If API missed anything) ---
                
                # Debug Dump: If API failed AND we have no title, dump HTML to see what's wrong
                if not api_success and item_name == "Unknown Item":
                    try:
                        content = await page.content()
                        with open("debug_centurion.html", "w", encoding="utf-8") as f:
                            f.write(content)
                        logger.info("[Centurion] Dumped page content to 'debug_centurion.html' for inspection.")
                    except: pass
                
                # Title (API usually doesn't have it, so we always scrape this)
                if item_name == "Unknown Item":
                    try:
                        # 1. Try <title> tag first (most reliable on this site)
                        page_title = await page.title()
                        if page_title and "Centurion Service" not in page_title: 
                             item_name = page_title.strip()

                        # 2. Try selectors if title tag was generic
                        if item_name == "Unknown Item" or "Centurion Service" in item_name:
                            title_selectors = [
                                 "h1.lot-details-heading",
                                 "/html/body/div[3]/form/div/article/section[2]/div[1]/h1/span",
                                 "h1",
                                 ".lot-details h1"
                            ]
                            for sel in title_selectors:
                                if sel.startswith("/"): el = page.locator(f"xpath={sel}")
                                else: el = page.locator(sel)
                                if await el.count() > 0:
                                    item_name = await el.first.inner_text()
                                    break
                    except: pass

                # Price Fallback
                if current_bid == 0.0:
                    try:
                        price_selectors = [
                            ".cur_bid", # Best match from screenshot
                            ".left.cur_bid",
                            "span:has-text('Current bid:')",
                            "/html/body/div[3]/form/div/article/section[3]/div[2]/div[2]/div[1]/div/div/span", 
                            ".current-bid-amount",
                            "span:has-text('$')"
                        ]
                        for sel in price_selectors:
                            if sel.startswith("/"): el = page.locator(f"xpath={sel}")
                            else: el = page.locator(sel)
                            
                            count = await el.count()
                            if count > 0:
                                for i in range(count):
                                    text = await el.nth(i).inner_text()
                                    logger.info(f"[Centurion DEBUG] Raw Price Text ({sel}): '{text}'")
                                    
                                    # Fix: Handle "Current bid: $5\nAsking: $10" -> 510 issue
                                    # 1. Look for specific "Current bid" label
                                    if "Current bid:" in text:
                                        # Extract just the current bid line/part
                                        parts = text.split("Current bid:")
                                        if len(parts) > 1:
                                            text = parts[1].split("\n")[0] # Take line immediate after label
                                    
                                    # 2. Extract first valid price number (e.g. $5.00)
                                    # This avoids merging multiple numbers like 5 and 10 into 510
                                    price_match = re.search(r'\$?([\d,]+\.?\d{0,2})', text.replace(",", ""))
                                    if price_match:
                                        val = float(price_match.group(1))
                                        if val > 0:
                                            current_bid = val
                                            logger.info(f"[Centurion DEBUG] Parsed Price: {current_bid}")
                                            break
                                if current_bid > 0: break
                    except Exception as e:
                        logger.warning(f"[Centurion] Price Scrape Error: {e}")

                # Time Fallback
                if not closing_time_iso:
                    try:
                        # Explicit wait for time element (User reported it wasn't fetching)
                        try:
                            await page.wait_for_selector(".time-left", timeout=5000)
                        except: pass

                        time_selectors = [
                            "/html/body/div[3]/form/div/article/section[3]/div[2]/div[2]/div[1]/span", # User Requested
                            ".time-left", # From screenshot
                            "span[id^='lot-time']",
                            ".cur_time"
                        ]
                        time_str = ""
                        for sel in time_selectors:
                             if sel.startswith("/"): el = page.locator(f"xpath={sel}")
                             else: el = page.locator(sel)
                             
                             if await el.count() > 0:
                                 time_str = await el.first.inner_text()
                                 logger.info(f"[Centurion DEBUG] Raw Time Text ({sel}): '{time_str}'")
                                 
                                 if any(x in time_str for x in ['d', 'h', 'm', 's']): 
                                     break
                        
                        if time_str:
                            days, hours, minutes, seconds = 0, 0, 0, 0
                            if m := re.search(r'(\d+)\s*d', time_str): days = int(m.group(1))
                            if m := re.search(r'(\d+)\s*h', time_str): hours = int(m.group(1))
                            if m := re.search(r'(\d+)\s*m', time_str): minutes = int(m.group(1))
                            if m := re.search(r'(\d+)\s*s', time_str): seconds = int(m.group(1))
                            
                            total_s = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds
                            if total_s > 0:
                                closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()
                                logger.info(f"[Centurion] Time scraped: {time_str} -> {closing_time_iso}")
                    except Exception as e:
                        logger.warning(f"[Centurion] Time scrape err: {e}")

                if item_name == "Unknown Item" or (current_bid == 0.0 and not closing_time_iso):
                     # Final debug dump if we are still missing critical info
                    try:
                        with open("debug_centurion_fail.html", "w", encoding="utf-8") as f:
                            f.write(await page.content())
                        logger.warning("[Centurion] Dumped content to debug_centurion_fail.html")
                    except: pass


                return {
                    "item_name": item_name.strip(),
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": total_bidders,
                    "closing_time": closing_time_iso,
                    "website_name": "Centurion Service",
                    "status": "active"
                }

            except Exception as e:
                logger.error(f"[Centurion] Critical Error: {e}")
                return None
            finally:
                await browser.close()
