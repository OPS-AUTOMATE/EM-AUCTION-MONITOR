import re
import logging

logger = logging.getLogger(__name__)

async def apply_bandwidth_saver(page):
    """
    Lean Firewall to block heavy resources (images, maps, tracking).
    Keeps only necessary requests for scraping.
    """
    # Initialize basic request counter
    if not hasattr(page, "tracker"):
        page.tracker = {
            "request_count": 0, 
            "blocked_count": 0
        }

    # 1. Block by file extension
    BLOCK_EXTENSIONS = [
        "jpg", "jpeg", "png", "gif", "webp", "svg", "ico",
        "woff", "woff2", "ttf", "otf",
        "css",
        "mp4", "webm", "avi",
        "wasm", "pbf", "geojson",
        "js.map", "map"
    ]
    ext_pattern = re.compile(r"\.(" + "|".join(BLOCK_EXTENSIONS) + r")", re.I)

    # 2. Block by Keyword
    BLOCK_KEYWORDS = [
        "google-analytics", "doubleclick", "facebook", "clarity", 
        "hotjar", "hubspot", "marketo", "intercom", "segment",
        "gtm.js", "collect?v=", "analytics", "ads", "telemetry",
        "mapbox", "tiles.mapbox", "arcgis", "ruxitagentjs", 
        "dynatrace", "zendesk", "drift", "onetrust", 
        "openreplay", "appinsights", "optanon", "newrelic",
        "vimeo", "youtube", "arcgis.com", "google.com/maps"
    ]
    keyword_pattern = re.compile("|".join(BLOCK_KEYWORDS), re.I)

    async def intercept_route(route):
        url = route.request.url.lower()
        if keyword_pattern.search(url) or ext_pattern.search(url):
            page.tracker["blocked_count"] += 1
            return await route.abort()
        
        page.tracker["request_count"] += 1
        await route.continue_()

    # Route interception is sufficient for blocking
    await page.route("**/*", intercept_route)

def get_bandwidth_summary(page):
    """Returns a simplified summary of firewall performance."""
    stats = getattr(page, "tracker", {
        "request_count": 0, 
        "blocked_count": 0
    })
    
    return (
        f" [Firewall] {stats['request_count']} passed, {stats['blocked_count']} blocked"
    )
