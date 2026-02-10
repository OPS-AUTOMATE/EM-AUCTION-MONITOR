import asyncio
import logging
import json
import re
from typing import Optional, Dict, Any
import httpx
from .base_adapter import BaseAuctionAdapter
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class PurpleWaveAdapter(BaseAuctionAdapter):
    """
    Hardened PurpleWave Adapter (Tier A - JSON/HTML).
    Utilizes semantic HTML tags and embedded JSON metadata for speed.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            }
            
            # Proxy Rotation
            proxy_conf = self.get_proxy_config()
            proxies = None
            if proxy_conf:
                proxies = proxy_conf['server']
                if 'username' in proxy_conf:
                    auth_prefix = f"{proxy_conf['username']}:{proxy_conf['password']}@"
                    proxies = proxies.replace("://", f"://{auth_prefix}")
                logger.info(f"[PurpleWave] Using Proxy: {proxy_conf['server']}")

            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True, proxy=proxies) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                
                html = response.text
                
                # --- 1. Extract Item Name ---
                item_name = "Unknown PurpleWave Item"
                name_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.I)
                if name_match:
                    item_name = re.sub('<[^<]+?>', '', name_match.group(1)).strip()

                # --- 2. Current Bid ---
                current_bid = 0.0
                # PurpleWave uses 'Current bid: $X,XXX'
                bid_match = re.search(r"Current bid:\s*\$?\s*([\d,]+\.?\d*)", html, re.I)
                if bid_match:
                    current_bid = float(bid_match.group(1).replace(",", ""))
                
                # --- 3. Location ---
                city, state = "Unknown", "Unknown"
                # Pattern: Location: City, ST
                loc_match = re.search(r"Location:\s*([^<,]+),\s*([A-Z]{2})", html, re.I)
                if loc_match:
                    city, state = loc_match.group(1).strip(), loc_match.group(2).strip()

                # --- 4. Closing Time ---
                closing_time_iso = None
                # Pattern: 'Closes: Feb 5, 2026 10:00 AM'
                time_match = re.search(r"Closes:\s*([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[APM]{2})", html, re.I)
                if time_match:
                    try:
                        date_str = time_match.group(1).strip()
                        naive_dt = datetime.strptime(date_str, "%b %d, %Y %I:%M %p")
                        # PurpleWave usually uses US/Central (Manhattan, KS HQ)
                        central = pytz.timezone('US/Central')
                        closing_time_iso = central.localize(naive_dt).isoformat()
                    except: pass

                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "closing_time": closing_time_iso,
                    "city": city,
                    "state": state,
                    "website_name": "Purple Wave",
                    "status": "active"
                }

        except Exception as e:
            logger.error(f"[PurpleWave] Fetch Failure: {e}")
            return None
