import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GovPlanetAdapter(BaseAuctionAdapter):
    """
    Hardened GovPlanet Adapter (Tier B - Playwright).
    Prioritizes robust semantic selectors but falls back to user XPaths.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[GovPlanet] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                locale="en-US"
            )
            page = await context.new_page()
            
            try:
                # Add headers
                await page.set_extra_http_headers({
                    "Accept-Language": "en-US,en;q=0.9",
                })

                logger.info(f"[GovPlanet] Fetching: {url}")
                try:
                    await page.goto(url, wait_until="commit", timeout=60000)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=20000)
                    except: pass
                except Exception as e:
                    logger.warning(f"[GovPlanet] Page load timeout/error: {e}")
                    # Might still be able to Scrape if content loaded partially

                # Extract Item ID from URL to construct dynamic selectors
                # URL formats: .../item/12345 or .../for-sale/.../12345?h=...
                item_id = ""
                # Find the last number sequence in the path before query params
                path = url.split("?")[0]
                id_match = re.search(r"(\d{5,})", path)
                if id_match:
                    # If multiple matches, usually the last one is the ID in typical GovPlanet URLs
                    # But if URL is /item/12345, it works.
                    # If URL is /for-sale/Title-123/45678, we want 45678.
                    all_matches = re.findall(r"(\d{5,})", path)
                    if all_matches:
                        item_id = all_matches[-1]
                
                logger.info(f"[GovPlanet] Inferred Item ID: {item_id}")

                # Wait for core content
                try:
                    await page.wait_for_selector('h1', timeout=30000)
                except:
                    pass 

                await asyncio.sleep(2) # Stabilization

                async def get_text_safe(selector: str) -> str:
                    try:
                        loc = page.locator(selector)
                        count = await loc.count()
                        if count > 0:
                             # Return first visible if available
                             for i in range(count):
                                 if await loc.nth(i).is_visible():
                                     return await loc.nth(i).inner_text()
                             # Fallback to first even if hidden
                             return await loc.first.inner_text()
                    except:
                        pass
                    return ""

                # 1. Title
                item_name = await get_text_safe('h1.itemdesc, h1')

                # 2. Location
                # Extra robust label-based search
                location = await get_text_safe('xpath=//*[contains(@class, "label") and contains(translate(.), "location", "LOCATION"), "LOCATION")]/following-sibling::*[contains(@class, "value")]')
                if not location:
                    location = await get_text_safe('.location, [itemprop="availableAtOrFrom"], .item-location')

                # 3. No. of Bids
                bids_selector = f'[id="IP${item_id}_bidcountItemstring"]' if item_id else '[id*="_bidcountItemstring"]'
                bids_text = await get_text_safe(bids_selector)
                if not bids_text:
                    bids_text = await get_text_safe('xpath=//*[contains(@class, "label") and contains(translate(.), "bid", "BID"), "BID")]/following-sibling::*[contains(@class, "value")]')

                # 4. Auction Date/Time
                time_text = await get_text_safe(f'[id="IP${item_id}_timeBox"]' if item_id else '[id*="_timeBox"]')
                if not time_text:
                    time_text = await get_text_safe('xpath=//*[contains(@class, "label") and contains(translate(.), "auction date", "AUCTION DATE"), "AUCTION DATE")]/following-sibling::*[contains(@class, "value")]')

                # 5. Price
                price_selector = f'[id="IP${item_id}_price"]' if item_id else '[id*="_price"], .current-bid, .price'
                price_text = await get_text_safe(price_selector)

                # Parse data
                current_bid = 0.0
                try:
                    clean_bid = re.sub(r'[^\d.]', '', price_text)
                    if clean_bid:
                        current_bid = float(clean_bid)
                except:
                    pass

                # Location parsing
                city, state = "Unknown", "Unknown"
                if location:
                    # Handle "City, State, Country. Zip"
                    # Remove the trailing country/zip part if present (e.g., ", United States. 89030")
                    clean_loc = re.sub(r',\s*United States.*$', '', location, flags=re.I).strip()
                    parts = [p.strip() for p in clean_loc.split(',')]
                    if len(parts) >= 2:
                        city = parts[0]
                        state = parts[1]
                    elif len(parts) == 1:
                        city = parts[0]

                # 6. Calculate ISO closing time
                closing_time_iso = None
                if time_text:
                    try:
                        from dateutil import parser as date_parser
                        # GovPlanet format is often "Mar 10, 12:09 PM - 12:10 PM PDT"
                        # We take the start time part (before the dash)
                        time_to_parse = time_text.split("-")[0].strip()
                        
                        # Handle potential timezone at the end of the full string
                        timezone_match = re.search(r'\b([A-Z]{3,4})\b$', time_text.strip())
                        timezone_suffix = f" {timezone_match.group(1)}" if timezone_match else ""
                        
                        full_parse_str = f"{time_to_parse}{timezone_suffix}"
                        
                        # Define common US timezones for dateutil
                        tzinfos = {
                            "PDT": -7 * 3600, "PST": -8 * 3600,
                            "EDT": -4 * 3600, "EST": -5 * 3600,
                            "CDT": -5 * 3600, "CST": -6 * 3600,
                            "MDT": -6 * 3600, "MST": -7 * 3600,
                        }
                        
                        dt = date_parser.parse(full_parse_str, tzinfos=tzinfos)
                        
                        # Ensure year is reasonable (parser might default to current year if missing, or 1900 if offset 0)
                        now = datetime.now()
                        if dt.year < 2000:
                            dt = dt.replace(year=now.year)
                        
                        # If date has passed significantly (e.g. Dec item but it is currently Jan), it might be next year
                        if dt < now - timedelta(days=60):
                             dt = dt.replace(year=now.year + 1)
                             
                        closing_time_iso = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"[GovPlanet] Date parsing failed for '{time_text}': {e}")
                        # Fallback to simple regex if dateutil fails
                        pass

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": int(re.sub(r'\D', '', bids_text)) if bids_text and re.sub(r'\D', '', bids_text) else 0,
                    "time_remaining_str": time_text.strip(),
                    "closing_time": closing_time_iso,
                    "website_name": "GovPlanet",
                    "status": "active"
                }

            except Exception as e:
                logger.error(f"[GovPlanet] Error: {e}")
                return None
            finally:
                try:
                    await browser.close()
                except:
                    pass
