import asyncio
from playwright.async_api import async_playwright
import logging
import re
from datetime import datetime
import pytz
import os

# Try-except for stealth to avoid hard crash if package version differs
try:
    from playwright_stealth import stealth_async
except ImportError:
    stealth_async = None

logger = logging.getLogger(__name__)

async def scrape_gsa(url: str):
    """
    Precision GSA Scraper (V2.6).
    Fixed Stealth Import for Python 3.12 compatibility.
    Dynamic detection of 'Item Name' and 'Location' blocks.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        # ACTIVATE STEALTH MODE IF AVAILABLE
        if stealth_async:
            await stealth_async(page)
        
        try:
            logger.info(f"[GSA] V2.6 Monitoring: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for content
            try:
                # GSA often takes 5-10 seconds to fully hydrate the React state
                await page.wait_for_selector("text=Item Name", timeout=25000)
                await asyncio.sleep(10) 
            except Exception:
                logger.warning(f"[GSA] Element timeout on {url}. Proceeding with raw capture.")

            # Get the body text - usually more reliable for regex on GSA Dynamic pages
            inner_text = await page.inner_text("body")

            # --- 1. Extraction ---
            item_name = "Unknown GSA Item"
            city, state = "Unknown", "Unknown"
            
            # Name Extraction (Catching the split line pattern)
            nm = re.search(r"Item Name\s*:\s*(.*?)(?:\n|$)", inner_text, re.I)
            if nm:
                # Remove "Sale Lot Number" if it got caught in the same line
                item_name = nm.group(1).split("Sale Lot Number")[0].strip()
            
            # Location Extraction
            loc_match = re.search(r"City,\s*State\s*:\s*(.*?)\s*Closing Time", inner_text, re.DOTALL | re.I)
            if loc_match:
                loc_parts = loc_match.group(1).strip().split(",")
                if len(loc_parts) >= 2:
                    city, state = loc_parts[0].strip(), loc_parts[1].strip()

            # --- 2. Price & Bidders ---
            current_bid = 0.0
            total_bidders = 0
            pm = re.search(r"Current Bid:\s*\$?\s*([\d,]+\.?\d*)", inner_text, re.I)
            if pm: current_bid = float(pm.group(1).replace(",", ""))
            bm = re.search(r"Bidders:\s*(\d+)", inner_text, re.I)
            if bm: total_bidders = int(bm.group(1))

            # --- 3. Timezone ---
            closing_time_iso = None
            # GSA Date Format: 01/29/2026 12:00 PM CT
            closing_match = re.search(r"Closing Time:\s*(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})\s*CT", inner_text, re.I)
            if closing_match:
                try:
                    naive_dt = datetime.strptime(closing_match.group(1).strip(), "%m/%d/%Y %I:%M %p")
                    utc_dt = pytz.timezone('US/Central').localize(naive_dt).astimezone(pytz.UTC)
                    closing_time_iso = utc_dt.isoformat()
                except: pass

            # --- 4. Timer ---
            time_str = "Syncing..."
            parts = re.findall(r"(\d+)\s*([dhms])", inner_text)
            if parts:
                time_str = "".join([f"{p[0]}{p[1]} " for p in parts]).strip()

            logger.info(f"[GSA] V2.6 Sync Result: {item_name[:25]}... | Bid: ${current_bid}")

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
            logger.error(f"[GSA] Critical Failure: {e}")
            return None
        finally:
            await browser.close()
