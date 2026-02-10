import asyncio
import logging
import re
import random
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class DotMedAdapter(BaseAuctionAdapter):
    """
    Hardened DotMed Adapter (Tier B - Playwright).
    Since DotMed blocks direct HTTP (403), we use a browser with stealth headers.
    Uses robust CSS selectors derived from user's input as primary, falling back to XPaths.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy Rotation
            launch_opts = {
                "headless": True,
                "channel": "chrome",
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
                logger.info(f"[DotMed] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1,
                locale="en-US,en",
                timezone_id="America/New_York",
                permissions=["geolocation"],
            )
            page = await context.new_page()
            
            # Inject stealth script to hide webdriver property
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
            """)
            
            # Helper inside
            async def get_text_safe(selector: str) -> str:
                try:
                    if await page.locator(selector).count() > 0:
                        txt = await page.locator(selector).first.inner_text()
                        return txt
                except:
                    pass
                return ""

            try:
                logger.info(f"[DotMed] Fetching: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except Exception as e:
                    logger.warning(f"[DotMed] Page load timeout/error: {e}")

                # Check for Cloudflare Block
                page_title = await page.title()
                logger.info(f"[DotMed] Page Title: {page_title}")
                
               # Cloudflare titles often include "Just a moment..." or "Attention Required"
                if "Just a moment" in page_title or "Attention Required" in page_title or "Cloudflare" in page_title:
                    logger.warning("[DotMed] Cloudflare Challenge Detected. Attempting to solve with stealth...")
                    
                    # Wait for widget to load
                    await asyncio.sleep(random.uniform(4, 6))
                    
                    # Try to find the Turnstile iframe/checkbox
                    solved = False
                    start_time = asyncio.get_event_loop().time()
                    
                    while (asyncio.get_event_loop().time() - start_time) < 40: 
                        frames = page.frames
                        for frame in frames:
                            url_frame = frame.url
                            if "cloudflare" in url_frame or "challenge" in url_frame:
                                logger.info(f"[DotMed] Checking challenge frame: {url_frame}")
                                
                                try:
                                    # 1. Try generic click on body if it's small/contained
                                    # Often clicking the frame itself triggers the verify
                                    body_el = frame.locator("body").first
                                    if await body_el.count() > 0:
                                        box = await body_el.bounding_box()
                                        if box and box['width'] > 0 and box['height'] > 0:
                                             # Click slightly off-center to mimic human slightly
                                            x = box['x'] + (box['width'] / 2) + random.uniform(-10, 10)
                                            y = box['y'] + (box['height'] / 2) + random.uniform(-10, 10)
                                            logger.info(f"[DotMed] Clicking frame at ({x},{y})")
                                            await page.mouse.move(x, y)
                                            await asyncio.sleep(random.uniform(0.1, 0.3))
                                            await page.mouse.down()
                                            await asyncio.sleep(random.uniform(0.05, 0.15))
                                            await page.mouse.up()
                                            solved = True
                                            break

                                    # 2. Try specific checkbox selector
                                    checkbox = frame.locator("input[type='checkbox']").first
                                    if await checkbox.count() > 0:
                                        logger.info("[DotMed] Clicking Turnstile checkbox...")
                                        await checkbox.click(force=True)
                                        solved = True
                                        break
                                    
                                    # 3. Wrapper check
                                    wrapper = frame.locator(".ctp-checkbox-label, label").first
                                    if await wrapper.count() > 0:
                                        logger.info("[DotMed] Clicking Turnstile label...")
                                        await wrapper.click(force=True)
                                        solved = True
                                        break
                                        
                                except Exception as e:
                                    logger.debug(f"[DotMed] Frame interaction error: {e}")
                        
                        if solved:
                             # Wait a bit after clicking to see if reload happens
                             logger.info("[DotMed] Click action sent. Waiting...")
                             await asyncio.sleep(4)
                             # Check if Title changed or navigated away
                             current_title = await page.title()
                             if "Just a moment" not in current_title and "Attention Required" not in current_title and "Cloudflare" not in current_title:
                                 logger.info(f"[DotMed] Title changed to: {current_title}")
                                 break
                             # If still stuck, maybe click failed or need verify button
                             # Continue loop
                        
                        await asyncio.sleep(2)

                    # Final check
                    page_title = await page.title()
                    if "Just a moment" in page_title or "Attention Required" in page_title:
                        logger.error("[DotMed] Still stuck. Dumping HTML for analysis.")
                        
                        # Dump HTML to file for inspection
                        html_content = await page.content()
                        debug_file = "dotmed_cloudflare_dump.html"
                        with open(debug_file, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        logger.info(f"[DotMed] Saved Cloudflare page HTML to {debug_file}")

                        return {"status": "blocked", "website_name": "DotMed", "error": f"Cloudflare loop. HTML dumped to {debug_file}"}
                    else:
                        logger.info("[DotMed] Challenge seemingly passed.")


                # 1. Item Name
                # User provided: body > div.container > ... > div.listing_title_info > h3
                item_name = await get_text_safe('div.listing_title_info > h3')
                if not item_name:
                    item_name = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[1]/div[1]/div/div[2]/div[1]/h3')
                if not item_name:
                     item_name = await get_text_safe('body > div.container > div:nth-child(3) > div > div.row > div.col-12.col-sm-12.col-lg-9 > div > div.product_cart_description.mb-4.mb-lg-0.col-12.col-lg-5.order-0.order-lg-1 > div.listing_title_info > h3')
                if not item_name:
                     item_name = await get_text_safe('h1')

                # 2. Starting Bid
                starting_bid_text = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[1]/div[1]/div/div[2]/div[1]/ul/li[1]/h4')
                if not starting_bid_text:
                     starting_bid_text = await get_text_safe('.listing_title_info + div ul li:nth-child(1) h4')

                # 3. Time Remaining
                time_left = await get_text_safe('#countdowncontainer')
                if not time_left:
                    time_left = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[1]/div[1]/div/div[2]/div[1]/ul/li[3]/span[2]')

                # 4. Bid Closing Date
                bid_closes = await get_text_safe('.listing_title_info + div ul li:nth-child(4)')
                if not bid_closes:
                    bid_closes = await get_text_safe('body > div.container > div:nth-child(3) > div > div.row > div.col-12.col-sm-12.col-lg-9 > div > div.product_cart_description.mb-4.mb-lg-0.col-12.col-lg-5.order-0.order-lg-1 > div.listing_title_info > ul > li:nth-child(3)')
                
                # 5. Fee
                fee = await get_text_safe('body > div.container > div:nth-child(3) > div > div.row > div.col-12.col-sm-12.col-lg-9 > div > div.product_cart_description.mb-4.mb-lg-0.col-12.col-lg-5.order-0.order-lg-1 > table > tbody > tr:nth-child(3) > td:nth-child(2)')
                if not fee:
                    fee = await get_text_safe('.product_cart_description table tr:nth-child(3) td:nth-child(2)')

                # 6. Location
                location = await get_text_safe('xpath=/html/body/div[5]/div[2]/div/div[2]/div/div[1]/div[2]/div/p[3]')
                if not location:
                    location = await get_text_safe('#desc_tab > div.additional_info > div > p:nth-child(4)')
                if not location:
                     location = await get_text_safe('.product_cart_description ul li:first-child')

                # Processing extracted data
                current_bid = 0.0
                try:
                    clean_bid = re.sub(r'[^\d.]', '', starting_bid_text)
                    if clean_bid:
                        current_bid = float(clean_bid)
                except: 
                    pass
                
                # Parse Location logic
                city, state = "Unknown", "Unknown"
                if location:
                    loc_text = location.replace("Location:", "")
                    lines = loc_text.split('\n')
                    target_line = lines[0]
                    for line in lines:
                        if "," in line:
                            target_line = line
                            break
                    
                    if "," in target_line:
                         parts = target_line.split(",")
                         city = parts[0].strip()
                         if len(parts) > 1:
                            state = parts[1].strip()

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "time_remaining_str": time_left.strip(),
                    "website_name": "DotMed",
                    "status": "active"
                }

            except Exception as e:
                logger.error(f"[DotMed] Error: {e}")
                return None
            finally:
                try:
                    await browser.close()
                except:
                    pass
