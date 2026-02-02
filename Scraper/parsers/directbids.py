import logging
from playwright.async_api import async_playwright, Browser

logger = logging.getLogger(__name__)

async def scrape_directbids(url: str, browser: Browser = None, context = None):
    if context:
        return await _scrape_directbids_with_context(url, context)
    
    if browser:
        context = await browser.new_context()
        return await _scrape_directbids_with_context(url, context)

    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(headless=True)
        context = await temp_browser.new_context()
        data = await _scrape_directbids_with_context(url, context)
        await temp_browser.close()
        return data

async def _scrape_directbids_with_context(url: str, context):
    page = await context.new_page()
    try:
        logger.info(f"Navigating to Direct Bids: {url}")
        await page.goto(url, wait_until="networkidle", timeout=45000)
        item_name = await page.locator(".auction-title, h1").first.inner_text()
        bid_text = await page.locator(".current-price, .bid-amount").first.inner_text()
        current_bid = float(bid_text.replace("$", "").replace(",", "").strip())
        return {
            "item_name": item_name.strip(),
            "current_bid": current_bid,
            "website_name": "Direct Bids"
        }
    except Exception as e:
        logger.error(f"Direct Bids scrape error: {e}")
        return None
    finally:
        await page.close()
