import asyncio
from playwright.async_api import async_playwright
import logging
import re
from datetime import datetime
import pytz

# Try various stealth imports to find the correct one for his environment
try:
    from playwright_stealth import stealth_async
except ImportError:
    try:
        from playwright_stealth import stealth as stealth_async
    except ImportError:
        stealth_async = None

logger = logging.getLogger(__name__)

async def scrape_gsa(url: str):
    """
    Detective GSA Scraper (V2.7).
    Includes deep logging of page content on failure to diagnose server-side blocks.
    Uses 'networkidle' for more robust loading of React components.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        # Higher range User-Agent to look like a modern Windows 11 laptop
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )
        page = await context.new_page()
        
        if stealth_async:
            try:
                await stealth_async(page)
            except: pass
        
        try:
            logger.info(f"[GSA] V2.7 Monitoring (Stealth): {url}")
            
            # Use 'networkidle' - this waits until the page stops loading data
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # --- V2.7 DIAGNOSTIC CHECK ---
            try:
                await page.wait_for_selector("text=Item Name", timeout=15000)
            except:
                title = await page.title()
                content_snippet = (await page.inner_text("body"))[:200].replace("\n", " ")
                logger.error(f"[GSA] BLOCK DETECTED? Title: '{title}' | Content: '{content_snippet}'")

            inner_text = await page.inner_text("body")

            # --- Extraction ---
            item_name = "Unknown GSA Item"
            current_bid = 0.0
            
            nm = re.search(r"Item Name\s*:\s*(.*?)(?:\n|$)", inner_text, re.I)
            if nm: item_name = nm.group(1).split("Sale Lot Number")[0].strip()
            
            pm = re.search(r"Current Bid:\s*\$?\s*([\d,]+\.?\d*)", inner_text, re.I)
            if pm: current_bid = float(pm.group(1).replace(",", ""))

            # (Rest of extraction logic stays same for reliability)
            city, state = "Unknown", "Unknown"
            loc_match = re.search(r"City,\s*State\s*:\s*(.*?)\s*Closing Time", inner_text, re.DOTALL | re.I)
            if loc_match:
                pts = loc_match.group(1).strip().split(",")
                if len(pts) >= 2: city, state = pts[0].strip(), pts[1].strip()

            closing_time_iso = None
            closing_match = re.search(r"Closing Time:\s*(\d{2}/\d{2}/\d{4}\s*\d{2}:\d{2}\s*[APM]{2})\s*CT", inner_text, re.I)
            if closing_match:
                try:
                    naive_dt = datetime.strptime(closing_match.group(1).strip(), "%m/%d/%Y %I:%M %p")
                    utc_dt = pytz.timezone('US/Central').localize(naive_dt).astimezone(pytz.UTC)
                    closing_time_iso = utc_dt.isoformat()
                except: pass

            time_str = "Syncing..."
            parts = re.findall(r"(\d+)\s*([dhms])", inner_text)
            if parts: time_str = "".join([f"{p[0]}{p[1]} " for p in parts]).strip()

            logger.info(f"[GSA] V2.7 Result: {item_name[:25]}... | Bid: ${current_bid}")

            return {
                "item_name": item_name.strip(),
                "current_bid": current_bid,
                "total_bidders": 0, # Fallback
                "time_remaining_str": time_str,
                "closing_time": closing_time_iso,
                "city": city,
                "state": state,
                "website_name": "GSA Auctions",
                "status": "active"
            }

        except Exception as e:
            logger.error(f"[GSA] V2.7 Error: {e}")
            return None
        finally:
            await browser.close()
