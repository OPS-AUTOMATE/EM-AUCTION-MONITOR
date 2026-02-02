import asyncio
import logging
import re
from typing import Optional, Dict, Any
import httpx
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class SurplusMarketplaceAdapter(BaseAuctionAdapter):
    """
    Hardened Surplus Marketplace Adapter (Tier A - HTTP).
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            }
            
            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                
                html = response.text
                
                # --- 1. Item Name ---
                item_name = "Unknown Surplus Item"
                name_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.I)
                if name_match:
                    item_name = re.sub('<[^<]+?>', '', name_match.group(1)).strip()

                # --- 2. Current Bid ---
                current_bid = 0.0
                bid_match = re.search(r"(?:Current|Starting)\s*Bid:\s*[^0-9]*([\d,]+\.?\d*)", html, re.I)
                if not bid_match:
                    bid_match = re.search(r'class="amount"[^>]*>([^<]+)', html, re.I)
                
                if bid_match:
                    price_str = bid_match.group(1).replace(",", "").strip()
                    try:
                        current_bid = float(price_str)
                    except: pass
                
                return {
                    "item_name": item_name[:200],
                    "current_bid": current_bid,
                    "website_name": "Surplus Marketplace",
                    "status": "active"
                }

        except Exception as e:
            logger.error(f"[SurplusMarketplace] Fetch Failure: {e}")
            return None
