import logging
import re
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class BidspotterAdapter(BaseAuctionAdapter):
    """
    Hardened Bidspotter Adapter (Tier B - SSR HTML).
    Uses strict XPaths provided for verified layouts.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Prepare Launch options (Proxy support)
            launch_opts = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info(f"[Bidspotter] Using Proxy: {proxy_conf['server']}")

            browser = await p.chromium.launch(**launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # OPTIMIZATION: Block heavy resources
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
                else route.continue_())
            
            try:
                logger.info(f"[Bidspotter] Fetching: {url}")
                await page.goto(url, wait_until="load", timeout=30000)
                await asyncio.sleep(5) # Wait for JS to settle

                # 1. Title
                # XPath: /html/body/div[1]/main/div/div[1]/div/div[2]/div/h1
                item_name = "Unknown Item"
                try:
                    title_el = page.locator("xpath=/html/body/div[1]/main/div/div[1]/div/div[2]/div/h1")
                    if await title_el.count() > 0:
                        item_name = await title_el.first.inner_text()
                except Exception as e:
                    logger.warning(f"[Bidspotter] Title extract failed: {e}")

                # 2. Current Bid / Price
                # XPath: /html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[1]/span
                current_bid = 0.0
                try:
                    price_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[1]/span"
                    price_el = page.locator(f"xpath={price_xpath}")
                    if await price_el.count() > 0:
                        bid_text = await price_el.first.inner_text()
                        # Clean: "3,200" -> 3200.0
                        clean_text = re.sub(r'[^\d.]', '', bid_text)
                        if clean_text:
                            current_bid = float(clean_text)
                except Exception as e:
                    logger.warning(f"[Bidspotter] Price extract failed: {e}")

                # 3. Location
                # XPath: /html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[2]/div[2]/strong/span
                # Logic: If contains "VAT REFUND", set to "Unknown, Unknown"
                city, state = "Unknown", "Unknown"
                try:
                    loc_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[2]/div[2]/strong/span"
                    loc_el = page.locator(f"xpath={loc_xpath}")
                    if await loc_el.count() > 0:
                        loc_text = await loc_el.first.inner_text()
                        if "VAT REFUND" in loc_text.upper():
                            city, state = "Unknown", "Unknown"
                        else:
                            # Try to split by comma if format is "City, State"
                            parts = loc_text.split(",")
                            if len(parts) >= 2:
                                city = parts[0].strip()
                                state = parts[1].strip()
                            else:
                                city = loc_text.strip()
                except Exception as e:
                    logger.warning(f"[Bidspotter] Location extract failed: {e}")

                # 4. End Time (GMT to PKT)
                # XPath: /html/body/div[2]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[1]/div[2]/div[2]/div/div/span
                # Note: The div[1] or div[2] at root might vary, using loose path for body/main
                end_time_pkt = None
                try:
                    # Original Strict Path (User Provided)
                    time_xpath = "/html/body/div[2]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[1]/div[2]/div[2]/div/div/span"
                    time_el = page.locator(f"xpath={time_xpath}")
                    
                    if await time_el.count() == 0:
                        # Fallback for div[1] variation
                        time_xpath = "/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[1]/div[2]/div[2]/div/div/span"
                        time_el = page.locator(f"xpath={time_xpath}")

                    if await time_el.count() > 0:
                        # Try to get datetime attribute first, or inner text
                        # Usually <time datetime="...">
                        dt_str = await time_el.first.get_attribute("datetime")
                        if not dt_str:
                            dt_str = await time_el.first.inner_text()
                        
                        # Parsing logic
                        # 1. Try ISO format (preferred from datetime attr)
                        dt = None
                        if dt_str:
                            raw = dt_str.strip()
                            # Handle quirks like '2026-01-31T01-00-00Z' (hyphens in time)
                            if 'T' in raw:
                                # Normalizing ISO-like strings
                                # Replace hyphens in time part with colons if needed: T01-00-00 -> T01:00:00
                                parts = raw.split('T')
                                if len(parts) == 2:
                                    date_part = parts[0]
                                    time_part = parts[1].replace('Z', '')
                                    # If time part looks like 01-00-00, fix it
                                    if '-' in time_part and ':' not in time_part:
                                        time_part = time_part.replace('-', ':')
                                    
                                    clean_iso = f"{date_part}T{time_part}"
                                    # Append +00:00 if it was Z or implied UTC
                                    if 'Z' in raw or raw.endswith('00'): 
                                        clean_iso += "+00:00"
                                    
                                    try:
                                        dt = datetime.fromisoformat(clean_iso)
                                    except ValueError:
                                        pass

                        # 2. Try Text Format with variable Timezones (GMT, CT, ET, PT, UTC)
                        if not dt and dt_str:
                            try:
                                raw_text = dt_str.strip()
                                # Detect known timezones map to offset
                                tz_map = {
                                    "GMT": 0, "UTC": 0, "Z": 0,
                                    "EST": -5, "EDT": -4, "ET": -5,
                                    "CST": -6, "CDT": -5, "CT": -6,
                                    "MST": -7, "MDT": -6, "MT": -7,
                                    "PST": -8, "PDT": -7, "PT": -8
                                }
                                
                                offset_hours = 0
                                found_tz = None
                                
                                # Check for timezone string in text
                                for tz_name, offset in tz_map.items():
                                    if tz_name in raw_text:
                                        offset_hours = offset
                                        found_tz = tz_name
                                        raw_text = raw_text.replace(tz_name, "").strip()
                                        break
                                
                                # Try parsing the cleaned text
                                # Formats: "Jan 29, 2026 10:11pm", "Jan 29, 2026 10:11 PM"
                                for fmt in ["%b %d, %Y %I:%M%p", "%b %d, %Y %I:%M %p", "%Y-%m-%d %H:%M:%S"]:
                                    try:
                                        dt = datetime.strptime(raw_text, fmt)
                                        break
                                    except ValueError:
                                        continue

                                # Apply timezone info
                                if dt:
                                    # Create timezone with offset
                                    dt_tz = timezone(timedelta(hours=offset_hours))
                                    dt = dt.replace(tzinfo=dt_tz)
                                    
                            except Exception as ve:
                                logger.warning(f"[Bidspotter] Date parse warning: {ve}")

                        if dt:
                            # Convert to PKT (UTC+5)
                            pkt_tz = timezone(timedelta(hours=5))
                            pkt_dt = dt.astimezone(pkt_tz)
                            # Return ISO format for DB compatibility
                            end_time_pkt = pkt_dt.isoformat()

                except Exception as e:
                    logger.warning(f"[Bidspotter] End time extract failed: {e}")

                # 5. Status check
                # Simple check for "Auction Closed" text anywhere or sold state
                status = "active"
                content = await page.content()
                if "Auction Closed" in content or "Bidding has ended" in content:
                    status = "expired"

                # VALIDATION: Critical fields
                if not end_time_pkt:
                    logger.warning(f"[Bidspotter] Failed to parse closing time for {url}. Skipping to avoid DB crash.")
                    return None

                return {
                    "item_name": item_name.strip()[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "closing_time": end_time_pkt,
                    "website_name": "BidSpotter",
                    "status": status
                }

            except Exception as e:
                logger.error(f"[Bidspotter] Critical Error: {e}")
                return None
            finally:
                await browser.close()
