"""
Base Adapter Module.
Defines the abstract base class and common utilities for all auction-specific adapters.
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from utils.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)

class BaseAuctionAdapter(ABC):
    """
    Contract for data extraction.
    Strictly stateless. No retries or heuristics allowed here.
    """

    def __init__(self, session_id: Optional[str] = None, proxy_config: Optional[Dict[str, Any]] = None):
        self.session_id = session_id
        self.proxy_config = proxy_config

    def get_proxy_config(self) -> Optional[Dict[str, str]]:
        """
        Helper to get a sticky proxy config based on the session ID.
        Delegates to the central ProxyManager.
        """
        return ProxyManager.get_proxy_config(self.session_id)

    @abstractmethod
    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        """
        Extract data from the URL.
        Returns a flat dict of fields or None.
        """
