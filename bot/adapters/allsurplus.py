import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright
from .base_adapter import BaseAuctionAdapter

logger = logging.getLogger(__name__)

class AllSurplusAdapter(BaseAuctionAdapter):
    """
    AllSurplus Adapter (Tier B - Playwright).
    """

    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                logger.info(f"Fetching AllSurplus URL: {url}")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Extract Title
                title_elem = await page.query_selector("h1")
                item_name = await title_elem.inner_text() if title_elem else "Unknown AllSurplus Item"
                item_name = item_name.strip()

                # Extract Price
                # Format: "1,880.00 USD (6 Bids)"
                price_text = ""
                price_elem = await page.query_selector(".bidding-box .price, .asset-current-bid")
                if price_elem:
                    price_text = await price_elem.inner_text()
                else:
                    # Fallback to search
                    price_elem = await page.query_selector("text=Current Bid")
                    if price_elem:
                        parent = await price_elem.query_selector("xpath=..")
                        if parent:
                            price_text = await parent.inner_text()

                current_price = 0.0
                if price_text:
                    price_match = re.search(r"([\d,]+\.?\d*)", price_text.replace(",", ""))
                    if price_match:
                        current_price = float(price_match.group(1))

                # Extract Closing Time
                # Format: "3h41m(Mar 18, 2026 07:00 PM EDT)"
                closing_date = None
                time_elem = await page.query_selector(".time-left, .asset-ends")
                if time_elem:
                    time_text = await time_elem.inner_text()
                    date_match = re.search(r"\((.*?)\)", time_text)
                    if date_match:
                        date_str = date_match.group(1)
                        try:
                            # Mar 18, 2026 07:00 PM EDT
                            clean_date_str = re.sub(r"\s[A-Z]{3}$", "", date_str)
                            closing_date = datetime.strptime(clean_date_str, "%b %d, %Y %I:%M %p")
                        except Exception as e:
                            logger.error(f"Error parsing date {date_str}: {e}")

                return {
                    "item_name": item_name,
                    "current_price": current_price,
                    "closing_date": closing_date,
                    "location": "See Website",
                    "url": url,
                    "site_key": "allsurplus"
                }

            except Exception as e:
                logger.error(f"Error fetching AllSurplus: {e}")
                return None
            finally:
                await browser.close()
