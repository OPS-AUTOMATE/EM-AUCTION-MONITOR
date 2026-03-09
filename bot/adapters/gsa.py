import asyncio
import logging
import re
from datetime import datetime
import pytz
import random
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright
import playwright_stealth
from .base_adapter import BaseAuctionAdapter
from utils.proxy_manager import ProxyManager
import urllib.parse

logger = logging.getLogger(__name__)

class GsaAdapter(BaseAuctionAdapter):
    """
    Hardened GSA Adapter using User-Defined XPaths and Patterns.
    Combines API speed with browser precision.
    """

    def _get_stealth_profile(self) -> Dict[str, Any]:
        """Returns a randomized browser/device profile."""
        is_mobile = random.choice([True, False])
        if is_mobile:
            # High-end Mobile (iPhone 15 Pro style)
            return {
                "is_mobile": True,
                "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
                "viewport": {"width": 393, "height": 852},
                "headers": {
                    "Sec-CH-UA-Mobile": "?1",
                    "Sec-CH-UA-Platform": '"iOS"',
                    "Sec-CH-UA": '"Safari";v="17", "Not:A-Brand";v="8"',
                }
            }
        else:
            # Premium Desktop (Chrome 123)
            return {
                "is_mobile": False,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "viewport": {"width": random.randint(1440, 1920), "height": random.randint(900, 1080)},
                "headers": {
                    "Sec-CH-UA-Mobile": "?0",
                    "Sec-CH-UA-Platform": '"Windows"',
                    "Sec-CH-UA": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
                }
            }

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        # 1. API Mode (SUID or Preview ID)
        suid_match = re.search(r"[?&]suid=([A-Z0-9]+)", url, re.I)
        preview_match = re.search(r"/(?:preview|auctions/preview)/(\d+)", url, re.I)
        
        suid = None
        if suid_match:
            suid = suid_match.group(1)
        elif preview_match:
            # GSA's preview ID often works as SUID for API calls
            suid = preview_match.group(1) 

        if suid:
            logger.info(f"[GSA] Detected ID: {suid}, attempting API fetch.")
            data = await self._fetch_via_api(suid, url)
            if data: return data

        # 2. Browser Mode (Fallback)
        return await self._fetch_via_browser(url)

    async def _fetch_via_api(self, suid: str, original_url: str) -> Optional[Dict[str, Any]]:
        import httpx
        # New Verified API Endpoint
        api_url = f"https://www.ppms.gov/gw/auction/ppms/api/v1/auctions/getAuction/{suid}"
        logger.info(f"[GSA-API] Fetching: {api_url}")

        async def _do_api_request(p_url: str, p_config: Optional[str], profile: Dict[str, Any]) -> Optional[httpx.Response]:
            try:
                # Enhanced headers to mimic a premium browser session
                async with httpx.AsyncClient(timeout=20.0, verify=False, proxy=p_config) as client:
                    headers = {
                        "User-Agent": profile["ua"],
                        "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Origin": "https://gsaauctions.gov",
                        "Referer": "https://gsaauctions.gov/",
                        "DNT": "1",
                        "Sec-Fetch-Dest": "empty",
                        "Sec-Fetch-Mode": "cors",
                        "Sec-Fetch-Site": "cross-site",
                        "Sec-Fetch-User": "?1",
                        "Upgrade-Insecure-Requests": "1",
                        **profile["headers"]
                    }
                    return await client.get(p_url, headers=headers)
            except Exception as e:
                logger.error(f"[GSA-API] Request Attempt failed: {e}")
                return None

        # --- ROTATION LOGIC ---
        all_raw_proxies = ProxyManager.get_all_proxies()
        proxies_to_try = []
        
        # 1. First try the sticky selection
        proxy_conf = self.get_proxy_config()
        if proxy_conf:
            proxies_to_try.append(proxy_conf)
            
        # 2. Add 2 more random ones from the pool
        other_proxies = [p for p in all_raw_proxies if proxy_conf and p not in proxy_conf.get("server", "")]
        if other_proxies:
            random.shuffle(other_proxies)
            for p_str in other_proxies[:2]:
                proxies_to_try.append(ProxyManager.parse_proxy_to_config(p_str))

        if not proxies_to_try:
            # If no proxies, try Direct
            proxies_to_try = [None]

        response = None
        for i, config in enumerate(proxies_to_try):
            p_url = None
            if config:
                p_user = config.get("username")
                p_pass = config.get("password")
                p_server = config.get("server", "").replace("http://", "").replace("https://", "")
                if p_user and p_pass:
                    p_url = f"http://{urllib.parse.quote(p_user)}:{urllib.parse.quote(p_pass)}@{p_server}"
                else:
                    p_url = f"http://{p_server}"
            
            # Select a random profile for each attempt
            profile = self._get_stealth_profile()
            logger.info(f"[GSA-API] Attempt {i+1}/{len(proxies_to_try)} using: {config.get('server') if config else 'DIRECT'} | Profile: {'Mobile' if profile['is_mobile'] else 'Desktop'}")
            
            response = await _do_api_request(api_url, p_url, profile)
            if response and response.status_code == 200:
                break
            logger.warning(f"[GSA-API] Attempt {i+1} failed ({getattr(response, 'status_code', 'ERR')}).")

        # FALLBACK: If all proxies failed, try Direct
        if (not response or response.status_code >= 400) and any(proxies_to_try):
            logger.warning("[GSA-API] All proxies failed/blocked. Retrying DIRECT...")
            response = await _do_api_request(api_url, None, self._get_stealth_profile())

        try:
            if response and response.status_code == 200:
                logger.info(f"[GSA-API] Status: {response.status_code}")
                try:
                    data = response.json()
                    # New ppms.gov API response mapping
                    item_name = data.get("lotName") or data.get("itemName") or "GSA Item"
                    
                    if not item_name or "403" in str(item_name):
                        logger.warning(f"[GSA-API] Blocked or empty name detected: {item_name}")
                        return None
                        
                    # Extract location details
                    loc = data.get("location") or {}
                    city = loc.get("city") or data.get("city", "Unknown")
                    state = loc.get("state") or data.get("state", "Unknown")
                    
                    # Extract closing time
                    closing_time = data.get("endDate") or data.get("closingTime") or data.get("auctionEndTime")
                    
                    return {
                        "item_name": str(item_name).strip()[:200],
                        "current_bid": float(str(data.get("currentBid", 0)).replace(",", "")),
                        "total_bidders": int(data.get("numberOfBidders") or data.get("bidderCount", 0)),
                        "closing_time": closing_time,
                        "city": city,
                        "state": state,
                        "website_name": "GSA Auctions",
                        "status": "active"
                    }
                except Exception as e:
                    logger.error(f"[GSA-API] JSON Parse Error: {e}")
                    return None
            elif response and response.status_code == 403:
                logger.warning("[GSA-API] 403 Forbidden - Falling back to browser.")
                return None
        except Exception as e:
             logger.error(f"[GSA-API] Request Failed: {e}")
             return None
        return None

    async def _is_proxy_healthy(self, proxy_url: str) -> bool:
        """Check if proxy supports HTTPS CONNECT and is alive."""
        import httpx
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=5.0, verify=False) as client:
                resp = await client.get("https://www.google.com", follow_redirects=True)
                return resp.status_code == 200
        except Exception:
            return False

    async def _inject_hardened_fingerprint(self, page):
        """Injects a script to randomize fingerprinting signals."""
        fingerprint_script = f"""
            (() => {{
                // Randomize Canvas
                const originalGetContext = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type, attributes) {{
                    const context = originalGetContext.call(this, type, attributes);
                    if (type === '2d') {{
                        const originalGetImageData = context.getImageData;
                        context.getImageData = function(x, y, w, h) {{
                            const imageData = originalGetImageData.call(this, x, y, w, h);
                            for (let i = 0; i < imageData.data.length; i += 4) {{
                                imageData.data[i] = imageData.data[i] + (Math.random() > 0.5 ? 1 : -1);
                            }}
                            return imageData;
                        }};
                    }}
                    return context;
                }};
                // Randomize Screen geometry
                Object.defineProperty(window.screen, 'width', {{ get: () => {random.randint(1600, 2560)} }});
                Object.defineProperty(window.screen, 'height', {{ get: () => {random.randint(900, 1440)} }});
            }})();
        """
        await page.add_init_script(fingerprint_script)

    async def _emulate_human(self, page):
        """Mimics human behavior: random scrolling and mouse jitter."""
        try:
            for _ in range(random.randint(3, 5)):
                await page.mouse.move(random.randint(100, 800), random.randint(100, 600), steps=random.randint(5, 10))
                await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.mouse.wheel(0, random.randint(200, 500))
        except: pass

    async def _fetch_via_browser(self, url: str) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p_engine:
            proxy_conf = self.get_proxy_config()
            all_raw_proxies = ProxyManager.get_all_proxies()
            proxies_to_try = []
            
            if proxy_conf:
                proxies_to_try.append(proxy_conf)
            
            other_proxies = [p for p in all_raw_proxies if proxy_conf and p not in proxy_conf.get("server", "")]
            if other_proxies:
                random.shuffle(other_proxies)
                for p_str in other_proxies[:2]:
                    proxies_to_try.append(ProxyManager.parse_proxy_to_config(p_str))
            
            # Helper for browser attempts
            async def _attempt_with_config(specific_conf, profile: Dict[str, Any]):
                browser = None
                try:
                    launch_opts = {"headless": True}
                    if specific_conf:
                        p_server = specific_conf.get("server", "")
                        p_user = specific_conf.get("username")
                        p_pass = specific_conf.get("password")
                        clean_host = p_server.replace("http://", "").replace("https://", "")
                        safe_user = urllib.parse.quote(p_user) if p_user else ""
                        safe_pass = urllib.parse.quote(p_pass) if p_pass else ""
                        p_url = f"http://{safe_user}:{safe_pass}@{clean_host}" if p_user else f"http://{clean_host}"
                        
                        if not await self._is_proxy_healthy(p_url):
                            logger.warning(f"[GSA-Health] Skipping proxy: {p_server}")
                            return None
                        launch_opts["proxy"] = specific_conf
                    else:
                        logger.info("[GSA-Browser] Attempting DIRECT connection...")

                    browser = await p_engine.chromium.launch(**launch_opts)
                    context = await browser.new_context(
                        user_agent=profile["ua"],
                        viewport=profile["viewport"],
                        is_mobile=profile["is_mobile"],
                        has_touch=profile["is_mobile"],
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                            **profile["headers"]
                        }
                    )
                    page = await context.new_page()
                    await self._inject_hardened_fingerprint(page)
                    try:
                        if hasattr(playwright_stealth, "Stealth"):
                            await playwright_stealth.Stealth().apply_stealth_async(page)
                        elif hasattr(playwright_stealth, "stealth_async"):
                            await playwright_stealth.stealth_async(page)
                    except: pass

                    # --- NETWORK INTERCEPTION STRATEGY ---
                    # Instead of calling ppms.gov directly (which gets blocked by IP),
                    # we let the real browser navigate to gsaauctions.gov and 
                    # intercept the ppms.gov XHR/fetch that the SPA makes natively.
                    # This request carries real browser cookies/session context.
                    captured_data = {}

                    async def handle_response(response):
                        try:
                            parsed = urllib.parse.urlparse(response.url)
                            if parsed.hostname == "www.ppms.gov" and "getAuction" in parsed.path and response.status == 200:
                                json_body = await response.json()
                                captured_data.update(json_body)
                        except Exception:
                            pass

                    page.on("response", handle_response)

                    # Block images/fonts to speed up load
                    await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
                    
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await self._emulate_human(page)

                    # Wait up to 15 seconds for the ppms.gov response to be intercepted
                    for _ in range(30):
                        if captured_data:
                            break
                        await asyncio.sleep(0.5)

                    if not captured_data:
                        # Check if the page itself shows something useful
                        content = await page.content()
                        if any(block in content.lower() for block in ["access denied", "403 forbidden", "blocked"]):
                            logger.warning("[GSA-Browser] Access Denied detected.")
                        else:
                            logger.warning("[GSA-Browser] ppms.gov API response not captured.")
                        return None

                    logger.info(f"[GSA-Browser] Successfully intercepted ppms.gov response.")
                    data = captured_data
                    item_name = data.get("lotName") or data.get("itemName") or "GSA Item"
                    loc = data.get("location") or {}
                    city = loc.get("city") or data.get("city", "Unknown")
                    state = loc.get("state") or data.get("state", "Unknown")
                    closing_time = data.get("endDate") or data.get("closingTime") or data.get("auctionEndTime")

                    return {
                        "item_name": str(item_name).strip()[:200],
                        "current_bid": float(str(data.get("currentBid", 0)).replace(",", "")),
                        "total_bidders": int(data.get("numberOfBidders") or data.get("bidderCount", 0)),
                        "closing_time": closing_time,
                        "city": city,
                        "state": state,
                        "website_name": "GSA Auctions",
                        "status": "active"
                    }

                except Exception as e:
                    logger.debug(f"[GSA-Browser] Attempt failed: {e}")
                    return None
                finally:
                    if browser: await browser.close()

            result = None
            for i, config in enumerate(proxies_to_try):
                profile = self._get_stealth_profile()
                logger.info(f"[GSA-Browser] Attempt {i+1}/{len(proxies_to_try)} using: {config.get('server')} | Profile: {'Mobile' if profile['is_mobile'] else 'Desktop'}")
                result = await _attempt_with_config(config, profile)
                if result: break
            
            if not result:
                logger.warning("[GSA-Browser] All proxies failed. Attempting LAST RESORT (DIRECT)...")
                result = await _attempt_with_config(None, self._get_stealth_profile())
            
            return result
