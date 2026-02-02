import asyncio
import logging
import json
import re
from typing import Optional, Dict, Any
import httpx
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class MazreeAdapter(BaseAuctionAdapter):
    """
    Hardened Mazree Adapter (Tier A - API/JSON).
    Extracts data from the internal Angular state (ng-state) to avoid heavy browser scraping.
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        # Mazree is reliable via HTTP because they embed the state in the HTML
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,xml;q=0.9,image/avif,webp,*/*;q=0.8"
            }
            
            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    logger.warning(f"[Mazree] HTTP {response.status_code} for {url}")
                    return None
                
                html = response.text
                
                # --- 1. Extract JSON State ---
                # Mazree (Angular) stores the lot details in a script tag with id="ng-state"
                state_match = re.search(r'<script id="ng-state" type="application/json">(.*?)</script>', html, re.DOTALL)
                if not state_match:
                    logger.warning(f"[Mazree] Could not find ng-state for {url}")
                    # Fallback to Regex if JSON state is missing
                    return self._regex_fallback(html)

                try:
                    state_data = json.loads(state_match.group(1))
                    # Note: Angular state structure can be deep. We crawl it for keywords.
                    return self._parse_mazree_state(state_data, html)
                except Exception as e:
                    logger.error(f"[Mazree] State parse error: {e}")
                    return self._regex_fallback(html)

        except Exception as e:
            logger.error(f"[Mazree] Fetch Failure: {e}")
            return None

    def _parse_mazree_state(self, state: Dict, html: str) -> Optional[Dict[str, Any]]:
        """
        Heuristic parsing of the Mazree Angular state.
        Searching for lot details, prices, and locations.
        """
        # Mazree state is often a list of objects under __nghData__ or similar
        # We also use raw regex on the whole HTML as a robust fallback for the name
        item_name = "Unknown Mazree Item"
        name_match = re.search(r'<title>(.*?)</title>', html, re.I)
        if name_match: item_name = name_match.group(1).replace("| Mazree", "").strip()

        # Prices and Bidders are often in the state
        current_bid = 0.0
        total_bidders = 0
        city, state_code = "Unknown", "Unknown"
        closing_time = None

        # Deep search in state (Mazree specific paths)
        flat_state = str(state)
        
        # Current Bid
        price_match = re.search(r"'currentBid':\s*([\d.]+)", flat_state)
        if not price_match: price_match = re.search(r"\"currentBid\":\s*([\d.]+)", flat_state)
        if price_match: current_bid = float(price_match.group(1))
        
        # Bidder Count
        bidder_match = re.search(r"'bidderCount':\s*(\d+)", flat_state)
        if not bidder_match: bidder_match = re.search(r"\"bidderCount\":\s*(\d+)", flat_state)
        if bidder_match: total_bidders = int(bidder_match.group(1))

        # Location
        loc_match = re.search(r"'city':\s*'([^']+)',\s*'state':\s*'([^']+)'", flat_state)
        if loc_match:
            city, state_code = loc_match.group(1), loc_match.group(2)

        # Closing Time (Milliseconds usually)
        time_match = re.search(r"'endTime':\s*(\d{10,13})", flat_state)
        if time_match:
            ts = int(time_match.group(1))
            if ts > 10**11: ts /= 1000 # Convert ms to s
            closing_time = datetime.fromtimestamp(ts, tz=pytz.UTC).isoformat()

        return {
            "item_name": item_name,
            "current_bid": current_bid,
            "total_bidders": total_bidders,
            "closing_time": closing_time,
            "city": city,
            "state": state_code,
            "website_name": "Mazree",
            "status": "active"
        }

    def _regex_fallback(self, html: str) -> Optional[Dict[str, Any]]:
        """
        Standard Regex patterns if JSON parsing fails.
        """
        item_name = "N/A"
        name_match = re.search(r"\"lotName\":\"([^\"]+)\"", html)
        if name_match: item_name = name_match.group(1)
        
        bid = 0.0
        bid_match = re.search(r"\"currentBid\":\s*([\d.]+)", html)
        if bid_match: bid = float(bid_match.group(1))

        return {
            "item_name": item_name,
            "current_bid": bid,
            "website_name": "Mazree",
            "status": "active"
        }
import pytz
from datetime import datetime
