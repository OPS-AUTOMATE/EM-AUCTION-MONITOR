"""
Centurion Adapter Module.
Handles medical equipment auctions, session persistence, and authenticated scraping.
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class CenturionAdapter(BaseAuctionAdapter):
    """
    Hardened Centurion Adapter (Tier B).
    Includes session persistence (storage_state) and automated login flow.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            # Proxy & Browser Configuration
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[Centurion] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            
            storage_path = "centurion_session.json"
            context_args = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080},
            }
            if os.path.exists(storage_path):
                context_args["storage_state"] = storage_path

            context = await browser.new_context(**context_args)
            page = await context.new_page()

            # Optimization: Block heavy media
            await page.route("**/*", lambda route: route.abort() 
                if route.request.resource_type in ["image", "media", "font"] 
                else route.continue_())

            async def perform_login():
                user = os.getenv("CENTURION_USERNAME")
                pw = os.getenv("CENTURION_PASSWORD")
                if not user or not pw:
                    logger.warning("[Centurion] Missing credentials for login.")
                    return False
                
                try:
                    logger.info("[Centurion] Attempting login...")
                    await page.goto("https://bid.centurionservice.com/login", wait_until="domcontentloaded")
                    await page.fill("input[type='email']", user)
                    await page.fill("input[type='password']", pw)
                    await page.click("input[type='submit']")
                    await page.wait_for_load_state("networkidle")
                    
                    if await page.locator("text='Sign Out'").count() > 0:
                        await context.storage_state(path=storage_path)
                        return True
                except (PlaywrightError, Exception) as e:
                    logger.error("[Centurion] Login failed: %s", e)
                return False

            try:
                logger.info("[Centurion] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)

                # Check if login is needed
                if await page.locator("text='Sign in to bid'").count() > 0:
                    if await perform_login():
                        await page.goto(url, wait_until="domcontentloaded")

                # Data Extraction
                async def get_text(sel: str) -> str:
                    try:
                        loc = page.locator(sel).first
                        return (await loc.inner_text()).strip() if await loc.count() > 0 else ""
                    except: return ""

                item_name = await get_text("h1") or "Unknown Item"
                
                # Bid Extraction
                bid_text = await get_text("#currentBid")
                current_bid = float(re.sub(r'[^\d.]', '', bid_text)) if bid_text and re.sub(r'[^\d.]', '', bid_text) else 0.0

                # Status & Time
                status = "active"
                time_text = (await get_text("span.time-left")).lower()
                closing_time_iso = None
                
                if "lot closed" in (await page.content()).lower():
                    status = "expired"
                elif time_text:
                    d, h, m, s = 0, 0, 0, 0
                    if mt := re.search(r'(\d+)\s*d', time_text): d = int(mt.group(1))
                    if mt := re.search(r'(\d+)\s*h', time_text): h = int(mt.group(1))
                    if mt := re.search(r'(\d+)\s*m', time_text): m = int(mt.group(1))
                    total_s = (d * 86400) + (h * 3600) + (m * 60)
                    closing_time_iso = (datetime.now(timezone.utc) + timedelta(seconds=total_s)).isoformat()

                # Location Fallback
                city, state = "Unknown", "Unknown"
                # Simple logic for common Centurion locations
                body_text = await page.inner_text("body")
                if "chicago" in body_text.lower(): city, state = "Chicago", "IL"
                elif "phoenix" in body_text.lower(): city, state = "Phoenix", "AZ"

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "city": city,
                    "state": state,
                    "total_bidders": 0,
                    "closing_time": closing_time_iso,
                    "website_name": "Centurion Service",
                    "status": status
                }

            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[Centurion] Fetch failure: %s", e)
                return None
            finally:
                await browser.close()
