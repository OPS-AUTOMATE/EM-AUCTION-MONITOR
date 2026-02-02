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
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[Troostwijk] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Troostwijk is a modern React/Next.js site, wait for core title
                await page.wait_for_selector('h1, .lot-title, [data-testid="lot-title"]', timeout=15000)
                await asyncio.sleep(5) # Stabilization

                # 1. Item Name
                item_name = "Unknown Item"
                name_selectors = ['h1', '.lot-title', '[data-testid="lot-title"]']
                for sel in name_selectors:
                    if await page.locator(sel).count() > 0:
                        item_name = await page.locator(sel).first.inner_text()
                        break
                
                # 2. Bid Extraction
                current_bid = 0.0
                price_selectors = ['.bid-price', '.amount', '[data-testid="current-bid"]', '.price']
                for sel in price_selectors:
                    if await page.locator(sel).count() > 0:
                        bid_text = await page.locator(sel).first.inner_text()
                        try:
                            # Clean both Euro symbols and Commas (European decimal style)
                            clean_bid = bid_text.replace("€", "").replace(" ", "")
                            if "," in clean_bid and "." not in clean_bid:
                                clean_bid = clean_bid.replace(",", ".")
                            clean_bid = re.sub(r'[^\d.]', '', clean_bid)
                            if clean_bid:
                                current_bid = float(clean_bid)
                                break
                        except: continue

                # 3. Status Check
                status = "active"
                if "closed" in await page.content().lower() or "sold" in await page.content().lower():
                    status = "expired"

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "website_name": "Troostwijk Auctions",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[Troostwijk] Error: {e}")
                return None
            finally:
                await browser.close()
