import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GCSurplusAdapter(BaseAuctionAdapter):
    """
    Hardened GC Surplus Adapter (Tier B - Playwright).
    Handles bilingual (EN/FR) state and dynamic pricing.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[GCSurplus] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[GCSurplus] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                # Wait for title to appear
                try:
                    await page.wait_for_selector('h1, #bidPanelId', timeout=15000)
                except:
                    logger.warning("[GCSurplus] Timeout waiting for selectors.")

                await asyncio.sleep(3) # Stabilization

                # Helper to safely get text content
                async def get_text_safe(selector: str, use_xpath: bool = False) -> str:
                   try:
                       loc = page.locator(f"xpath={selector}" if use_xpath else selector)
                       if await loc.count() > 0:
                           return await loc.first.inner_text()
                   except: pass
                   return ""

                # 1. Item Name
                item_name = await get_text_safe("#bidPanelId > section > div > div.col-sp-12.fontSize120.blueBold.bPad10")
                if not item_name:
                    item_name = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/div[1]", use_xpath=True)
                if not item_name:
                    item_name = await get_text_safe("h1")

                # 2. Bid Extraction
                current_bid_text = await get_text_safe("#currentBid")
                if not current_bid_text:
                    current_bid_text = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[1]/span[1]", use_xpath=True)
                
                current_bid = 0.0
                if current_bid_text:
                    try:
                        clean_bid = re.sub(r'[^\d.]', '', current_bid_text)
                        if clean_bid:
                            current_bid = float(clean_bid)
                    except: pass

                # 3. Time Remaining
                time_remaining = await get_text_safe("#timeRemaining")
                if not time_remaining:
                    time_remaining = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[3]/span[1]", use_xpath=True)

                # 4. Location
                location = await get_text_safe("#bidPanelId > section > div > dl > dd:nth-child(12)")
                if not location:
                    location = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[6]", use_xpath=True)

                # 5. Closing Date
                closing_date = await get_text_safe("#closingDateId")
                if not closing_date:
                    closing_date = await get_text_safe("/html/body/div[3]/div/main/div[2]/form/div/div/div[6]/div[2]/section/div/div[1]/section/div/dl/dd[8]/span", use_xpath=True)

                # Status Check: Hardened
                status = "active"
                if not item_name or item_name == "Unknown Item":
                     content_lower = (await page.content()).lower()
                     if "closed" in content_lower or "fermé" in content_lower:
                         status = "expired"
                
                if time_remaining and any(char.isdigit() for char in time_remaining):
                    status = "active"

                return {
                    "item_name": item_name.strip()[:200] if item_name else "Unknown Item",
                    "current_bid": current_bid,
                    "city": location.strip() if location else "Unknown",
                    "state": "",
                    "time_remaining_str": time_remaining.strip() if time_remaining else "",
                    "website_name": "GC Surplus",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[GCSurplus] Error: {e}")
                return None
            finally:
                await browser.close()
