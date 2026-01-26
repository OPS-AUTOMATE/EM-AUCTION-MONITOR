import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def scrape_govplanet(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            logger.info(f"Navigating to GovPlanet: {url}")
            await page.goto(url, wait_until="networkidle", timeout=45000)
            item_name = await page.locator(".item-title, h1").first.inner_text()
            bid_text = await page.locator(".bid-price, .current-bid").first.inner_text()
            current_bid = float(bid_text.replace("$", "").replace(",", "").strip())
            return {
                "item_name": item_name.strip(),
                "current_bid": current_bid,
                "website_name": "GovPlanet"
            }
        except Exception as e:
            logger.error(f"GovPlanet scrape error: {e}")
            return None
        finally:
            await browser.close()
