import asyncio
from playwright.async_api import async_playwright
import logging

logger = logging.getLogger(__name__)

async def scrape_bidspotter(url: str):
    """
    Scrapes a BidSpotter auction item page.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # BidSpotter often needs a realistic user agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        try:
            logger.info(f"Navigating to BidSpotter: {url}")
            await page.goto(url, wait_until="networkidle", timeout=45000)
            
            # Extract Item Name
            item_name = await page.locator(".lot-details__title, h1").first.inner_text()
            
            # Extract Current Bid
            bid_text = await page.locator(".lot-details__bid-amount, .current-bid").first.inner_text()
            current_bid = float(bid_text.replace("$", "").replace(",", "").strip())

            # Extract Bidders count (if available)
            bidders = 0
            if await page.locator(".lot-details__bid-count").count() > 0:
                bid_count_text = await page.locator(".lot-details__bid-count").first.inner_text()
                bidders = int("".join(filter(str.isdigit, bid_count_text)))

            # Extract Location
            location = await page.locator(".lot-details__location").first.inner_text()
            city = ""
            state = ""
            if "," in location:
                parts = location.split(",")
                city = parts[0].strip()
                state = parts[1].strip()

            # Time Remaining
            time_remaining = await page.locator(".lot-details__time-left").first.inner_text()

            return {
                "item_name": item_name.strip(),
                "current_bid": current_bid,
                "total_bidders": bidders,
                "city": city,
                "state": state,
                "time_remaining_str": time_remaining.strip(),
                "website_name": "BidSpotter"
            }

        except Exception as e:
            logger.error(f"BidSpotter scrape error: {e}")
            return None
        finally:
            await browser.close()
