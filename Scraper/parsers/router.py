import logging
from utils.bandwidth import apply_bandwidth_saver
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
from playwright.async_api import Browser
from parsers.purplewave import scrape_purplewave

logger = logging.getLogger(__name__)

async def get_auction_data(url: str, browser: Browser = None, context = None):
    """
    Routes a URL to the appropriate scraper based on the domain.
    """
    try:
        # Route to specialized parsers
        if "gsaauctions.gov" in url:
            return await scrape_gsa(url, browser=browser, context=context)
        elif "bidspotter.com" in url:
            return await scrape_bidspotter(url, browser=browser, context=context)
        elif "centurionservice.com" in url:
            return await scrape_centurion(url, browser=browser, context=context)
        elif "britishmedicalauctions.com" in url:
            return await scrape_bma(url, browser=browser, context=context)
        elif "govplanet.com" in url:
            return await scrape_govplanet(url, browser=browser, context=context)
        elif "mazree.com" in url:
            return await scrape_mazree(url, browser=browser, context=context)
        elif "dotmed.com" in url:
            return await scrape_dotmed(url, browser=browser, context=context)
        elif "globalmedauction.com" in url:
            return await scrape_globalmed(url, browser=browser, context=context)
        elif "directbids.com" in url:
            return await scrape_directbids(url, browser=browser, context=context)
        elif "surplusmarketplace.com" in url:
            return await scrape_surplusmarketplace(url, browser=browser, context=context)
        elif "gcsurplus.ca" in url:
            return await scrape_gcsurplus(url, browser=browser, context=context)
        elif "greenpulse.com" in url:
            return await scrape_greenpulse(url, browser=browser, context=context)
        elif "troostwijkauctions.com" in url:
            return await scrape_troostwijk(url, browser=browser, context=context)
        elif "publicsurplus.com" in url:
            return await scrape_publicsurplus(url, browser=browser, context=context)
        elif "purplewave.com" in url:
            return await scrape_purplewave(url, browser=browser, context=context)
            
        # Fallback to generic scraper for everything else
        return await scrape_generic(url, browser=browser, context=context)
        
    except Exception as e:
        logger.error(f"Routing error for {url}: {e}")
        return None

async def scrape_generic(url: str, browser: Browser = None, context = None):
    """
    A fallback scraper that uses common patterns for many auction sites.
    """
    if context:
        return await _scrape_generic_with_context(url, context, is_shared=True)

    if browser:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        return await _scrape_generic_with_context(url, context, is_shared=False)
    
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        temp_browser = await p.chromium.launch(headless=True)
        context = await temp_browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        data = await _scrape_generic_with_context(url, context, is_shared=False)
        await temp_browser.close()
        return data

async def _scrape_generic_with_context(url: str, context, is_shared=False):
    page = await context.new_page()
    await apply_bandwidth_saver(page)
    try:
        # domcontentloaded is more resilient than networkidle
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
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

        from utils.bandwidth import get_bandwidth_summary
        summary = get_bandwidth_summary(page)
        logger.info(f"[Generic] {summary}")

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
        await page.close()
        if not is_shared:
            await context.close()
