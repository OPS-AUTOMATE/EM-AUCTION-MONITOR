"""
DotMed Adapter Module.
Handles scraping for DotMed listings with Cloudflare bypass logic and stealth browser techniques.
"""
import asyncio
import logging
import re
import random
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class DotMedAdapter(BaseAuctionAdapter):
    """
    Hardened DotMed Adapter (Tier B - Playwright).
    Since DotMed often blocks bots, this uses stealth scripts and a sophisticated
    Cloudflare challenge bypass loop.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Enhanced Stealth Launch Options
            launch_opts: Dict[str, Any] = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-notifications",
                    "--no-first-run",
                ]
            }
            
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[DotMed] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US,en",
            )
            page = await context.new_page()
            
            # Inject stealth script to mimic a real browser
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)
            
            async def get_text_safe(selector: str) -> str:
                try:
                    loc = page.locator(selector).first
                    if await loc.count() > 0:
                        return (await loc.inner_text()).strip()
                except (PlaywrightError, Exception):
                    pass
                return ""

            try:
                logger.info("[DotMed] Fetching: %s", url)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except (PlaywrightError, asyncio.TimeoutError) as e:
                    logger.warning("[DotMed] Page load timeout/error: %s", e)

                # 🛡️ CLOUDFLARE BYPASS LOGIC 🛡️
                page_title = await page.title()
                if any(k in page_title for k in ["Just a moment", "Attention Required", "Cloudflare"]):
                    logger.warning("[DotMed] Cloudflare Challenge Detected. Attempting solve...")
                    await asyncio.sleep(random.uniform(4, 6))
                    
                    start_time = asyncio.get_event_loop().time()
                    while (asyncio.get_event_loop().time() - start_time) < 40: 
                        solved = False
                        for frame in page.frames:
                            if any(k in frame.url for k in ["cloudflare", "challenge"]):
                                try:
                                    # Attempt generic click on frame body
                                    body_el = frame.locator("body").first
                                    if await body_el.count() > 0:
                                        box = await body_el.bounding_box()
                                        if box and box['width'] > 0:
                                            x = box['x'] + (box['width'] / 2) + random.uniform(-10, 10)
                                            y = box['y'] + (box['height'] / 2) + random.uniform(-10, 10)
                                            await page.mouse.move(x, y)
                                            await asyncio.sleep(0.1)
                                            await page.mouse.down()
                                            await page.mouse.up()
                                            solved = True
                                            break
                                except (PlaywrightError, Exception):
                                    continue
                        
                        if solved:
                             await asyncio.sleep(4)
                             if "Just a moment" not in await page.title():
                                 break
                        await asyncio.sleep(2)

                # 1. Item Name
                item_name = await get_text_safe('div.listing_title_info > h3')
                if not item_name:
                    item_name = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[1]/div[1]/div/div[2]/div[1]/h3')
                if not item_name:
                    item_name = await get_text_safe('h1')

                # 2. Starting Bid
                starting_bid_text = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[1]/div[1]/div/div[2]/div[1]/ul/li[1]/h4')
                current_bid = 0.0
                if starting_bid_text:
                    clean_bid = re.sub(r'[^\d.]', '', starting_bid_text)
                    if clean_bid:
                        current_bid = float(clean_bid)
                
                # 3. Time Remaining
                time_left = await get_text_safe('#countdowncontainer')
                if not time_left:
                    time_left = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[1]/div[1]/div/div[2]/div[1]/ul/li[3]/span[2]')

                # 4. Location
                location = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[2]/div/div[1]/div[2]/div/p[3]')
                city, state = "Unknown", "Unknown"
                if location:
                    loc_text = location.replace("Location:", "").strip()
                    first_line = loc_text.split('\n')[0]
                    if "," in first_line:
                         parts = first_line.split(",")
                         city = parts[0].strip()
                         state = parts[1].strip() if len(parts) > 1 else "Unknown"

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "time_remaining_str": time_left.strip(),
                    "website_name": "DotMed",
                    "status": "active"
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[DotMed] Critical Error: %s", e)
                return None
            finally:
                await browser.close()
