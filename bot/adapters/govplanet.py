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
                # User XPath: /html/body/div[2]/div[3]/div[1]/div/div[2]/div/div[1]/div/h1
                # Robust: h1.itemdesc
                item_name = await get_text_safe('h1.itemdesc')
                if not item_name:
                    item_name = await get_text_safe('h1')

                # 2. Location
                # User XPath: .../div[3]/div[2]/span
                # Robust: .location, [itemprop="availableAtOrFrom"]
                location = await get_text_safe('.location, [itemprop="availableAtOrFrom"], .item-location')
                if not location:
                     location = await get_text_safe('xpath=/html/body/div[2]/div[3]/div[1]/div/div[2]/div/div[3]/div[2]/span')

                # 3. No. of Bids
                # Construct specific selector if ID known
                bids_text = ""
                if item_id:
                     # ID has $ which needs escaping in CSS selector
                     # Use attribute selector: [id="IP$ITEMID_bidcountItemstring"]
                     bids_selector = f'[id="IP${item_id}_bidcountItemstring"]'
                     bids_text = await get_text_safe(bids_selector)
                
                if not bids_text:
                    bids_text = await get_text_safe('[id*="_bidcountItemstring"]') 
                if not bids_text:
                    bids_text = await get_text_safe('xpath=/html/body/div[2]/div[3]/div[1]/div/div[3]/div[2]/div[5]/div/div/div/div[1]/div[3]/div[2]/div/div[2]/span/nobr/b/span')

                # 4. Auction Date/Time
                time_text = ""
                if item_id:
                    time_text = await get_text_safe(f'[id="IP${item_id}_timeBox"]')
                
                if not time_text:
                    time_text = await get_text_safe('[id*="_timeBox"]')

                # 5. Price
                price_text = ""
                if item_id:
                     price_text = await get_text_safe(f'[id="IP${item_id}_price"]')
                
                if not price_text:
                     price_text = await get_text_safe('[id*="_price"], .current-bid, .price')

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
                    parts = location.split(',')
                    if len(parts) >= 2:
                        city = parts[0].strip()
                        state = parts[1].strip()

                # 6. Calculate ISO closing time
                closing_time_iso = None
                if time_text:
                    try:
                        clean_time = time_text.strip()
                        # Handle "Feb 17, time TBD" or just "Feb 17"
                        # Regex to find Month and Day
                        date_match = re.search(r'([A-Z][a-z]{2})\s*(\d{1,2})', clean_time, re.I)
                        if date_match:
                            month_str = date_match.group(1)
                            day_val = int(date_match.group(2))
                            # Default to current year or next if month already passed? 
                            # Usually these are future auctions.
                            now = datetime.now()
                            # Minimal parsing
                            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                            month_idx = months.index(month_str.capitalize()) + 1
                            
                            # Use aware datetime to prevent engine overlap errors
                            dt = datetime(now.year, month_idx, day_val, 0, 0, 0)
                            # If the date is very far in the past, move to next year
                            if dt < now - timedelta(days=30):
                                dt = dt.replace(year=now.year + 1)
                            
                            # Add UTC offset to string
                            closing_time_iso = dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                    except:
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
