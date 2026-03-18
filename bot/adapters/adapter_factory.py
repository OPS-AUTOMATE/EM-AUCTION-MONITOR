from typing import Dict, Type, Optional
from urllib.parse import urlparse
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
from .allsurplus import AllSurplusAdapter
from .equipnet import EquipNetAdapter

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
    "allsurplus": AllSurplusAdapter,
    "equipnet": EquipNetAdapter,
}

def detect_site_key(url: str) -> str:
    """
    Analyzes the URL to determine the correct site_key.
    Used as a fallback if the DB has 'mock' or missing site_key.
    """
    # Parse the URL and inspect the hostname instead of doing substring checks
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except Exception:
        host = ""

    if not host:
        return "mock"

    # Map known hostnames to site keys. This can be extended to support
    # subdomains if needed (e.g., host.endswith(".gsaauctions.gov")).
    if host == "gsaauctions.gov" or host.endswith(".gsaauctions.gov"):
        return "gsa"
    if host == "centurionservice.com" or host.endswith(".centurionservice.com"):
        return "centurion"
    if host == "bidspotter.com" or host.endswith(".bidspotter.com"):
        return "bidspotter"
    if host == "govplanet.com" or host.endswith(".govplanet.com"):
        return "govplanet"
    if host == "purplewave.com" or host.endswith(".purplewave.com"):
        return "purplewave"
    if host == "mazree.com" or host.endswith(".mazree.com"):
        return "mazree"
    if host == "directbids.com" or host.endswith(".directbids.com"):
        return "directbids"
    if host == "dotmed.com" or host.endswith(".dotmed.com"):
        return "dotmed"
    if host == "britishmedicalauctions.com" or host.endswith(".britishmedicalauctions.com"):
        return "bma"
    if host == "surplusmarketplace.com" or host.endswith(".surplusmarketplace.com"):
        return "surplusmarketplace"
    if host == "globalmedauctions.com" or host.endswith(".globalmedauctions.com"):
        return "globalmed"
    if host == "gcsurplus.ca" or host.endswith(".gcsurplus.ca"):
        return "gcsurplus"
    if host == "publicsurplus.com" or host.endswith(".publicsurplus.com"):
        return "publicsurplus"
    if host == "troostwijkauctions.com" or host.endswith(".troostwijkauctions.com"):
        return "troostwijk"
    if host == "greenpulse.health" or host.endswith(".greenpulse.health"):
        return "greenpulse"
    if host == "allsurplus.com" or host.endswith(".allsurplus.com"):
        return "allsurplus"
    if host == "equipnet.com" or host.endswith(".equipnet.com"):
        return "equipnet"
    return "mock"

def get_adapter(site_key: str) -> Optional[Type[BaseAuctionAdapter]]:
    """
    Returns the specific adapter for the site_key.
    Returns None if no hardened adapter is found.
    """
    key = str(site_key).lower().strip()
    return ADAPTER_MAP.get(key)
