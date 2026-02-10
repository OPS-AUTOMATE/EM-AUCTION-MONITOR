import asyncio
import os
import random
import json
from playwright.async_api import async_playwright

async def get_ip(page, name):
    try:
        await page.goto("https://api.ipify.org?format=json", timeout=10000)
        content = await page.inner_text("body")
        data = json.loads(content)
        print(f"[{name}] IP: {data.get('ip')}")
        return data.get('ip')
    except Exception as e:
        print(f"[{name}] Error: {e}")
        return None

async def main():
    print("--- Proxy Verification Test ---")
    
    # 1. Parse Proxy from proxies.txt
    proxy_config = None
    raw_proxy = None
    
    if os.path.exists("proxies.txt"):
        with open("proxies.txt", "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        if lines:
            raw_proxy = random.choice(lines)
            print(f"Selected Proxy raw: {raw_proxy}")
            
            # Parsing Logic
            try:
                conf = {}
                if "://" not in raw_proxy: raw_proxy = f"http://{raw_proxy}"
                
                if "@" in raw_proxy:
                    auth_part, host_part = raw_proxy.split("://")[1].rsplit("@", 1)
                    if ":" in auth_part:
                        u, p = auth_part.split(":", 1)
                        conf["username"] = u
                        conf["password"] = p
                    conf["server"] = f"http://{host_part}"
                else:
                    conf["server"] = raw_proxy
                
                proxy_config = conf
            except Exception as e:
                print(f"Parsing failed: {e}")
                return

    if not proxy_config:
        print("No proxy found in proxies.txt")
        return

    async with async_playwright() as p:
        # Step 2: Check Local IP (No Proxy)
        print("\nChecking LOCAL IP...")
        browser_local = await p.chromium.launch()
        page_local = await browser_local.new_page()
        local_ip = await get_ip(page_local, "LOCAL")
        await browser_local.close()

        # Step 3: Check Proxy IP
        print(f"\nChecking PROXY IP ({proxy_config['server']})...")
        try:
            browser_proxy = await p.chromium.launch(proxy=proxy_config)
            page_proxy = await browser_proxy.new_page()
            proxy_ip = await get_ip(page_proxy, "PROXY")
            await browser_proxy.close()
        except Exception as e:
            print(f"Proxy Connection Failed: {e}")
            return

    # Result
    print("\n--- RESULT ---")
    if local_ip and proxy_ip:
        if local_ip != proxy_ip:
            print(f"✅ SUCCESS! Proxy is working. IPs are different.\nLocal: {local_ip}\nProxy: {proxy_ip}")
        else:
            print(f"❌ FAILURE! IPs are the same. Proxy is NOT being used.")
    else:
        print("❌ Could not verify IPs.")

if __name__ == "__main__":
    asyncio.run(main())
