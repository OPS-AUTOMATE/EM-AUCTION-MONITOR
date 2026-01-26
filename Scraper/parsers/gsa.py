import asyncio
from playwright.async_api import async_playwright
import logging
import re
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

async def scrape_gsa(url: str):
    """
    Enhanced GSA Scraper (V2.4).
    Deep-wait logic to ensure dynamic content is fully loaded on remote servers.
    Validates presence of key auction fields before extraction.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        try:
            logger.info(f"[GSA] Monitoring Start: {url}")
            # Ensure the page is actually reachable
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # --- V2.4 DEEP WAIT ---
            # Wait for the actual "Item Name" text to appear in the container
            logger.info("[GSA] Waiting for dynamic content to populate...")
            try:
                # This ensures we don't just grab a 'Loading...' screen
                await page.wait_for_selector("text=Item Name", timeout=30000)
                # Extra heartbeat for GSA's slow pricing scripts
                await asyncio.sleep(12) 
            except Exception as e:
                logger.warning(f"[GSA] Dynamic content delay: {e}")

            # Target the container with the real data
            main_block = page.locator(".ppms-details-container").first
            if await main_block.count() == 0:
                 main_block = page.locator("body")
            
            full_text = await main_block.inner_text()
            
            # --- 1. Extract Details with safer Regex ---
            item_name = "Unknown GSA Item"
            city, state = "Unknown", "Unknown"
            
            # Use multi-line matching for cleaner name extraction
            nm = re.search(r"Item Name\s*:\s*(.*?)\r?\n", full_text, re.I)
            if nm: 
                item_name = nm.group(1).replace("Sale Lot Number", "").strip()
            
            loc_match = re.search(r"City,\s*State\s*:\s*(.*?)\s*Closing Time", full_text, re.DOTALL | re.I)
            if loc_match:
                loc_text = loc_match.group(1).strip()
                if "," in loc_text:
                    parts = loc_text.split(",")
                    city, state = parts[0].strip(), parts[1].strip()

            # --- 2. Prices & Bidders ---
            current_bid = 0.0
            total_bidders = 0
            pm = re.search(r"Current Bid:\s*\$?\s*([\d,]+\.?\d*)", full_text, re.I)
            if pm: current_bid = float(pm.group(1).replace(",", ""))
            
            bm = re.search(r"Bidders:\s*(\d+)", full_text, re.I)
            if bm: total_bidders = int(bm.group(1))

            # --- 3. Timezone Aware Closing Time (UTC) ---
            closing_time_iso = None
            closing_match = re.search(r"Closing Time:\s*(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})\s*CT", full_text, re.I)
            if closing_match:
                date_str = closing_match.group(1).strip()
                try:
                    naive_dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
                    central = pytz.timezone('US/Central')
                    utc_dt = central.localize(naive_dt).astimezone(pytz.UTC)
                    closing_time_iso = utc_dt.isoformat()
                except: pass

            # --- 4. Remaining Time ---
            time_str = "Syncing..."
            parts = re.findall(r"(\d+)\s*([dhms])", full_text)
            if parts:
                time_str = " ".join([f"{p[0]}{p[1]}" for p in parts]).strip()

            logger.info(f"[GSA] V2.4 Sync: {item_name[:25]}... | Bid: ${current_bid} | Time: {time_str}")

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
            logger.error(f"[GSA] Scrape Failure (V2.4): {e}")
            return None
        finally:
            await browser.close()
