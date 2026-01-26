# Auction Sites Premium Percentages

PREMIUM_MAP = {
    "gsaauctions.gov": 0.00,
    "bid.centurionservice.com": 19.00,
    "britishmedicalauctions.com": 20.00,
    "globalmedauctions.com": 19.00,
    "bidspotter.com": 20.00,
    "dotmed.com": 18.00,
    "mazree.com": 18.00,
    "govplanet.com": 18.00,
    "directbids.com": 15.00,
    "surplusmarketplace.com": 13.00,
    "gcsurplus.ca": 15.00,
    "greenpulse.health": 18.00,
    "troostwijkauctions.com": 0.00, # Varies, handle manually/specifically
    "publicsurplus.com": 10.00,
    "purplewave.com": 10.00
}

def get_premium(url: str) -> float:
    """Helper to get premium % based on domain."""
    for domain, percentage in PREMIUM_MAP.items():
        if domain in url:
            return percentage
    return 0.00
