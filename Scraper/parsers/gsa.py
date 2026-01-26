import asyncio
from playwright.async_api import async_playwright
import logging
import re
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

async def scrape_gsa(url: str):
    """
    Precision GSA Scraper with Timezone Awareness.
    Converts GSA Central Time (CT) to UTC for correct global display.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        try:
            logger.info(f"[GSA] Monitoring Start: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
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

            # --- 3. Extract Closing Time (Timezone Aware) ---
            closing_time_iso = None
            # Pattern: 01/27/2026 01:15 PM CT
            closing_match = re.search(r"Closing Time:\s*(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})\s*CT", full_text, re.I)
            if closing_match:
                date_str = closing_match.group(1).strip()
                try:
                    # 1. Parse naive datetime
                    naive_dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
                    # 2. Assign US/Central Timezone
                    central = pytz.timezone('US/Central')
                    localized_dt = central.localize(naive_dt)
                    # 3. Convert to UTC for Supabase
                    utc_dt = localized_dt.astimezone(pytz.UTC)
                    closing_time_iso = utc_dt.isoformat()
                    logger.info(f"[GSA] Converted {date_str} CT to {closing_time_iso} UTC")
                except Exception as parse_e:
                    logger.warning(f"[GSA] Timezone parse error: {parse_e}")

            # --- 4. Extract Remaining Time String ---
            time_str = "Syncing..."
            parts = re.findall(r"(\d+)\s*([dhms])", full_text)
            if parts:
                time_str = " ".join([f"{p[0]}{p[1]}" for p in parts]).strip()

            logger.info(f"[GSA] V2.2 Sync: {item_name[:20]}... | Bid: ${current_bid} | Time: {time_str}")

            return {
                "item_name": item_name.strip(),
                "current_bid": current_bid,
                "total_bidders": total_bidders,
                "time_remaining_str": time_str,
                "closing_time": closing_time_iso,
                "city": city,
                "state": state,
                "website_name": "GSA Auctions",
                "status": "active"
            }

        except Exception as e:
            logger.error(f"[GSA] Scrape Failure: {e}")
            return None
        finally:
            await browser.close()
