import logging
from parsers.gsa import scrape_gsa
from parsers.bidspotter import scrape_bidspotter
from parsers.centurion import scrape_centurion
from parsers.bma import scrape_bma
from parsers.globalmed import scrape_globalmed
from parsers.dotmed import scrape_dotmed
from parsers.mazree import scrape_mazree
from parsers.govplanet import scrape_govplanet
from parsers.directbids import scrape_directbids
from parsers.surplusmarketplace import scrape_surplusmarketplace
from parsers.gcsurplus import scrape_gcsurplus
from parsers.greenpulse import scrape_greenpulse
from parsers.troostwijk import scrape_troostwijk
from parsers.publicsurplus import scrape_publicsurplus
from parsers.purplewave import scrape_purplewave

logger = logging.getLogger(__name__)

async def get_auction_data(url: str):
    """
    Routes a URL to the appropriate scraper based on the domain.
    """
    try:
        if "gsaauctions.gov" in url:
            return await scrape_gsa(url)
        elif "bidspotter.com" in url:
            return await scrape_bidspotter(url)
        elif "centurionservice.com" in url:
            return await scrape_centurion(url)
        elif "britishmedicalauctions.com" in url:
            return await scrape_bma(url)
        elif "globalmedauctions.com" in url:
            return await scrape_globalmed(url)
        elif "dotmed.com" in url:
            return await scrape_dotmed(url)
        elif "mazree.com" in url:
            return await scrape_mazree(url)
        elif "govplanet.com" in url:
            return await scrape_govplanet(url)
        elif "directbids.com" in url:
            return await scrape_directbids(url)
        elif "surplusmarketplace.com" in url:
            return await scrape_surplusmarketplace(url)
        elif "gcsurplus.ca" in url:
            return await scrape_gcsurplus(url)
        elif "greenpulse.health" in url:
            return await scrape_greenpulse(url)
        elif "troostwijkauctions.com" in url:
            return await scrape_troostwijk(url)
        elif "publicsurplus.com" in url:
            return await scrape_publicsurplus(url)
        elif "purplewave.com" in url:
            return await scrape_purplewave(url)
        
        # Placeholder for other sites - we will implement a generic 
        # fallback for now and add specific logic as needed.
        return await scrape_generic(url)
        
    except Exception as e:
        logger.error(f"Routing error for {url}: {e}")
        return None

async def scrape_generic(url: str):
    """
    A fallback scraper that uses common patterns for many auction sites.
    """
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Common patterns for Item Names
            item_name = "Unknown Item"
            selectors = ["h1", "h2", ".title", ".product-name", "#itemTitle"]
            for sel in selectors:
                if await page.locator(sel).count() > 0:
                    text = await page.locator(sel).first.inner_text()
                    if text.strip():
                        item_name = text.strip()
                        break

            # Common patterns for Bids
            current_bid = 0.0
            bid_selectors = [".bid-amount", ".current-bid", ".price", ".amount"]
            for sel in bid_selectors:
                if await page.locator(sel).count() > 0:
                    text = await page.locator(sel).first.inner_text()
                    try:
                        clean_text = text.replace("$", "").replace(",", "").strip()
                        current_bid = float(clean_text)
                        break
                    except: continue

            return {
                "item_name": item_name,
                "current_bid": current_bid,
                "website_name": url.split("//")[-1].split("/")[0],
                "status": "active"
            }
        except Exception as e:
            logger.error(f"Generic scrape failed for {url}: {e}")
            return None
        finally:
            await browser.close()
