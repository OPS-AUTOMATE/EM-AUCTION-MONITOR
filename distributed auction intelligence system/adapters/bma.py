import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class BmaAdapter(BaseAuctionAdapter):
    """
    Hardened BMA (British Medical Auctions) Adapter (Tier B - Playwright).
    
    IMPORTANT: BMA requires registration to access certain fields (number of bidders, location).
    This adapter only extracts publicly visible data:
    - Item Name (title)
    - Starting Price (current bid)
    - Time Left
    
    Placeholder values are used for restricted fields:
    - Total Bidders: 0
    - Location: "Unknown, UK"
    - Premium: 15% (standard BMA premium)
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[BMA] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[BMA] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Wait for lot details container
                await page.wait_for_selector('#LotDetailsTimed', timeout=15000)
                await asyncio.sleep(2) # Stabilization

                # 1. Item Name - using provided selector
                item_name = "Unknown Item"
                try:
                    # Selector: #LotDetailsTimed > div > article > section.auctitle.auc_dtl_title.auc_mob_dis > div.tle.aucdttle > h3 > span
                    title_elem = page.locator('#LotDetailsTimed .auc_dtl_title h3 span').first
                    if await title_elem.count() > 0:
                        item_name = await title_elem.inner_text()
                except Exception as e:
                    logger.warning(f"[BMA] Title extraction failed: {e}")
                    # Fallback to h3
                    if await page.locator('h3').count() > 0:
                        item_name = await page.locator('h3').first.inner_text()
                
                # 2. Starting Price - using provided selector
                current_bid = 0.0
                try:
                    # Selector: #currentBid > span
                    bid_elem = page.locator('#currentBid > span').first
                    if await bid_elem.count() > 0:
                        bid_text = await bid_elem.inner_text()
                        # Clean currency symbols (£, $)
                        clean_bid = re.sub(r'[^\d.]', '', bid_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                except Exception as e:
                    logger.warning(f"[BMA] Bid extraction failed: {e}")

                # 3. Time Left - using provided selector pattern
                time_remaining_str = "Unknown"
                try:
                    # Selector pattern: #lot-time{lotid}
                    # We'll look for any element with id starting with "lot-time"
                    time_elem = page.locator('[id^="lot-time"]').first
                    if await time_elem.count() > 0:
                        time_remaining_str = await time_elem.inner_text()
                except Exception as e:
                    logger.warning(f"[BMA] Time extraction failed: {e}")

                # 4. Placeholder values for auth-restricted fields
                total_bidders = 0  # Requires login
                city = "Unknown"   # Requires login
                state = "UK"       # Default for British auctions
                premium_percentage = 15  # Standard BMA premium

                # 5. Status Check
                status = "active"
                content_lower = await page.content()
                if "closed" in content_lower.lower() or "ended" in content_lower.lower():
                    status = "expired"

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "time_remaining_str": time_remaining_str,
                    "total_bidders": total_bidders,
                    "city": city,
                    "state": state,
                    "premium_percentage": premium_percentage,
                    "website_name": "British Medical Auctions",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[BMA] Error: {e}")
                return None
            finally:
                await browser.close()
