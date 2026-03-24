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
    
    # Extract headless if provided, default to True
    headless = kwargs.pop('headless', True)
    
    # Combine user args with defaults
    user_args = kwargs.pop('args', [])
    combined_args = list(set(default_args + user_args))
    
    return await p.chromium.launch(
        headless=headless,
        args=combined_args,
        **kwargs
    )
