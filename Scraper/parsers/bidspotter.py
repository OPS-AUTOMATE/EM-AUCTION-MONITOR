import asyncio
from playwright.async_api import async_playwright, Browser
try:
    from playwright_stealth import stealth_async
except ImportError:
    stealth_async = None
import logging
import re
from datetime import datetime
import pytz
from utils.bandwidth import apply_bandwidth_saver

logger = logging.getLogger(__name__)

async def scrape_bidspotter(url: str, browser: Browser = None, context = None):
    """
    Robust BidSpotter Scraper (V2.0).
    Supports browser reuse and shared caching.
    """
    if context:
        # Use shared context (High Efficiency Caching)
        return await _scrape_with_context(url, context, is_shared=True)

    if browser:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        return await _scrape_with_context(url, context, is_shared=False)
    
    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await temp_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        data = await _scrape_with_context(url, context, is_shared=False)
        await temp_browser.close()
        return data

async def _scrape_with_context(url: str, context, is_shared=False):
    page = await context.new_page()
    try:
        if stealth_async:
            await stealth_async(page)
        
        await apply_bandwidth_saver(page)
        
        logger.info(f"[BidSpotter] Navigating to: {url}")
        # Use domcontentloaded instead of networkidle to avoid timeouts from background requests
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        # Wait for content to appear after initial load
        await page.wait_for_selector('h1, #price, #timer', timeout=20000)
        await asyncio.sleep(8) # Robust wait for dynamic prices/timers

        # 1. Item Name
        item_name = "N/A"
        name_selectors = ['h1.lot-details-title', 'h1', '.lot-title']
        for sel in name_selectors:
            if await page.locator(sel).count() > 0:
                item_name = await page.locator(sel).first.inner_text()
                break

        # 2. Current Bid
        current_bid = 0.0
        bid_selectors = ['.current-bid-price', '.price-value', '.bid-amount', '.price']
        for sel in bid_selectors:
            if await page.locator(sel).count() > 0:
                bid_text = await page.locator(sel).first.inner_text()
                clean_bid = re.sub(r'[^\d.]', '', bid_text)
                if clean_bid:
                    current_bid = float(clean_bid)
                    break

        # 3. Total Bidders
        total_bidders = 0
        bid_count_selectors = ['.bid-count', '.total-bids', '.bid-history-link']
        for sel in bid_count_selectors:
            if await page.locator(sel).count() > 0:
                count_text = await page.locator(sel).first.inner_text()
                match = re.search(r'(\d+)', count_text)
                if match:
                    total_bidders = int(match.group(1))
                    break

        # 4. Premium Percentage
        premium_percentage = 18.0 # Fallback
        content = await page.content()
        premium_match = re.search(r'Buyer\'s Premium(?:\s*:\s*|\s*)\(?(\d+(?:\.\d+)?)\s*%', content, re.IGNORECASE)
        if premium_match:
            premium_percentage = float(premium_match.group(1))

        # 5. Time Remaining & Closing Time
        time_remaining = "Unknown"
        closing_time_iso = None
        
        # Strategy A: Extract from specific timer elements
        timer_selectors = ['.timer-value', '#timer', '.time-left', '.closing-message']
        for sel in timer_selectors:
            if await page.locator(sel).count() > 0:
                time_remaining = await page.locator(sel).first.inner_text()
                break

        # Strategy B: Try to find data-closing-time attributes (Non-blocking)
        closing_locator = page.locator('[data-closing-time]').first
        if await closing_locator.count() > 0:
            closing_attr = await closing_locator.get_attribute('data-closing-time')
            if closing_attr:
                try:
                    # Often in milliseconds
                    if len(closing_attr) > 10:
                        dt = datetime.fromtimestamp(int(closing_attr)/1000, tz=pytz.UTC)
                    else:
                        dt = datetime.fromtimestamp(int(closing_attr), tz=pytz.UTC)
                    closing_time_iso = dt.isoformat()
                except: pass

        # 6. Location (City, State)
        city, state = "Unknown", "Unknown"
        loc_selector = '.lot-location, .location'
        # XPath for table based info often found on BidSpotter
        loc_xpath = "xpath=//td[contains(text(), 'Location')]/following-sibling::td"
        
        if await page.locator(loc_xpath).count() > 0:
            loc_text = await page.locator(loc_xpath).first.inner_text()
            items = loc_text.split("\n")
            if len(items) >= 2:
                city = items[0].strip()
                state = items[1].strip()
            if len(items) >= 6:
                city = items[4].strip()
                state = items[5].strip()
        elif await page.locator(loc_selector).count() > 0:
            loc_text = await page.locator(loc_selector).first.inner_text()
            if "," in loc_text:
                parts = loc_text.split(",")
                city = parts[0].strip()
                state = parts[1].strip()

        logger.info(f"[BidSpotter] Extracted: {item_name[:20]} | Bid: ${current_bid} | Premium: {premium_percentage}%")

        # Get summary from bandwidth utility
        from utils.bandwidth import get_bandwidth_summary
        summary = get_bandwidth_summary(page)
        logger.info(f"[BidSpotter] {summary}")

        return {
            "item_name": item_name.strip(),
            "current_bid": current_bid,
            "total_bidders": total_bidders,
            "premium_percentage": premium_percentage,
            "time_remaining_str": time_remaining.strip(),
            "closing_time": closing_time_iso,
            "city": city,
            "state": state,
            "website_name": "BidSpotter",
            "status": "active"
        }

    except Exception as e:
        logger.error(f"[BidSpotter] Scrape Failure for {url}: {e}")
        return None
    finally:
        await page.close()
        if not is_shared:
            await context.close()
