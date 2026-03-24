"""
GovPlanet Adapter Module.
Extracts listing details for government surplus equipment, with special handling for item IDs and dates.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GovPlanetAdapter(BaseAuctionAdapter):
    """
    Hardened GovPlanet Adapter (Tier B - Playwright).
    Sophisticated extraction with support for US timezones and dynamic item IDs.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[GovPlanet] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                locale="en-US"
            )
            page = await context.new_page()
            
            try:
                await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
                logger.info("[GovPlanet] Fetching: %s", url)
                
                try:
                    await page.goto(url, wait_until="commit", timeout=60000)
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except (PlaywrightError, asyncio.TimeoutError):
                    logger.warning("[GovPlanet] Partial load or timeout at %s", url)

                # Extract Item ID for targeting specific elements
                item_id = ""
                path = url.split("?")[0]
                if id_match := re.findall(r"(\d{5,})", path):
                    item_id = id_match[-1]
                
                logger.debug("[GovPlanet] Inferred Item ID: %s", item_id)

                try:
                    await page.wait_for_selector('h1', timeout=20000)
                except (PlaywrightError, asyncio.TimeoutError):
                    pass 

                await asyncio.sleep(2) # Stabilization

                async def get_text_safe(selector: str) -> str:
                    try:
                        loc = page.locator(selector)
                        count = await loc.count()
                        if count > 0:
                             for i in range(count):
                                 if await loc.nth(i).is_visible():
                                     return (await loc.nth(i).inner_text()).strip()
                             return (await loc.first.inner_text()).strip()
                    except (PlaywrightError, Exception):
                        pass
                    return ""

                # 1. Title
                item_name = await get_text_safe('h1.itemdesc, h1')

                # 2. Location
                # Live items have "Location" label, Sold items have "LOCATION"
                location = await get_text_safe('xpath=//*[contains(translate(text(), "LOCATION", "location"), "location")]/following-sibling::*[1]')
                if not location:
                    # Try targeting the parent container
                    location = await get_text_safe('xpath=//div[contains(text(), "Location")]/following-sibling::div')
                if not location:
                    location = await get_text_safe(".location, .item-location, .item-stats div:nth-child(2), [itemprop='availableAtOrFrom']")

                # 3. No. of Bids
                bids_text = None
                # Check for "11 bids" or "97" pattern anywhere on page
                bids_count_el = await page.query_selector('xpath=//*[contains(text(), " bids") or contains(text(), " Bids")]')
                if bids_count_el:
                    bids_text = await bids_count_el.inner_text()
                
                if not bids_text:
                    bids_text = await get_text_safe('xpath=//*[contains(translate(text(), "BIDS", "bids"), "bids")]/following-sibling::*[1]')
                
                if not bids_text:
                    bids_selector = f'[id="IP${item_id}_bidcountItemstring"]' if item_id else '[id*="_bidcountItemstring"]'
                    bids_text = await get_text_safe(bids_selector)

                # 4. Auction Date/Time
                time_text = await get_text_safe(f'[id="IP${item_id}_timeBox"]' if item_id else '[id*="_timeBox"]')

                # 5. Price
                # Live items use "Highest bid", Sold items use "Winning Bid"
                price_text = await get_text_safe('xpath=//div[contains(translate(normalize-space(), "BID", "bid"), "bid")]/following-sibling::div[1]')
                if not price_text:
                    price_selector = f'[id="IP${item_id}_price"]' if item_id else '[id*="_price"], .current-bid, .price, .winning-bid'
                    price_text = await get_text_safe(price_selector)

                current_bid = 0.0
                if price_text:
                    # Remove labels if they were captured (e.g. "US $305")
                    clean_price = re.sub(r'[^\d.]', '', price_text.replace(",", ""))
                    if clean_price:
                        current_bid = float(clean_price)

                # Location Parsing
                city, state = "Unknown", "Unknown"
                if location:
                    # Clean "United States" and zip codes
                    clean_loc = re.sub(r'United States.*$', '', location, flags=re.I).strip()
                    clean_loc = clean_loc.rstrip(',. ')
                    parts = [p.strip() for p in clean_loc.split(',')]
                    if len(parts) >= 2:
                        city, state = parts[0], parts[1]
                    elif parts:
                        city = parts[0]

                # 6. Date Parsing
                closing_time_iso = None
                if time_text and "TBD" not in time_text.upper():
                    try:
                        from dateutil import parser as date_parser
                        time_to_parse = time_text.split("-")[0].strip()
                        tz_match = re.search(r'\b([A-Z]{3,4})\b$', time_text.strip())
                        tz_suffix = f" {tz_match.group(1)}" if tz_match else ""
                        
                        tzinfos = {
                            "PDT": -7 * 3600, "PST": -8 * 3600, "EDT": -4 * 3600, "EST": -5 * 3600,
                            "CDT": -5 * 3600, "CST": -6 * 3600, "MDT": -6 * 3600, "MST": -7 * 3600,
                        }
                        
                        dt = date_parser.parse(f"{time_to_parse}{tz_suffix}", tzinfos=tzinfos)
                        now_utc = datetime.now(timezone.utc)
                        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                        if dt.year < 2000: dt = dt.replace(year=now_utc.year)
                        if dt < now_utc - timedelta(days=60): dt = dt.replace(year=now_utc.year + 1)
                        closing_time_iso = dt.isoformat()
                    except (ImportError, ValueError, OverflowError):
                        pass

                # 7. Status Logic
                page_content = (await page.content()).lower()
                status = "active"
                if any(kw in page_content for kw in ["sold!", "winning bid", "bidding closed", "auction ended"]):
                    status = "expired"
                
                # Check Standalone 'sold' word boundary
                if status == "active" and re.search(r"\bsold\b", page_content):
                    if "sold on" in page_content or "winning bid" in page_content:
                        status = "expired"

                return {
                    "item_name": item_name[:200] if item_name else "Unknown",
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": int(re.sub(r'\D', '', bids_text)) if bids_text and re.sub(r'\D', '', bids_text) else 0,
                    "time_remaining_str": time_text or "",
                    "closing_time": closing_time_iso,
                    "website_name": "GovPlanet",
                    "status": status
                }




            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[GovPlanet] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
