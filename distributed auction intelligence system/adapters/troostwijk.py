import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class TroostwijkAdapter(BaseAuctionAdapter):
    """
    Hardened Troostwijk Adapter (Tier B - Playwright).
    Handles international currency (Euro) and multicontinental layouts.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[Troostwijk] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[Troostwijk] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                
                # Troostwijk is a modern React/Next.js site, wait for core title
                try:
                    await page.wait_for_selector('h1, [data-testid="lot-title"]', timeout=15000)
                except:
                    logger.warning("[Troostwijk] Timeout waiting for selectors.")

                await asyncio.sleep(4) # Stabilization

                # Helper to safely get text content
                async def get_text_safe(selector: str, use_xpath: bool = False) -> str:
                   try:
                       loc = page.locator(f"xpath={selector}" if use_xpath else selector)
                       if await loc.count() > 0:
                           return await loc.first.inner_text()
                   except: pass
                   return ""

                # 1. Item Name
                item_name = await get_text_safe("#__next > div > main > div:nth-child(2) > div > div.col-start-1.col-end-3.row-start-3.row-end-4.pb-4.pt-6.md\\:col-end-2.md\\:row-start-4.md\\:row-end-5.lg\\:col-start-1.lg\\:col-end-2.lg\\:row-start-4.lg\\:row-end-5.lg\\:pr-5.xl\\:col-start-2.xl\\:col-end-3.xl\\:row-start-4.xl\\:row-end-5 > div > div:nth-child(1) > h1")
                if not item_name:
                    item_name = await get_text_safe("/html/body/div[1]/div/main/div[2]/div/div[2]/div/div[1]/h1", use_xpath=True)

                # 2. Location
                # Selector ends in text() so we take the element
                location = await get_text_safe("/html/body/div[1]/div/main/div[2]/div/aside/div[1]/div[1]/dl[1]/dd/a", use_xpath=True)

                # 3. Time Remaining
                time_remaining = await get_text_safe("#__next > div > main > div:nth-child(2) > div > div.relative.md\\:mx-0.md\\:pl-4.md\\:pr-4.md\\:pt-4.after\\:content-\\[\\'\\.\\'\\].after\\:absolute.after\\:left-full.after\\:top-0.after\\:h-full.after\\:w-screen.col-start-2.col-end-3.row-start-2.row-end-6.md\\:row-start-1.md\\:row-end-12.md\\:bg-c-background-neutral-subtle-default.lg\\:col-start-2.lg\\:col-end-3.xl\\:col-start-3.xl\\:col-end-4 > div:nth-child(1) > div.flex.items-center.justify-between.border-b.border-solid.border-c-stroke-neutral-default.pb-3 > div > p")
                if not time_remaining:
                    time_remaining = await get_text_safe("/html/body/div[1]/div/main/div[2]/div/div[3]/div[1]/div[1]/div/p", use_xpath=True)

                # 4. Bid Extraction
                current_bid_text = await get_text_safe("#__next > div > main > div:nth-child(2) > div > div.relative.md\\:mx-0.md\\:pl-4.md\\:pr-4.md\\:pt-4.after\\:content-\\[\\'\\.\\'\\].after\\:absolute.after\\:left-full.after\\:top-0.after\\:h-full.after\\:w-screen.col-start-2.col-end-3.row-start-2.row-end-6.md\\:row-start-1.md\\:row-end-12.md\\:bg-c-background-neutral-subtle-default.lg\\:col-start-2.lg\\:col-end-3.xl\\:col-start-3.xl\\:col-end-4 > div:nth-child(1) > div:nth-child(2) > dl > dd.col-start-1.row-start-2.flex.flex-col > span")
                if not current_bid_text:
                    current_bid_text = await get_text_safe("/html/body/div[1]/div/main/div[2]/div/div[3]/div[1]/div[2]/dl/dd[1]/span", use_xpath=True)
                
                current_bid = 0.0
                if current_bid_text:
                    try:
                        clean_bid = current_bid_text.replace("€", "").replace(" ", "")
                        if "," in clean_bid and "." not in clean_bid:
                            clean_bid = clean_bid.replace(",", ".")
                        clean_bid = re.sub(r'[^\d.]', '', clean_bid)
                        if clean_bid:
                            current_bid = float(clean_bid)
                    except: pass

                # 5. No. of Bids
                bid_count_text = await get_text_safe("/html/body/div[1]/div/main/div[2]/div/div[3]/div[1]/div[5]/div[1]/div[1]", use_xpath=True)

                # Status Check: Hardened
                status = "active"
                # Only mark as expired if explicitly closed or if no time remaining and no title
                if not item_name or item_name == "Unknown Item":
                     content_lower = (await page.content()).lower()
                     if "closed" in content_lower or "sold" in content_lower:
                         status = "expired"
                
                # If we have time remaining, it's definitely NOT expired
                if time_remaining and any(char.isdigit() for char in time_remaining):
                    status = "active"

                return {
                    "item_name": item_name.strip()[:200] if item_name else "Unknown Item",
                    "current_bid": current_bid,
                    "city": location.strip() if location else "Unknown",
                    "state": "",
                    "total_bidders": int(re.sub(r'\D', '', bid_count_text)) if bid_count_text and re.sub(r'\D', '', bid_count_text) else 0,
                    "time_remaining_str": time_remaining.strip() if time_remaining else "",
                    "website_name": "Troostwijk Auctions",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[Troostwijk] Error: {e}")
                return None
            finally:
                await browser.close()
