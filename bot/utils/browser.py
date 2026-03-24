"""
Shared Browser Utilities.
Standardized methods for launching resilient Playwright browsers for
reliable data extraction.
"""
import logging

logger = logging.getLogger(__name__)

async def launch_browser(p, **kwargs):
    """
    Standardized browser launch for Docker/Server environments.
    Optimized for memory and stability.
    Supports passing additional arguments like proxy.
    """
    # Default stable Docker arguments
    default_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--no-first-run",
        "--no-zygote",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-browser-side-navigation",
    ]
    default_args.extend(kwargs.pop('args', []))
    
    return await p.chromium.launch(
        headless=kwargs.get('headless', True),
        args=default_args,
        **kwargs
    )
