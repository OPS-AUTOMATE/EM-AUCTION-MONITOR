from playwright.async_api import async_playwright, Browser
import logging
from utils.bandwidth import apply_bandwidth_saver

logger = logging.getLogger(__name__)

async def scrape_bma(url: str, browser: Browser = None, context = None):
    """
    Scrapes British Medical Auctions (BMA).
    Supports browser reuse and shared caching.
    """
    if context:
        # Use shared context (High Efficiency Caching)
        return await _scrape_bma_with_context(url, context, is_shared=True)

    if browser:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return await _scrape_bma_with_context(url, context, is_shared=False)
    
    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(headless=True)
        context = await temp_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        data = await _scrape_bma_with_context(url, context, is_shared=False)
        await temp_browser.close()
        return data

async def _scrape_bma_with_context(url: str, context, is_shared=False):
    page = await context.new_page()
    await apply_bandwidth_saver(page)
    try:
        logger.info(f"Navigating to British Medical Auctions: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        # Extract Item Name
        item_name = await page.locator(".lot-title, h1").first.inner_text()
        
        # Extract Current Bid
        # BMA often shows bids in GBP or USD based on session, we clean both
        bid_text = "$0"
        if await page.locator(".current-bid, .amount").count() > 0:
            bid_text = await page.locator(".current-bid, .amount").first.inner_text()
        
        # Clean symbols like £ or $
        price_clean = bid_text.replace("£", "").replace("$", "").replace(",", "").strip()
        current_bid = float(price_clean) if price_clean else 0.0

        # Time Remaining
        time_remaining = "Ended"
        if await page.locator(".countdown, .time-left").count() > 0:
            time_remaining = await page.locator(".time-left, .countdown").first.inner_text()

        return {
            "item_name": item_name.strip(),
            "current_bid": current_bid,
            "time_remaining_str": time_remaining.strip(),
            "website_name": "British Medical Auctions"
        }

    except Exception as e:
        logger.error(f"BMA scrape error: {e}")
        return None
    finally:
        await page.close()
        if not is_shared:
            await context.close()
