import asyncio
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
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

                # 6. Specific End Time (Experimental)
                ends_at_xpath = 'xpath=//*[contains(text(), "Ends at:")]'
                ends_at_text = await get_text_safe(ends_at_xpath)

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
                    parts = location.split(',')
                    if len(parts) >= 2:
                        city = parts[0].strip()
                        state = parts[1].strip()

                # Parse Buyer Premium
                premium_value = None
                if buyer_premium:
                    try:
                        premium_value = float(re.sub(r'[^\d.]', '', buyer_premium.strip()))
                    except:
                        pass

                # --- ADVANCED DATE PARSING ---
                closing_time_iso = None
                now_utc = datetime.now(timezone.utc)

                # Strategy A: Parse "Ends at: MM/DD/YY - HH:mm"
                if ends_at_text and "Ends at:" in ends_at_text:
                    try:
                        date_str = ends_at_text.replace("Ends at:", "").strip()
                        # Format: 03/13/26 - 22:13
                        # We assume Central Time (CST/CDT) as per site location, but parse it
                        dt = date_parser.parse(date_str)
                        # If no timezone, assume US/Central (approx -6)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone(timedelta(hours=-6)))
                        closing_time_iso = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"[SurplusMarketplace] Static date parse failed: {e}")

                # Strategy B: Parse Countdown Fallback (e.g. "3d 21h:1m 47s")
                if not closing_time_iso and time_left:
                    try:
                        # Normalize string
                        clean_time = time_left.replace(":", " ").strip()
                        days = re.search(r'(\d+)d', clean_time)
                        hours = re.search(r'(\d+)h', clean_time)
                        mins = re.search(r'(\d+)m', clean_time)
                        secs = re.search(r'(\d+)s', clean_time)

                        d = int(days.group(1)) if days else 0
                        h = int(hours.group(1)) if hours else 0
                        m = int(mins.group(1)) if mins else 0
                        s = int(secs.group(1)) if secs else 0

                        if d or h or m or s:
                            dt = now_utc + timedelta(days=d, hours=h, minutes=m, seconds=s)
                            closing_time_iso = dt.isoformat()
                    except Exception as e:
                        logger.warning(f"[SurplusMarketplace] Countdown parse failed: {e}")

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "time_remaining_str": time_left.strip(),
                    "premium_percentage": premium_value,
                    "closing_time": closing_time_iso,
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
