"""
GSA Adapter Module.
Combines fast API fetching with browser-based interception for GSA Auctions.
"""
import asyncio
import logging
import random
import re
from datetime import datetime
from typing import Optional, Dict, Any

from playwright.async_api import async_playwright, Error as PlaywrightError
from utils.browser import launch_browser

from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class GsaAdapter(BaseAuctionAdapter):
    """
    Hardened GSA Adapter.
    Uses API fetch with browser fallback for high-reliability medical equipment scraping.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        # 1. API Mode Fast-Path
        id_match = re.search(r"(?:suid=|preview/|auctions/preview/)(\d+|[A-Z0-9]+)", url, re.I)
        if id_match:
            suid = id_match.group(1)
            logger.info("[GSA] Attempting API fetch for ID: %s", suid)
            data = await self._fetch_via_api(suid)
            if data: return data

        # 2. Browser Mode Fallback
        return await self._fetch_via_browser(url)

    async def _fetch_via_api(self, suid: str) -> Optional[Dict[str, Any]]:
        import httpx
        api_url = f"https://www.ppms.gov/gw/auction/ppms/api/v1/auctions/getAuction/{suid}"
        
        proxy_conf = self.get_proxy_config()
        proxy_url = None
        if proxy_conf:
            p_server = proxy_conf['server'].replace("http://", "").replace("https://", "")
            proxy_url = f"http://{proxy_conf['username']}:{proxy_conf['password']}@{p_server}"

        try:
            async with httpx.AsyncClient(timeout=15.0, verify=False, proxy=proxy_url) as client:
                resp = await client.get(api_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    "Origin": "https://gsaauctions.gov",
                    "Referer": "https://gsaauctions.gov/"
                })
                if resp.status_code == 200:
                    data = resp.json()
                    item_name = data.get("lotName") or data.get("itemName") or "GSA Item"
                    loc = data.get("location") or {}
                    
                    return {
                        "item_name": str(item_name).strip()[:200],
                        "current_bid": float(str(data.get("currentBid", 0)).replace(",", "")),
                        "total_bidders": int(data.get("numberOfBidders", 0)),
                        "closing_time": data.get("endDate"),
                        "city": loc.get("city", "Unknown"),
                        "state": loc.get("state", "Unknown"),
                        "website_name": "GSA Auctions",
                        "status": "active"
                    }
        except Exception as e:
            logger.warning("[GSA-API] API Fetch failed: %s", e)
        return None

    async def _fetch_via_browser(self, url: str) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            launch_opts: Dict[str, Any] = {"headless": True}
            proxy_conf = self.get_proxy_config()
            if proxy_conf:
                launch_opts["proxy"] = proxy_conf
                logger.info("[GSA-Browser] Using Proxy: %s", proxy_conf['server'])

            browser = await launch_browser(p, **launch_opts)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            captured_data = {}
            async def handle_response(response):
                try:
                    if "getAuction" in response.url and response.status == 200:
                        captured_data.update(await response.json())
                except: pass

            page.on("response", handle_response)

            try:
                logger.info("[GSA-Browser] Fetching: %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for interception
                for _ in range(20):
                    if captured_data: break
                    await asyncio.sleep(0.5)

                if captured_data:
                    data = captured_data
                    item_name = data.get("lotName") or data.get("itemName") or "GSA Item"
                    loc = data.get("location") or {}
                    return {
                        "item_name": str(item_name).strip()[:200],
                        "current_bid": float(str(data.get("currentBid", 0)).replace(",", "")),
                        "total_bidders": int(data.get("numberOfBidders", 0)),
                        "closing_time": data.get("endDate"),
                        "city": loc.get("city", "Unknown"),
                        "state": loc.get("state", "Unknown"),
                        "website_name": "GSA Auctions",
                        "status": "active"
                    }
            except (PlaywrightError, asyncio.TimeoutError) as e:
                logger.error("[GSA-Browser] Fetch failure: %s", e)
            finally:
                await browser.close()
        return None
