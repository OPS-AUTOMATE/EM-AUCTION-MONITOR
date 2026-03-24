"""
PurpleWave Adapter Module.
Extracts listing details for heavy equipment using fast HTTP requests and regex parsing.
"""
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any

import httpx
import pytz
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class PurpleWaveAdapter(BaseAuctionAdapter):
    """
    Hardened PurpleWave Adapter (Tier A - HTTP/Regex).
    Extremely fast extraction using semantic HTML patterns.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            }
            
            # Proxy Configuration
            proxy_conf = self.get_proxy_config()
            proxies = None
            if proxy_conf:
                server = proxy_conf['server']
                if 'username' in proxy_conf:
                    auth = f"{proxy_conf['username']}:{proxy_conf['password']}@"
                    proxies = server.replace("://", f"://{auth}")
                else:
                    proxies = server
                logger.debug("[PurpleWave] Using Proxy: %s", server)

            async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True, proxy=proxies) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    logger.warning("[PurpleWave] Fetch failed with status %d: %s", response.status_code, url)
                    return None
                
                html = response.text
                
                # 1. Item Name
                item_name = "Unknown PurpleWave Item"
                if name_match := re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.I):
                    item_name = re.sub('<[^<]+?>', '', name_match.group(1)).strip()

                # 2. Current Bid
                current_bid = 0.0
                if bid_match := re.search(r"Current bid:\s*\$?\s*([\d,]+\.?\d*)", html, re.I):
                    current_bid = float(bid_match.group(1).replace(",", ""))
                
                # 3. Location
                city, state = "Unknown", "Unknown"
                if loc_match := re.search(r"Location:\s*([^<,]+),\s*([A-Z]{2})", html, re.I):
                    city, state = loc_match.group(1).strip(), loc_match.group(2).strip()

                # 4. Closing Time
                closing_time_iso = None
                if time_match := re.search(r"Closes:\s*([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[APM]{2})", html, re.I):
                    try:
                        date_str = time_match.group(1).strip()
                        naive_dt = datetime.strptime(date_str, "%b %d, %Y %I:%M %p")
                        # PurpleWave typically uses US/Central
                        central = pytz.timezone('US/Central')
                        closing_time_iso = central.localize(naive_dt).isoformat()
                    except (ValueError, pytz.exceptions.Error):
                        pass

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "closing_time": closing_time_iso,
                    "city": city,
                    "state": state,
                    "website_name": "Purple Wave",
                    "status": "active"
                }

        except (httpx.HTTPError, TimeoutError) as e:
            logger.error("[PurpleWave] Network error: %s", e)
            return None
        except Exception as e:
            logger.error("[PurpleWave] Unexpected error: %s", e)
            return None
