import asyncio
import logging
import re
from datetime import datetime
import pytz
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GsaAdapter(BaseAuctionAdapter):
    """
    Hardened GSA Adapter using User-Defined XPaths and Patterns.
    Combines API speed with browser precision.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        # 1. API Mode (SUID links)
        suid_match = re.search(r"suid=([A-Z0-9]+)", url, re.I)
        if suid_match:
            data = await self._fetch_via_api(suid_match.group(1), url)
            if data: return data

        # 2. Browser Mode (Preview links)
        return await self._fetch_via_browser(url)

    async def _fetch_via_api(self, suid: str, original_url: str) -> Optional[Dict[str, Any]]:
        import httpx
        api_url = f"https://gsaauctions.gov/gsaauctions/aucindx/?suid={suid}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(api_url)
                if response.status_code == 200:
                    data = response.json()
                    item_name = data.get("itemName") or data.get("lotName") or "GSA Item"
                    current_bid = float(str(data.get("currentBid", 0)).replace(",", ""))
                    total_bidders = int(data.get("bidderCount", 0))
                    closing_time_iso = data.get("closingTime") or data.get("auctionEndTime")
                    
                    return {
                        "item_name": item_name.strip()[:200],
                        "current_bid": current_bid,
                        "total_bidders": total_bidders,
                        "closing_time": closing_time_iso,
                        "city": data.get("city", "Unknown"),
                        "state": data.get("state", "Unknown"),
                        "website_name": "GSA Auctions",
                        "status": "active"
                    }
        except: return None
        return None

    async def _fetch_via_browser(self, url: str) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Prepare Launch options (NO PROXY for GSA as requested)
            launch_opts = {"headless": True}
            
            # proxy_conf = self.get_proxy_config()
            # if proxy_conf:
            #     launch_opts["proxy"] = proxy_conf
            #     logger.info(f"[GSA-Browser] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # OPTIMIZATION: Block heavy resources
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
                else route.continue_())
            try:
                logger.info(f"[GSA-Browser] Deep Scrape: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Wait for GSA specific detail container
                try:
                    await page.wait_for_selector(".ppms-details-container", timeout=15000)
                except: pass
                
                await asyncio.sleep(6) # Stabilization

                # --- 1. Get Primary Content Block for Regex ---
                main_block = page.locator(".ppms-details-container").first
                full_text = await main_block.inner_text() if await main_block.count() > 0 else await page.content()

                # --- 2. Extract Basic Data via Patterns ---
                item_name = "Unknown GSA Item"
                name_match = re.search(r"Item Name\s*:\s*(.*?)\s*Sale Lot Number", full_text, re.DOTALL | re.I)
                if name_match: item_name = name_match.group(1).strip()
                else:
                    h1_count = await page.locator("h1").count()
                    if h1_count > 0:
                        h1 = await page.locator("h1").first.inner_text()
                        item_name = h1.strip()

                current_bid = 0.0
                price_match = re.search(r"Current Bid:\s*\$?\s*([\d,]+\.?\d*)", full_text, re.I)
                if price_match: current_bid = float(price_match.group(1).replace(",", ""))
                
                total_bidders = 0
                bidder_match = re.search(r"Bidders:\s*(\d+)", full_text, re.I)
                if bidder_match: total_bidders = int(bidder_match.group(1))

                # --- 3. Location via XPath ---
                city, state = "Unknown", "Unknown"
                xpath_location = "/html/body/div[1]/main/section/div/div/div[1]/div[1]/div/ul/li/div/div[1]/div[1]/ul/li[3]"
                loc_el = page.locator(f"xpath={xpath_location}")
                if await loc_el.count() > 0:
                    try:
                        loc_text = (await loc_el.inner_text()).replace("City, State :", "").strip()
                        if "," in loc_text:
                            parts = loc_text.split(",")
                            city, state = parts[0].strip(), parts[1].strip()
                    except: pass
                elif "," in full_text:
                    loc_match = re.search(r"City,\s*State\s*:\s*(.*?)\s*Closing Time", full_text, re.DOTALL | re.I)
                    if loc_match:
                        lt = loc_match.group(1).strip()
                        if "," in lt:
                            pts = lt.split(",")
                            city, state = pts[0].strip(), pts[1].strip()

                # --- 4. Closing Time via XPath & Regex ---
                closing_time_iso = None
                xpath_closing = "/html/body/div[1]/main/section/div/div/div[1]/div[1]/div/ul/li/div/div[2]/div[2]/div/div/ul/li[11]"
                closing_el = page.locator(f"xpath={xpath_closing}")
                raw_closing = None
                if await closing_el.count() > 0:
                    try:
                        raw_closing = (await closing_el.inner_text()).replace("Closing Time :", "").strip()
                    except: pass
                
                if not raw_closing:
                    patterns = [
                        r"(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})\s*CT",
                        r"(?:Closing Time|Ends)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})"
                    ]
                    for p in patterns:
                        m = re.search(p, await page.content(), re.I)
                        if m:
                            raw_closing = m.group(1).strip()
                            break

                if raw_closing:
                    try:
                        # Clean: 02/05/2026 04:47 PM
                        date_str = re.sub(r'(\d{1,2}:\d{2})\s*([APM]{2})', r'\1 \2', raw_closing, flags=re.I)
                        date_str = re.sub(r'[^0-9/: APM]', '', date_str).strip()
                        naive_dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
                        central = pytz.timezone('US/Central')
                        closing_time_iso = central.localize(naive_dt).isoformat()
                    except: pass

                # --- 5. Status ---
                status = "active"
                xpath_status = "/html/body/div[1]/main/section/div/div/div[1]/div[1]/div/ul/li/div/div[2]/div[2]/div/div/ul/li[12]"
                status_el = page.locator(f"xpath={xpath_status}")
                if await status_el.count() > 0:
                    try:
                        if "closed" in (await status_el.inner_text()).lower(): status = "expired"
                    except: pass

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "total_bidders": total_bidders,
                    "closing_time": closing_time_iso,
                    "city": city,
                    "state": state,
                    "website_name": "GSA Auctions",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[GSA-Browser] Error: {e}")
                return None
            finally:
                await browser.close()
