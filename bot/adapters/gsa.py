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
import urllib.parse

logger = logging.getLogger(__name__)

class GsaAdapter(BaseAuctionAdapter):
    """
    Hardened GSA Adapter using User-Defined XPaths and Patterns.
    Combines API speed with browser precision.
    """

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
        api_url = f"https://gsaauctions.gov/gsaauctions/aucindx/?suid={suid}"
        logger.info(f"[GSA-API] Fetching: {api_url}")
        
        
        proxies = None
        # RE-ENABLED Proxy for GSA with robust credential encoding
        proxy_conf = self.get_proxy_config()
        if proxy_conf:
            p_server = proxy_conf.get("server")
            p_user = proxy_conf.get("username")
            p_pass = proxy_conf.get("password")
            
            if p_server:
                clean_host = p_server.replace("http://", "").replace("https://", "")
                if p_user and p_pass:
                    # Escape special characters in password (like '+')
                    safe_user = urllib.parse.quote(p_user)
                    safe_pass = urllib.parse.quote(p_pass)
                    proxies = f"http://{safe_user}:{safe_pass}@{clean_host}"
                else:
                    proxies = f"http://{clean_host}"
                
                logger.info(f"[GSA-API] Using Proxy: {p_server}")

        async def _do_api_request(p_url: str, p_config: Optional[str]) -> Optional[httpx.Response]:
            try:
                # Enhanced headers to mimic a premium browser session
                async with httpx.AsyncClient(timeout=20.0, verify=False, proxy=p_config) as client:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": "https://gsaauctions.gov/auctions/",
                        "DNT": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-User": "?1",
                        "Upgrade-Insecure-Requests": "1"
                    }
                    return await client.get(p_url, headers=headers)
            except Exception as e:
                logger.error(f"[GSA-API] Request Attempt failed: {e}")
                return None

        response = await _do_api_request(api_url, proxies)
        
        # FALLBACK: If proxy failed (Tunnel error, etc.), try Direct if proxies were used
        if (not response or response.status_code >= 400) and proxies:
            logger.warning("[GSA-API] Proxy failed/blocked. Retrying DIRECT...")
            response = await _do_api_request(api_url, None)

        try:
            if response and response.status_code == 200:
                logger.info(f"[GSA-API] Status: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.info(f"[GSA-API] Data Keys: {list(data.keys())}")
                        item_name = data.get("itemName") or data.get("lotName") or "GSA Item"
                        
                        # Sanity check for "403" in name (GSA sometimes puts error in JSON fields if partially blocked)
                        if "403" in str(item_name):
                            logger.warning(f"[GSA-API] Blocked name detected: {item_name}")
                            return None

                        current_bid = float(str(data.get("currentBid", 0)).replace(",", ""))
                        total_bidders = int(data.get("bidderCount", 0))
                        closing_time_iso = data.get("closingTime") or data.get("auctionEndTime")
                        
                        return {
                            "item_name": item_name.strip()[:200],
                            "current_bid": current_bid,
                            "total_bidders": total_bidders,
                            "closing_time": closing_time_iso,
                            "city": data.get("city", "Unknown"),
                            "state": data.get("state", "Unknown"),
                            "website_name": "GSA Auctions",
                            "status": "active"
                        }
                    except Exception as e:
                        logger.error(f"[GSA-API] JSON Parse Error: {e}")
                        return None
                elif response.status_code == 403:
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
                # Use a lightweight check to a stable site
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

                // Randomize Screen/Viewport geometry
                Object.defineProperty(window.screen, 'width', {{ get: () => {random.randint(1600, 2560)} }});
                Object.defineProperty(window.screen, 'height', {{ get: () => {random.randint(900, 1440)} }});
                Object.defineProperty(window.screen, 'availWidth', {{ get: () => {random.randint(1550, 1600)} }});
                Object.defineProperty(window.screen, 'availHeight', {{ get: () => {random.randint(850, 900)} }});

                // Randomize Fonts (partially mask list)
                const originalQuery = document.fonts.query;
                if (originalQuery) {{
                    document.fonts.query = function() {{ return []; }};
                }}
            }})();
        """
        await page.add_init_script(fingerprint_script)

    async def _emulate_human(self, page):
        """Mimics human behavior: random scrolling and mouse jitter."""
        try:
            # 1. Random Mouse Movement
            for _ in range(random.randint(3, 6)):
                await page.mouse.move(random.randint(100, 800), random.randint(100, 600), steps=random.randint(5, 15))
                await asyncio.sleep(random.uniform(0.2, 0.5))

            # 2. Jittery Scrolling
            for _ in range(random.randint(2, 4)):
                scroll_amount = random.randint(200, 500)
                await page.mouse.wheel(0, scroll_amount)
                await asyncio.sleep(random.uniform(0.5, 1.2))
        except Exception as e:
            logger.debug(f"[GSA-Human] Behavior emulation skipped: {e}")

    async def _fetch_via_browser(self, url: str) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p_engine:
            # 1. Get Proxy Config
            proxy_conf = self.get_proxy_config()
            
            async def _attempt_browser_scrape(use_proxy: bool) -> Optional[Dict[str, Any]]:
                browser = None
                try:
                    launch_opts = {"headless": True}
                    if use_proxy and proxy_conf:
                        # Pre-check health to skip broken tunnels
                        p_server = proxy_conf.get("server")
                        p_user = proxy_conf.get("username")
                        p_pass = proxy_conf.get("password")
                        clean_host = p_server.replace("http://", "").replace("https://", "")
                        
                        safe_user = urllib.parse.quote(p_user) if p_user else ""
                        safe_pass = urllib.parse.quote(p_pass) if p_pass else ""
                        p_url = f"http://{safe_user}:{safe_pass}@{clean_host}" if p_user else f"http://{clean_host}"
                        
                        logger.info(f"[GSA-Health] Testing proxy: {p_server}")
                        if not await self._is_proxy_healthy(p_url):
                            logger.warning(f"[GSA-Health] Skipping broken/dead proxy: {p_server}")
                            return None
                        
                        launch_opts["proxy"] = proxy_conf
                        logger.info(f"[GSA-Browser] Using Healthy Proxy: {p_server}")
                    else:
                        logger.info("[GSA-Browser] Attempting DIRECT connection...")

                    browser = await p_engine.chromium.launch(**launch_opts)
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                        viewport={'width': random.randint(1280, 1920), 'height': random.randint(720, 1080)},
                        device_scale_factor=1,
                    )
                    page = await context.new_page()
                    
                    # Hardened Stealth & Fingerprinting
                    await self._inject_hardened_fingerprint(page)
                    try:
                        if hasattr(playwright_stealth, "Stealth"):
                            await playwright_stealth.Stealth().apply_stealth_async(page)
                        elif hasattr(playwright_stealth, "stealth_async"):
                            await playwright_stealth.stealth_async(page)
                    except Exception as se:
                        logger.warning(f"[GSA-Browser] Stealth failed: {se}")
                    
                    # Block only essentials (Keep SVG/CSS for fingerprinting parity)
                    await page.route("**/*", lambda route: route.abort() 
                        if route.request.resource_type in ["image", "media", "font"] 
                        else route.continue_())
                    
                    logger.info(f"[GSA-Browser] Navigation: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Human behavior emulation
                    await self._emulate_human(page)
                    
                    try:
                        await page.wait_for_selector(".ppms-details-container", timeout=15000)
                    except: pass
                    
                    # Final Extraction Logic
                    content = await page.content()
                    if any(block in content.lower() for block in ["403 forbidden", "access denied", "blocked"]):
                        logger.warning("[GSA-Browser] Block detected in content.")
                        return None
                    
                    # Reuse existing extraction logic contextually
                    main_block = page.locator(".ppms-details-container").first
                    full_text = await main_block.inner_text() if await main_block.count() > 0 else content
                    
                    item_name = "Unknown GSA Item"
                    name_match = re.search(r"Item Name\s*:\s*(.*?)\s*Sale Lot Number", full_text, re.DOTALL | re.I)
                    if name_match: item_name = name_match.group(1).strip()
                    else:
                        h1_count = await page.locator("h1").count()
                        if h1_count > 0: item_name = (await page.locator("h1").first.inner_text()).strip()

                    current_bid = 0.0
                    price_match = re.search(r"Current Bid:\s*\$?\s*([\d,]+\.?\d*)", full_text, re.I)
                    if price_match: current_bid = float(price_match.group(1).replace(",", ""))

                    return {
                        "item_name": item_name[:200],
                        "current_bid": current_bid,
                        "total_bidders": int((re.search(r"Bidders:\s*(\d+)", full_text, re.I) or re.search(r"(\d+)", "0")).group(1)),
                        "website_name": "GSA Auctions",
                        "status": "active",
                        "city": "Unknown", "state": "Unknown" # Expanded extraction omitted for brevity in loop
                    }

                except Exception as e:
                    logger.error(f"[GSA-Browser] Scrape failed: {e}")
                    return None
                finally:
                    if browser: await browser.close()

            # Resilience Loop: Try Proxy, then Try Direct
            result = None
            if proxy_conf:
                result = await _attempt_browser_scrape(use_proxy=True)
            
            if not result:
                result = await _attempt_browser_scrape(use_proxy=False)
            
            return result
