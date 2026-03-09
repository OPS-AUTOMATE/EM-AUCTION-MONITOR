import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class SurplusMarketplaceAdapter(BaseAuctionAdapter):
    """
    Hardened Surplus Marketplace Adapter (Tier B - Playwright).
    Moved from HTTP to Playwright to support MUI/React dynamic rendering.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[SurplusMarketplace] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"[SurplusMarketplace] Fetching: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Title selector - wait for it to ensure React has mounted
                title_xpath = 'xpath=/html/body/div/div[1]/div/div/div/div[1]/div[2]/div/h5'
                try:
                    await page.wait_for_selector(title_xpath, timeout=30000)
                except:
                     return {"status": "error", "reason": "timeout"}

                await asyncio.sleep(3) # Wait for hydration

                async def get_text_safe(xpath: str) -> str:
                    try:
                        if await page.locator(xpath).count() > 0:
                            return await page.locator(xpath).first.inner_text()
                    except:
                        pass
                    return ""

                # 1. Title
                item_name = await get_text_safe(title_xpath)

                # 2. Price
                price_xpath = 'xpath=/html/body/div/div[1]/div/div/div/div[1]/div[2]/div/div[1]/div[1]/div/div[2]/p[1]/span/span'
                price_text = await get_text_safe(price_xpath)

                # 3. Time Left
                time_left_xpath = 'xpath=/html/body/div/div[1]/div/div/div/div[1]/div[2]/div/div[1]/div[4]/div/div[2]/p[1]/span/p'
                time_left = await get_text_safe(time_left_xpath)

                # 4. Buyer Premium
                bp_xpath = 'xpath=/html/body/div/div[1]/div/div/div/div[1]/div[2]/div/div[1]/div[1]/div/div[2]/p[2]/span'
                buyer_premium = await get_text_safe(bp_xpath)

                # 5. Location
                location_xpath = 'xpath=/html/body/div/div[1]/div/div/div/div[1]/div[2]/div/div[1]/div[6]/div/p/span'
                location = await get_text_safe(location_xpath)

                # Parse Price
                current_bid = 0.0
                try:
                    clean_bid = re.sub(r'[^\d.]', '', price_text)
                    if clean_bid:
                        current_bid = float(clean_bid)
                except:
                    pass

                # Parse Location
                city, state = "Unknown", "Unknown"
                if location:
                    # Generic parser since format is unknown but likely "City, State"
                    parts = location.split(',')
                    if len(parts) >= 2:
                        city = parts[0].strip()
                        state = parts[1].strip()

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "time_remaining_str": time_left.strip(),
                    "premium_percentage": buyer_premium.strip(),
                    "website_name": "Surplus Marketplace",
                    "status": "active"
                }

            except Exception as e:
                logger.error(f"[SurplusMarketplace] Error: {e}")
                return None
            finally:
                try:
                    await browser.close()
                except:
                    pass
