"""
Surplus Marketplace Adapter Module.
Extracts listing details for surplus goods, utilizing Playwright to handle React/MUI dynamic hydration.
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

class SurplusMarketplaceAdapter(BaseAuctionAdapter):
    """
    Hardened Surplus Marketplace Adapter (Tier B - Playwright).
    Sophisticated extraction for modern SPAs with React hydration.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[SurplusMarketplace] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info("[SurplusMarketplace] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Title selector - wait for it to ensure React has mounted
                title_xpath = 'xpath=/html/body/div/div[1]/div/div/div/div[1]/div[2]/div/h5'
                try:
                    await page.wait_for_selector(title_xpath, timeout=30000)
                except (PlaywrightError, asyncio.TimeoutError):
                    logger.warning("[SurplusMarketplace] Selector timeout at %s", url)
                    return None

                await asyncio.sleep(3) # Wait for hydration

                async def get_text_safe(xpath: str) -> str:
                    try:
                        loc = page.locator(xpath).first
                        if await loc.count() > 0:
                            return (await loc.inner_text()).strip()
                    except (PlaywrightError, Exception):
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

                # 6. Specific End Time
                ends_at_xpath = 'xpath=//*[contains(text(), "Ends at:")]'
                ends_at_text = await get_text_safe(ends_at_xpath)

                # Parse Price
                current_bid = 0.0
                if price_text:
                    clean_bid = re.sub(r'[^\d.]', '', price_text)
                    if clean_bid:
                        current_bid = float(clean_bid)

                # Parse Location
                city, state = "Unknown", "Unknown"
                if location and ',' in location:
                    parts = location.split(',')
                    city = parts[0].strip()
                    state = parts[1].strip() if len(parts) > 1 else "Unknown"

                # Parse Buyer Premium
                premium_value = None
                if buyer_premium:
                    try:
                        premium_value = float(re.sub(r'[^\d.]', '', buyer_premium))
                    except ValueError:
                        pass

                # Date Parsing
                closing_time_iso = None
                now_utc = datetime.now(timezone.utc)

                if ends_at_text and "Ends at:" in ends_at_text:
                    try:
                        from dateutil import parser as date_parser
                        date_str = ends_at_text.replace("Ends at:", "").strip()
                        dt = date_parser.parse(date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone(timedelta(hours=-6))) # Assume Central
                        closing_time_iso = dt.isoformat()
                    except (ImportError, ValueError):
                        pass

                if not closing_time_iso and time_left:
                    try:
                        clean_time = time_left.replace(":", " ").strip()
                        d_match = re.search(r'(\d+)d', clean_time)
                        h_match = re.search(r'(\d+)h', clean_time)
                        m_match = re.search(r'(\d+)m', clean_time)
                        s_match = re.search(r'(\d+)s', clean_time)

                        d = int(d_match.group(1)) if d_match else 0
                        h = int(h_match.group(1)) if h_match else 0
                        m = int(m_match.group(1)) if m_match else 0
                        s = int(s_match.group(1)) if s_match else 0

                        if any([d, h, m, s]):
                            closing_time_iso = (now_utc + timedelta(days=d, hours=h, minutes=m, seconds=s)).isoformat()
                    except ValueError:
                        pass

                return {
                    "item_name": item_name[:200] if item_name else "Unknown",
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "time_remaining_str": time_left or "",
                    "premium_percentage": premium_value,
                    "closing_time": closing_time_iso,
                    "website_name": "Surplus Marketplace",
                    "status": "active"
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[SurplusMarketplace] Error: %s", e)
                return None
            finally:
                await browser.close()
