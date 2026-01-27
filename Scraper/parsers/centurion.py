from playwright.async_api import async_playwright, Browser
import logging

logger = logging.getLogger(__name__)

async def scrape_centurion(url: str, browser: Browser = None):
    """
    Scrapes a Centurion Service Group auction item.
    """
    if browser:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return await _scrape_centurion_with_context(url, context)
    
    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(headless=True)
        context = await temp_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        data = await _scrape_centurion_with_context(url, context)
        await temp_browser.close()
        return data

async def _scrape_centurion_with_context(url: str, context):
    page = await context.new_page()
    try:
        logger.info(f"Navigating to Centurion: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        
        # Extract Item Name
        item_name = await page.locator("h1.lot-title, .lotname").first.inner_text()
        
        # Extract Current Bid
        # Centurion often uses 'Current Bid' or 'Opening Bid'
        bid_text = "$0"
        if await page.locator(".current-bid-amount").count() > 0:
            bid_text = await page.locator(".current-bid-amount").first.inner_text()
        elif await page.locator(".high-bid-amount").count() > 0:
            bid_text = await page.locator(".high-bid-amount").first.inner_text()
        
        current_bid = float(bid_text.replace("$", "").replace(",", "").strip())

        # Extract Bidders count
        bidders = 0
        if await page.locator(".bid-count").count() > 0:
            count_text = await page.locator(".bid-count").first.inner_text()
            bidders = int("".join(filter(str.isdigit, count_text)))

        # Time Remaining
        time_remaining = "Unknown"
        if await page.locator(".time-left, .countdown").count() > 0:
            time_remaining = await page.locator(".time-left, .countdown").first.inner_text()

        return {
            "item_name": item_name.strip(),
            "current_bid": current_bid,
            "total_bidders": bidders,
            "time_remaining_str": time_remaining.strip(),
            "website_name": "Centurion Auctions"
        }

    except Exception as e:
        logger.error(f"Centurion scrape error: {e}")
        return None
    finally:
        await context.close()
