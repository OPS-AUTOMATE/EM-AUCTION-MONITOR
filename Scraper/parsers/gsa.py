import asyncio
from playwright.async_api import async_playwright, Browser
import logging
import re
from datetime import datetime
import pytz
from utils.bandwidth import apply_bandwidth_saver

logger = logging.getLogger(__name__)

async def scrape_gsa(url: str, browser: Browser = None, context = None):
    """
    Precision GSA Scraper with Timezone Awareness.
    Supports browser reuse and shared caching.
    """
    if context:
        # Use shared context (High Efficiency Caching)
        return await _scrape_with_context(url, context, is_shared=True)
    
    if browser:
        # One-off context for this browser
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        return await _scrape_with_context(url, context, is_shared=False)
    
    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(headless=True)
        context = await temp_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        data = await _scrape_with_context(url, context, is_shared=False)
        await temp_browser.close()
        return data

async def _scrape_with_context(url: str, context, is_shared: bool):
    page = await context.new_page()
    await apply_bandwidth_saver(page)
    
    try:
        logger.info(f"[GSA] Monitoring Start: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        # Wait for content
        await page.wait_for_selector(".ppms-details-container", timeout=15000)
        await asyncio.sleep(6) 

        # Get full text
        main_block = page.locator(".ppms-details-container").first
        full_text = await main_block.inner_text() if await main_block.count() > 0 else await page.content()

        # --- 1. Extract Name & Location ---
        item_name = "Unknown GSA Item"
        city, state = "Unknown", "Unknown"
        
        name_match = re.search(r"Item Name\s*:\s*(.*?)\s*Sale Lot Number", full_text, re.DOTALL | re.I)
        if name_match:
            item_name = name_match.group(1).strip()
        
        # User specified XPath for city/state
        xpath_location = "/html/body/div[1]/main/section/div/div/div[1]/div[1]/div/ul/li/div/div[1]/div[1]/ul/li[3]"
        loc_el = page.locator(f"xpath={xpath_location}")
        if await loc_el.count() > 0:
            loc_text = await loc_el.inner_text()
            # Clean "City, State :" from the text
            loc_text = loc_text.replace("City, State :", "").strip()
            if "," in loc_text:
                parts = loc_text.split(",")
                city = parts[0].strip()
                state = parts[1].strip()
        elif "," in full_text:
            loc_match = re.search(r"City,\s*State\s*:\s*(.*?)\s*Closing Time", full_text, re.DOTALL | re.I)
            if loc_match:
                loc_text = loc_match.group(1).strip()
                if "," in loc_text:
                    parts = loc_text.split(",")
                    city = parts[0].strip()
                    state = parts[1].strip()

        # --- 2. Extract Price & Bidders ---
        current_bid = 0.0
        total_bidders = 0
        price_match = re.search(r"Current Bid:\s*\$?\s*([\d,]+\.?\d*)", full_text, re.I)
        if price_match: current_bid = float(price_match.group(1).replace(",", ""))
        
        bidder_match = re.search(r"Bidders:\s*(\d+)", full_text, re.I)
        if bidder_match: total_bidders = int(bidder_match.group(1))

        # --- 3. Extract Status & Closing Time (User XPaths) ---
        status = "active"
        closing_time_iso = None

        # User specified XPaths
        xpath_status = "/html/body/div[1]/main/section/div/div/div[1]/div[1]/div/ul/li/div/div[2]/div[2]/div/div/ul/li[12]"
        xpath_closing = "/html/body/div[1]/main/section/div/div/div[1]/div[1]/div/ul/li/div/div[2]/div[2]/div/div/ul/li[11]"

        # Check Status first
        status_el = page.locator(f"xpath={xpath_status}")
        if await status_el.count() > 0:
            status_text = await status_el.inner_text()
            logger.info(f"[GSA] Status detected: {status_text}")
            if "closed" in status_text.lower() or "bid closed" in status_text.lower():
                status = "expired"

        # Check Closing Time via XPath
        closing_el = page.locator(f"xpath={xpath_closing}")
        raw_closing_str = None
        if await closing_el.count() > 0:
            raw_closing_str = await closing_el.inner_text()
            # Clean label if present
            raw_closing_str = raw_closing_str.replace("Closing Time :", "").strip()

        # Fallback to Regex if XPath failed or returned empty
        if not raw_closing_str:
            search_target = await page.content()
            patterns = [
                r"(?:Closing Time|Ends|Closes|Bid Closes|End Date)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})\s*CT",
                r"(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})\s*CT",
                r"(?:Closing Time|Ends|Closes)\s*[:\-]?\s*(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})"
            ]
            for pattern in patterns:
                m = re.search(pattern, search_target, re.I)
                if m:
                    raw_closing_str = m.group(1).strip()
                    break

        if raw_closing_str:
            try:
                # Basic cleaning
                date_str = raw_closing_str.strip()
                # Handle lack of space before AM/PM (e.g. 01:15PM -> 01:15 PM)
                # More robust: find PM/AM and ensure there's a space before it
                date_str = re.sub(r'(\d{1,2}:\d{2})\s*([APM]{2})', r'\1 \2', date_str, flags=re.I)
                # Remove any remaining label like "Closing Time :" or "Status"
                date_str = re.sub(r'[^0-9/: APM]', '', date_str).strip()
                
                naive_dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
                central = pytz.timezone('US/Central')
                localized_dt = central.localize(naive_dt)
                utc_dt = localized_dt.astimezone(pytz.UTC)
                closing_time_iso = utc_dt.isoformat()
            except Exception as e:
                logger.warning(f"[GSA] Final date parse error for '{raw_closing_str}': {e}")

        # --- 4. Extract Remaining Time String ---
        time_str = "Syncing..."
        if status == "expired":
            time_str = "Ended"
        else:
            time_match = re.search(r"(?:Ends In|Remaining):?\s*((?:\d+[dhms]\s*)+)", await page.content(), re.I)
            if time_match:
                time_str = time_match.group(1).strip()
            elif closing_time_iso:
                try:
                    now = datetime.now(pytz.UTC)
                    closing_dt = datetime.fromisoformat(closing_time_iso)
                    diff = closing_dt - now
                    if diff.total_seconds() > 0:
                        days = diff.days
                        hours, remainder = divmod(diff.seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        time_str = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"
                    else:
                        time_str = "Ended"
                        status = "expired"
                except: pass

        # Get summary from bandwidth utility
        from utils.bandwidth import get_bandwidth_summary
        summary = get_bandwidth_summary(page)
        logger.info(f"[GSA] {summary}")

        return {
            "item_name": item_name.strip(),
            "current_bid": current_bid,
            "total_bidders": total_bidders,
            "time_remaining_str": time_str,
            "closing_time": closing_time_iso,
            "city": city,
            "state": state,
            "website_name": "GSA Auctions",
            "status": status
        }

    except Exception as e:
        logger.error(f"[GSA] Scrape Failure: {e}")
        return None
    finally:
        await page.close() 
        if not is_shared:
            await context.close()
