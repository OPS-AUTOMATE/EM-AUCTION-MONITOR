import asyncio
import os
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def save_session():
    # Correct path to match mazree.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    session_dir = os.path.join(base_dir, ".sessions")
    os.makedirs(session_dir, exist_ok=True)
    storage_path = os.path.join(session_dir, "mazree_session.json")

    print(f"\n--- Mazree Session Saver (Stealth Mode) ---")
    print(f"Target path: {storage_path}")
    print(f"1. A browser window will open.")
    print(f"2. Please log in to Mazree manually.")
    print(f"3. IMPORTANT: If 'Next' is disabled, wait 5 seconds and try typing again.")
    print(f"4. Once on the dashboard, come back here and press Enter.")

    async with async_playwright() as p:
        # Launch non-headless browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Apply stealth to bypass bot detection
        await Stealth().apply_stealth_async(page)

        await page.goto("https://www.mazree.com/SignIn")

        input(">>> Login manually in the browser, then press ENTER here to save state...")

        # Save the current storage state (cookies, localStorage, etc.)
        await context.storage_state(path=storage_path)
        print(f"SUCCESS: Session saved to {storage_path}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(save_session())
