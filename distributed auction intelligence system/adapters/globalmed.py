import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GlobalMedAdapter(BaseAuctionAdapter):
    """
    Hardened GlobalMed Adapter (Tier B - Playwright).
    Uses specific CSS selectors provided for GlobalMed auction platform.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[GlobalMed] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[GlobalMed] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Wait for lot details container (dynamic ID)
                await page.wait_for_selector('div[id^="lot-details-"]', timeout=15000)
                await asyncio.sleep(3) # Stabilization for dynamic content

                # 1. Item Name - using provided selector
                item_name = "Unknown Item"
                try:
                    # Try the specific selector first
                    title_elem = page.locator('div[id^="lot-details-"] .content a').first
                    if await title_elem.count() > 0:
                        item_name = await title_elem.inner_text()
                except:
                    # Fallback to h1
                    if await page.locator('h1').count() > 0:
                        item_name = await page.locator('h1').first.inner_text()
                
                # 2. Current Bid - from next-minimum-bid-value
                current_bid = 0.0
                try:
                    bid_elem = page.locator('.next-minimum-bid-value, span.next-minimum-bid-value').first
                    if await bid_elem.count() > 0:
                        bid_text = await bid_elem.inner_text()
                        clean_bid = re.sub(r'[^\d.]', '', bid_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                except Exception as e:
                    logger.warning(f"[GlobalMed] Bid extraction failed: {e}")

                # 3. Buyer Premium - from buyers-premium field
                premium_percentage = 0
                try:
                    premium_elem = page.locator('.buyers-premium .field span').first
                    if await premium_elem.count() > 0:
                        premium_text = await premium_elem.inner_text()
                        premium_match = re.search(r'(\d+)', premium_text)
                        if premium_match:
                            premium_percentage = int(premium_match.group(1))
                except Exception as e:
                    logger.warning(f"[GlobalMed] Premium extraction failed: {e}")

                # 4. Time Remaining - from bidding-countdown
                time_remaining_str = "Unknown"
                closing_time = None
                try:
                    countdown_elem = page.locator('.bidding-countdown span, .bidding-countdown').first
                    if await countdown_elem.count() > 0:
                        time_remaining_str = await countdown_elem.inner_text()
                except Exception as e:
                    logger.warning(f"[GlobalMed] Time extraction failed: {e}")

                # 5. Location - parse from lot location div
                city, state = "Unknown", "Unknown"
                try:
                    # Look for location in the segments area
                    loc_elem = page.locator('div[id^="lot-details-"] .ui.segments .column').nth(3)
                    if await loc_elem.count() > 0:
                        loc_text = await loc_elem.inner_text()
                        # Parse "City, State" format
                        if "," in loc_text:
                            parts = loc_text.split(",")
                            city = parts[0].strip()
                            state = parts[1].strip() if len(parts) > 1 else "Unknown"
                except Exception as e:
                    logger.warning(f"[GlobalMed] Location extraction failed: {e}")

                # 6. Total Bidders - from current-bid link
                total_bidders = 0
                try:
                    bidders_elem = page.locator('.current-bid .field a').first
                    if await bidders_elem.count() > 0:
                        bidders_text = await bidders_elem.inner_text()
                        bidders_match = re.search(r'(\d+)', bidders_text)
                        if bidders_match:
                            total_bidders = int(bidders_match.group(1))
                except Exception as e:
                    logger.warning(f"[GlobalMed] Bidders extraction failed: {e}")

                # 7. Status Check: Hardened
                status = "active"
                content_lower = (await page.content()).lower()
                
                # Check for explicit "Ended" or "Closed" signs
                if "closed" in content_lower or "lot ended" in content_lower or "bidding closed" in content_lower:
                    status = "expired"
                
                # If we have any time string with digits, it's ACTIVE
                if time_remaining_str and any(char.isdigit() for char in time_remaining_str):
                    if "ended" not in time_remaining_str.lower():
                        status = "active"

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "premium_percentage": premium_percentage,
                    "time_remaining_str": time_remaining_str,
                    "city": city,
                    "state": state,
                    "total_bidders": total_bidders,
                    "website_name": "Global Med Auction",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[GlobalMed] Error: {e}")
                return None
            finally:
                await browser.close()
