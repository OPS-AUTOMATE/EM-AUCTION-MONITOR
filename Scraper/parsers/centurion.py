import asyncio
from playwright.async_api import async_playwright, Browser
import logging
import re
from utils.bandwidth import apply_bandwidth_saver
from constants import get_premium

logger = logging.getLogger(__name__)

async def scrape_centurion(url: str, browser: Browser = None, context = None):
    """
    Scrapes a Centurion Service Group auction item.
    Supports browser reuse and shared caching.
    """
    if context:
        # Use shared context (High Efficiency Caching)
        return await _scrape_centurion_with_context(url, context, is_shared=True)

    if browser:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        return await _scrape_centurion_with_context(url, context, is_shared=False)
    
    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(headless=True)
        context = await temp_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        data = await _scrape_centurion_with_context(url, context, is_shared=False)
        await temp_browser.close()
        return data

async def _scrape_centurion_with_context(url: str, context, is_shared=False):
    page = await context.new_page()
    await apply_bandwidth_saver(page)
    try:
        logger.info(f"Navigating to Centurion: {url}")
        # Centurion needs 'load' and a wait for the JS to hydrate
        await page.goto(url, wait_until="load", timeout=30000)
        
        # Give dynamic JS extra time to load prices and clocks
        await asyncio.sleep(6)

        content_text = await page.locator("body").inner_text()
        
        # 1. Extract Item Name
        item_name = "Unknown Centurion Item"
        title_selectors = ["h1", ".tle.aucdttle", ".product-name", ".lot-title"]
        for sel in title_selectors:
            try:
                if await page.locator(sel).count() > 0:
                    item_name = await page.locator(sel).first.inner_text()
                    break
            except: continue

        # 2. Extract Current Bid (Aggressive Search)
        current_bid = 0.0
        # Strategy A: Text-based near labels
        bid_patterns = [
            r'Current bid:\s*\$(\d+(?:,\d+)*(?:\.\d+)?)',
            r'Price:\s*\$(\d+(?:,\d+)*(?:\.\d+)?)',
            r'Asking:\s*\$(\d+(?:,\d+)*(?:\.\d+)?)',
            r'Amount:\s*\$(\d+(?:,\d+)*(?:\.\d+)?)'
        ]
        
        for pattern in bid_patterns:
            match = re.search(pattern, content_text, re.IGNORECASE)
            if match:
                current_bid = float(match.group(1).replace(",", ""))
                break
        
        # Strategy B: If still 0, look for any lone dollar amount in the prominent areas
        if current_bid == 0.0:
            # Look for money patterns in specific containers
            money_sel = ".current-bid, .amount, .price"
            if await page.locator(money_sel).count() > 0:
                money_text = await page.locator(money_sel).first.inner_text()
                match = re.search(r'\$(\d+(?:,\d+)*(?:\.\d+)?)', money_text)
                if match:
                    current_bid = float(match.group(1).replace(",", ""))

        # 3. Extract Time (Remaining or Start In)
        time_str = "Unknown"
        time_label = "Ends in"
        closing_time_iso = None
        
        # Improved Regex for labels (handle multi-line or shadowed text)
        time_patterns = [
            (r'(?:Bidding is open in|Bidding starts in):\s*(.*)', "Bidding starts in"),
            (r'(?:Time left|Time remaining|Ends in):\s*(.*)', "Ends in"),
            (r'Bidding Closes:\s*(.*)', "Ends in")
        ]
        
        for pattern, label in time_patterns:
            match = re.search(pattern, content_text, re.IGNORECASE)
            if match:
                time_label = label
                raw_time = match.group(1).split("\n")[0].strip() # Take just the first line
                time_str = raw_time
                
                # Parse "6d 7h 14m" or "23h 10m"
                try:
                    from datetime import datetime, timedelta, timezone
                    days = 0; hours = 0; mins = 0
                    d_m = re.search(r'(\d+)d', time_str)
                    h_m = re.search(r'(\d+)h', time_str)
                    m_m = re.search(r'(\d+)m', time_str)
                    if d_m: days = int(d_m.group(1))
                    if h_m: hours = int(h_m.group(1))
                    if m_m: mins = int(m_m.group(1))
                    
                    if days or hours or mins:
                        delta = timedelta(days=days, hours=hours, minutes=mins)
                        closing_dt = datetime.now(timezone.utc) + delta
                        closing_time_iso = closing_dt.isoformat().replace("+00:00", "Z")
                except: pass
                break

        # 4. Extract Bidders count
        bidders = 0
        bid_count_match = re.search(r'(\d+)\s*bids?', content_text, re.IGNORECASE)
        if bid_count_match:
            bidders = int(bid_count_match.group(1))

        # 5. Get Location & Premium
        premium = get_premium(url)
        city, state = "Unknown", ""
        
        loc_match = re.search(r'Location:\s*([^\n]+)', content_text, re.IGNORECASE)
        if loc_match:
            loc_str = loc_match.group(1).strip()
            if "," in loc_str:
                parts = loc_str.split(",")
                city = parts[0].strip()
                state = parts[1].strip()
            else:
                city = loc_str

        return {
            "item_name": item_name.strip(),
            "current_bid": current_bid,
            "total_bidders": bidders,
            "time_remaining_str": f"{time_label}: {time_str}".strip(),
            "closing_time": closing_time_iso,
            "premium_percentage": premium,
            "city": city,
            "state": state,
            "website_name": "Centurion Auctions"
        }

    except Exception as e:
        logger.error(f"Centurion scrape error: {e}")
        return None
    finally:
        try:
            await page.close()
            if not is_shared:
                await context.close()
        except: pass
