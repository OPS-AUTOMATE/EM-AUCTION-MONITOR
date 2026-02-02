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

def get_adapter(site_key: str) -> Optional[Type[BaseAuctionAdapter]]:
    """
    Returns the specific adapter for the site_key.
    Returns None if no hardened adapter is found.
    """
    key = str(site_key).lower().strip()
    return ADAPTER_MAP.get(key)
