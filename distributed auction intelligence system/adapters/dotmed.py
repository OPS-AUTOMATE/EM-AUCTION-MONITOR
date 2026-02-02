import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class DotMedAdapter(BaseAuctionAdapter):
    """
    Hardened DotMed Adapter (Tier B - Playwright).
    Since DotMed blocks direct HTTP (403), we use a browser with stealth headers.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                # Add extra headers to mimic a real browser
                await page.set_extra_http_headers({
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,xml;q=0.9,image/avif,webp,image/apng,*/*;q=0.8"
                })

                logger.info(f"[DotMed] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # Check for item title
                await page.wait_for_selector('h1, [itemprop="name"]', timeout=15000)
                await asyncio.sleep(2) # Stabilization

                # 1. Item Name
                item_name = await page.locator('h1').first.inner_text()
                
                # 2. Bid Extraction
                current_bid = 0.0
                # DotMed uses specific patterns for prices
                bid_selectors = ['.price', '[itemprop="price"]', 'b:has-text("$")']
                for sel in bid_selectors:
                    if await page.locator(sel).count() > 0:
                        bid_text = await page.locator(sel).first.inner_text()
                        try:
                            clean_bid = re.sub(r'[^\d.]', '', bid_text)
                            if clean_bid:
                                current_bid = float(clean_bid)
                                break
                        except: continue

                # 3. Location
                city, state = "Unknown", "Unknown"
                loc_match = re.search(r"Location:\s*</b>\s*([^<,]+),\s*([A-Z]{2})", await page.content(), re.I)
                if loc_match:
                    city, state = loc_match.group(1).strip(), loc_match.group(2).strip()

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "website_name": "DotMed",
                    "status": "active"
                }

            except Exception as e:
                logger.error(f"[DotMed] Error: {e}")
                return None
            finally:
                await browser.close()
