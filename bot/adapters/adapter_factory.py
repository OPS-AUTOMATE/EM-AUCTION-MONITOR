from typing import Dict, Type, Optional
from .base_adapter import BaseAuctionAdapter
from .gsa import GsaAdapter
from .bidspotter import BidspotterAdapter
from .centurion import CenturionAdapter
from .govplanet import GovPlanetAdapter
from .purplewave import PurpleWaveAdapter
from .mazree import MazreeAdapter
from .dotmed import DotMedAdapter
from .bma import BmaAdapter
from .surplusmarketplace import SurplusMarketplaceAdapter
from .globalmed import GlobalMedAdapter
from .directbids import DirectBidsAdapter
from .gcsurplus import GCSurplusAdapter
from .publicsurplus import PublicSurplusAdapter
from .troostwijk import TroostwijkAdapter
from .greenpulse import GreenPulseAdapter

# Strict Adapter Registry
# Every site key maps to its dedicated production-grade driver.
ADAPTER_MAP: Dict[str, Type[BaseAuctionAdapter]] = {
    "gsa": GsaAdapter,
    "bidspotter": BidspotterAdapter,
    "centurion": CenturionAdapter,
    "govplanet": GovPlanetAdapter,
    "purplewave": PurpleWaveAdapter,
    "mazree": MazreeAdapter,
    "dotmed": DotMedAdapter,
    "bma": BmaAdapter,
    "surplusmarketplace": SurplusMarketplaceAdapter,
    "globalmed": GlobalMedAdapter,
    "directbids": DirectBidsAdapter,
    "gcsurplus": GCSurplusAdapter,
    "publicsurplus": PublicSurplusAdapter,
    "troostwijk": TroostwijkAdapter,
    "greenpulse": GreenPulseAdapter,
}

def detect_site_key(url: str) -> str:
    """
    Analyzes the URL to determine the correct site_key.
    Used as a fallback if the DB has 'mock' or missing site_key.
    """
    url_lower = url.lower()
    if "gsaauctions.gov" in url_lower: return "gsa"
    if "centurionservice.com" in url_lower: return "centurion"
    if "bidspotter.com" in url_lower: return "bidspotter"
    if "govplanet.com" in url_lower: return "govplanet"
    if "purplewave.com" in url_lower: return "purplewave"
    if "mazree.com" in url_lower: return "mazree"
    if "directbids.com" in url_lower: return "directbids"
    if "dotmed.com" in url_lower: return "dotmed"
    if "britishmedicalauctions.com" in url_lower: return "bma"
    if "surplusmarketplace.com" in url_lower: return "surplusmarketplace"
    if "globalmedauctions.com" in url_lower: return "globalmed"
    if "gcsurplus.ca" in url_lower: return "gcsurplus"
    if "publicsurplus.com" in url_lower: return "publicsurplus"
    if "troostwijkauctions.com" in url_lower: return "troostwijk"
    if "greenpulse.health" in url_lower: return "greenpulse"
    return "mock"

def get_adapter(site_key: str) -> Optional[Type[BaseAuctionAdapter]]:
    """
    Returns the specific adapter for the site_key.
    Returns None if no hardened adapter is found.
    """
    key = str(site_key).lower().strip()
    return ADAPTER_MAP.get(key)
