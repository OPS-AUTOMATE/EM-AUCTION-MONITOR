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

logger = logging.getLogger(__name__)

async def scrape_bidspotter(url: str, browser: Browser = None):
    """
    Robust BidSpotter Scraper (V2.0).
    Using exact selectors and XPaths provided for precise data extraction.
    """
    if browser:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        return await _scrape_with_context(url, context)
    
    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await temp_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        data = await _scrape_with_context(url, context)
        await temp_browser.close()
        return data

async def _scrape_with_context(url: str, context):
    page = await context.new_page()
    if stealth_async:
        await stealth_async(page)
    
    try:
        logger.info(f"[BidSpotter] Navigating to: {url}")
        # Use domcontentloaded instead of networkidle to avoid timeouts from background requests
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for content to appear after initial load
        await page.wait_for_selector('h1, #price, #timer', timeout=30000)
        await asyncio.sleep(5) # Let dynamic prices/timers hydrate

        # --- 1. Extract Item Name ---
        item_name = "Unknown BidSpotter Item"
        title_selector = "body > div.viewport-wrapper > main > div > div:nth-child(2) > div > div:nth-child(2) > div > h1"
        if await page.locator(title_selector).count() > 0:
            item_name = await page.locator(title_selector).first.inner_text()
        else:
            item_name = await page.title()

        # --- 2. Extract Price ---
        current_bid = 0.0
        # Multiple possible selectors for price on BidSpotter
        price_selectors = ['#price', '.current-bid-amount', '.high-bid-amount', '.lot-price']
        for sel in price_selectors:
            if await page.locator(sel).count() > 0:
                price_text = await page.locator(sel).first.inner_text()
                if price_text:
                    clean_price = re.sub(r'[^\d.]', '', price_text)
                    if clean_price:
                        try:
                            current_bid = float(clean_price)
                            break
                        except ValueError: continue

        # --- 3. Extract Bidders ---
        total_bidders = 0
        bidders_selectors = ['#lotDetailsBids', '.bid-count', '.total-bids']
        for sel in bidders_selectors:
            if await page.locator(sel).count() > 0:
                text = await page.locator(sel).first.inner_text()
                match = re.search(r'(\d+)', text)
                if match:
                    total_bidders = int(match.group(1))
                    break

        # --- 4. Extract Buyers Premium ---
        premium_percentage = 0
        premium_selectors = ['#buyersPremium', '.buyers-premium', '.premium-amount']
        for sel in premium_selectors:
            if await page.locator(sel).count() > 0:
                premium_text = await page.locator(sel).first.inner_text()
                # Find number followed by % or just number
                premium_match = re.search(r'(\d+(?:\.\d+)?)\s*%', premium_text)
                if premium_match:
                    premium_percentage = float(premium_match.group(1))
                    break

        # --- 5. Extract Time Remaining ---
        time_remaining = "Syncing..."
        timer_selector = "#timer > span"
        if await page.locator(timer_selector).count() > 0:
            time_remaining = await page.locator(timer_selector).first.inner_text()

        # --- 6. Extract Closing Time (CT to UTC Conversion) ---
        closing_time_iso = None
        # Use user-provided specific selector + fallbacks
        closing_selectors = [
            "body > div.viewport-wrapper > main > div > div:nth-child(7) > div.ui.container > div > div > div > div.content.active > div > div > div:nth-child(2) > div > div > div > div > time",
            "time[datetime]",
            ".lot-details-time time",
            "time"
        ]
        
        raw_time_str = None
        for sel in closing_selectors:
            time_el = page.locator(sel).first
            if await time_el.count() > 0:
                # Try inner text FIRST (higher accuracy for timezone/AM-PM)
                text_val = await time_el.inner_text()
                if text_val and (":" in text_val or "AM" in text_val.upper() or "PM" in text_val.upper()):
                    raw_time_str = text_val.strip()
                    break
                # Fallback to datetime attribute
                raw_time_str = await time_el.get_attribute("datetime")
                if raw_time_str:
                    raw_time_str = raw_time_str.strip()
                    break
        
        if raw_time_str:
            logger.info(f"[BidSpotter] Raw Time Found: '{raw_time_str}'")
            try:
                # Clean labels and noise
                raw_time_str = re.sub(r'^(Ends from|Closing Time|Closes)\s*', '', raw_time_str, flags=re.I).strip()
                raw_time_str = raw_time_str.split('\n')[0].strip() # Take first line only

                # Ensure space before AM/PM
                raw_time_str = re.sub(r'(\d{1,2}:\d{2})\s*([APM]{2})', r'\1 \2', raw_time_str, flags=re.I)
                # Handle "10am" -> "10:00 AM"
                raw_time_str = re.sub(r'(\d{1,2})\s*([APM]{2})\b', r'\1:00 \2', raw_time_str, flags=re.I)

                # 1. BidSpotter format: "Jan 28, 2026 10:00 AM"
                bs_match = re.search(r"([a-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+[APM]{2})", raw_time_str, re.I)
                if bs_match:
                    date_str = bs_match.group(1)
                    # %b is for abbreviated month name like 'Jan'
                    naive_dt = datetime.strptime(date_str, "%b %d, %Y %I:%M %p")
                    central = pytz.timezone('US/Central')
                    closing_time_iso = central.localize(naive_dt).astimezone(pytz.UTC).isoformat()
                    logger.info(f"[BidSpotter] Parsed text date (CT): {closing_time_iso}")

                # 2. Standard format (MM/DD/YYYY)
                if not closing_time_iso:
                    dt_match = re.search(r"(\d{2}/\d{2}/\d{4}\s*\d{1,2}:\d{2}\s*[APM]{2})", raw_time_str, re.I)
                    if dt_match:
                        date_str = dt_match.group(1)
                        naive_dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
                        central = pytz.timezone('US/Central')
                        closing_time_iso = central.localize(naive_dt).astimezone(pytz.UTC).isoformat()
                
                # 3. ISO 8601 (Must look like a date-time 2024-01-01T...)
                if not closing_time_iso and re.search(r"\d{4}-\d{2}-\d{2}T", raw_time_str):
                    if '-' in raw_time_str.split('T')[1]:
                        date_p, time_p = raw_time_str.split('T')
                        raw_time_str = f"{date_p}T{time_p.replace('-', ':', 2)}"
                    closing_time_iso = raw_time_str.replace(" ", "")

                if not closing_time_iso and raw_time_str.isdigit() and len(raw_time_str) > 10:
                    closing_time_iso = datetime.fromtimestamp(int(raw_time_str) / 1000, pytz.UTC).isoformat()

            except Exception as e:
                logger.warning(f"[BidSpotter] Time processing error for '{raw_time_str}': {e}")

        # --- 7. Extract Location (City/State) ---
        city, state = "Unknown", "Unknown"
        # Try the specific selector first
        loc_selector = "body > div.viewport-wrapper > main > div > div:nth-child(7) > div.ui.stackable.grid > div > div:nth-child(2) > div.ui.basic.segment.auction-info > div > div:nth-child(2) > div.Rtable-cell.Rtable-cell--2of3.Rtable-cell--rowEnd > strong > span"
        
        # Alternative: Search for address structure
        address_locator = page.locator("address").first
        if await address_locator.count() > 0:
            items = await address_locator.locator(".item").all_inner_texts()
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
        await context.close()
