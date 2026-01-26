import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def scrape_publicsurplus(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
            item_name = await page.locator("h1, .auction-title").first.inner_text()
            bid_text = await page.locator(".current-bid, .amount").first.inner_text()
            current_bid = float(bid_text.replace("$", "").replace(",", "").strip())
            return {"item_name": item_name.strip(), "current_bid": current_bid, "website_name": "Public Surplus"}
        except Exception as e:
            logger.error(f"Public Surplus error: {e}")
            return None
        finally: await browser.close()
