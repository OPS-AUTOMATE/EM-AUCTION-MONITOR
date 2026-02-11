import logging
import re
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class BidspotterAdapter(BaseAuctionAdapter):
    """
    Hardened Bidspotter Adapter (Tier B - SSR HTML).
    Uses strict XPaths provided for verified layouts.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Prepare Launch options (Proxy support)
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[Bidspotter] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # OPTIMIZATION: Block images/media but KEEP stylesheets for JS layout
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font"] 
                else route.continue_())
            
            try:
                logger.info(f"[Bidspotter] Fetching: {url}")
                # Use 'load' for Bidspotter as it's a heavy SPA
                await page.goto(url, wait_until="load", timeout=60000)
                await asyncio.sleep(3) # Wait for JS to settle

                # Helper to safely get text content
                async def get_text_safe(selector: str) -> str:
                    try:
                        loc = page.locator(selector)
                        if await loc.count() > 0:
                            return (await loc.first.inner_text()).strip()
                    except: pass
                    return ""

                # Initialize defaults
                item_name = "Unknown Item"
                current_bid = 0.0
                city, state = "Unknown", ""
                total_bidders = 0
                end_time_pkt = None
                raw_time_str = ""

                # 1. Title
                # Strategy A: User XPath
                item_name = await get_text_safe("xpath=/html/body/div[1]/main/div/div[1]/div/div[2]/div/h1")
                if not item_name:
                    # Strategy B: Common H1
                    item_name = await get_text_safe("h1")
                if not item_name:
                    # Strategy C: Lot Details Class
                    item_name = await get_text_safe(".lot-name, .lot-title, h1.lot-details__title, .lot-details h1")
                
                if not item_name: item_name = "Unknown Item"
                logger.info(f"[Bidspotter] Extracted Title: {item_name}")

                # 2. Current Bid / Price
                # Strategy A: User XPath
                price_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[1]/span/strong"
                price_text = await get_text_safe(f"xpath={price_xpath}")
                if not price_text:
                    price_text = await get_text_safe("xpath=/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[1]/span")

                if not price_text:
                    # Strategy B: Common Price classes
                    price_text = await get_text_safe(".current-bid, .lot-price, .price-value, .lot-details__bid-box-current-bid-amount")
                
                if price_text:
                    logger.info(f"[Bidspotter] Extracted Price Text: {price_text}")
                    clean_text = re.sub(r'[^\d.]', '', price_text)
                    if clean_text:
                        current_bid = float(clean_text)
                else:
                    logger.warning("[Bidspotter] Price not found.")

                # 3. Location
                # Strategy A: User XPath
                loc_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[2]/div[2]/strong/span"
                loc_text = await get_text_safe(f"xpath={loc_xpath}")
                if not loc_text:
                    # Strategy B: Broad Location search
                    loc_text = await get_text_safe(".lot-location, .location-text, .venue-location, address, .lot-details__address")
                
                if loc_text:
                    logger.info(f"[Bidspotter] Extracted Location Text: {loc_text}")
                    if "VAT REFUND" in loc_text.upper():
                        city, state = "Unknown", "Unknown"
                    else:
                        parts = loc_text.split(",")
                        if len(parts) >= 2:
                            city = parts[0].strip()
                            state = parts[1].strip()
                        else:
                            city = loc_text.strip()
                else:
                    logger.warning("[Bidspotter] Location not found.")

                # 4. Bidders Count
                # Strategy A: User XPath
                bid_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/span/span/span[2]/span[1]/span[1]/span"
                bid_text = await get_text_safe(f"xpath={bid_xpath}")
                if not bid_text:
                    # Strategy B: User provided CSS
                    bid_text = await get_text_safe("#lotDetailsBids > span")
                
                if bid_text:
                    logger.info(f"[Bidspotter] Extracted Bidders Text: {bid_text}")
                    clean_bidders = re.sub(r'\D', '', bid_text)
                    if clean_bidders:
                        total_bidders = int(clean_bidders)
                else:
                    logger.warning("[Bidspotter] Bidders count not found.")

                # 5. Buyer's Premium (New)
                # Strategy A: User XPath
                premium_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[4]/div[2]/div[2]/div"
                premium_text = await get_text_safe(f"xpath={premium_xpath}")
                premium_val = 0.0
                
                if premium_text:
                    # Extract number from "18%" or "18 %"
                    mt = re.search(r'(\d+(?:\.\d+)?)', premium_text)
                    if mt:
                        premium_val = float(mt.group(1))
                        logger.info(f"[Bidspotter] Extracted Premium: {premium_val}%")

                # 5. End Time
                # Strategy: Locate the time element and extract raw string
                time_xpath_1 = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[1]/div[2]/div[2]/div/div/span"
                time_xpath_2 = "/html/body/div[2]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[1]/div[2]/div[2]/div/div/span"
                
                time_el = page.locator(f"xpath={time_xpath_1}")
                if await time_el.count() == 0:
                    time_el = page.locator(f"xpath={time_xpath_2}")
                
                # Fallback: General search for time elements
                if await time_el.count() == 0:
                    time_el = page.locator("time, .time-remaining, .countdown, [class*='time'], [class*='countdown']")
                
                if await time_el.count() > 0:
                    raw_time_str = await time_el.first.get_attribute("datetime")
                    if not raw_time_str:
                        raw_time_str = await time_el.first.inner_text()
                    
                    if raw_time_str:
                        raw_time_str = raw_time_str.strip()
                        logger.info(f"[Bidspotter] Extracted Time String: {raw_time_str}")
                        
                        # Parsing logic
                        dt = None
                        # ISO Part
                        if 'T' in raw_time_str:
                            try:
                                raw = raw_time_str
                                parts = raw.split('T')
                                if len(parts) == 2:
                                    date_part = parts[0]
                                    time_part = parts[1].replace('Z', '')
                                    if '-' in time_part and ':' not in time_part:
                                        time_part = time_part.replace('-', ':')
                                    clean_iso = f"{date_part}T{time_part}"
                                    if 'Z' in raw or raw.endswith('00'): clean_iso += "+00:00"
                                    dt = datetime.fromisoformat(clean_iso)
                            except: pass

                        # Text Format Part
                        if not dt:
                            try:
                                tz_map = {"GMT":0,"UTC":0,"EST":-5,"EDT":-4,"CST":-6,"CDT":-5,"MST":-7,"MDT":-6,"PST":-8,"PDT":-7, "ET":-5}
                                offset = 0
                                clean_text = raw_time_str
                                for k, v in tz_map.items():
                                    if k in clean_text:
                                        offset = v
                                        clean_text = clean_text.replace(k, "").strip()
                                        break
                                
                                clean_text = clean_text.upper()
                                for fmt in ["%b %d, %Y %I:%M%p", "%b %d, %Y %I:%M %p", "%Y-%m-%d %H:%M:%S", "%b %d, %Y %H:%M"]:
                                    try:
                                        dt = datetime.strptime(clean_text, fmt)
                                        dt = dt.replace(tzinfo=timezone(timedelta(hours=offset)))
                                        break
                                    except: continue
                            except: pass

                        # Countdown Part
                        if not dt:
                            try:
                                d, h, m, s = 0, 0, 0, 0
                                if mt := re.search(r'(\d+)\s*d', raw_time_str, re.I): d = int(mt.group(1))
                                if mt := re.search(r'(\d+)\s*h', raw_time_str, re.I): h = int(mt.group(1))
                                if mt := re.search(r'(\d+)\s*m', raw_time_str, re.I): m = int(mt.group(1))
                                if mt := re.search(r'(\d+)\s*s', raw_time_str, re.I): s = int(mt.group(1))
                                total_s = (d * 86400) + (h * 3600) + (m * 60) + s
                                if total_s > 0:
                                    dt = datetime.now(timezone.utc) + timedelta(seconds=total_s)
                            except: pass

                        if dt:
                            pkt_tz = timezone(timedelta(hours=5))
                            end_time_pkt = dt.astimezone(pkt_tz).isoformat()
                
                if not end_time_pkt:
                    # Final fallback: Look for date in page content
                    date_match = re.search(r'([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*[ap]m)', await page.content(), re.I)
                    if date_match:
                        raw_time_str = date_match.group(1)
                        try:
                            dt = datetime.strptime(raw_time_str.upper(), "%b %d, %Y %I:%M %p")
                            # Assume ET if not specified
                            dt = dt.replace(tzinfo=timezone(timedelta(hours=-5)))
                            pkt_tz = timezone(timedelta(hours=5))
                            end_time_pkt = dt.astimezone(pkt_tz).isoformat()
                        except: pass

                if not end_time_pkt:
                    logger.warning(f"[Bidspotter] Could not parse closing time from: {raw_time_str}")

                # 6. Status check
                status = "active"
                # Check bidding container first to avoid sidebar false positives
                bid_area = page.locator(".lot-details__bidding, #lotDetailsBidding, .bidding-container")
                area_text = ""
                if await bid_area.count() > 0:
                    area_text = (await bid_area.first.inner_text()).lower()
                
                # Keywords that confirm it's DEFINITELY closed
                if any(x in area_text for x in ["lot closed", "sold for", "bidding has ended"]):
                    status = "expired"
                
                # OVERRIDE: If we have a future date, trust the date over keywords (which might be from other lots)
                if end_time_pkt:
                    try:
                        ct = datetime.fromisoformat(end_time_pkt)
                        if ct > datetime.now(ct.tzinfo):
                            status = "active"
                    except: pass
                
                # If area_text is empty, fallback to a broader but still safe check
                if not area_text:
                    page_content = (await page.content()).lower()
                    if any(x in page_content for x in ["auction closed", "bidding has ended"]):
                        status = "expired"

                res = {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "premium_percentage": premium_val,
                    "total_bidders": total_bidders,
                    "closing_time": end_time_pkt,
                    "time_remaining_str": raw_time_str if raw_time_str else "Syncing...",
                    "website_name": "BidSpotter",
                    "status": status
                }
                logger.info(f"[Bidspotter] Final Result: {res}")
                return res

            except Exception as e:
                logger.error(f"[Bidspotter] Critical Error: {e}")
                return None
            finally:
                await browser.close()
