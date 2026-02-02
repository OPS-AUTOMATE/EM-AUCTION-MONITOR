import hashlib
import logging

logger = logging.getLogger(__name__)

class ProxyManager:
    """
    Orthogonal utility for proxy identity. 
    Does not make decisions about when or how to scrape.
    """

    @staticmethod
    def get_session_id(item_id: str, site_key: str) -> str:
        """
        Deterministic mapping of Item to Session ID for IP stickiness.
        """
        raw_id = str(item_id)
        raw_key = str(site_key)
        # Consistent hash ensures same session_id for the life of the item
        return hashlib.sha256(f"{raw_id}:{raw_key}".encode()).hexdigest()

    @staticmethod
    def get_proxy_config(session_id: str):
        """
        Returns a static proxy config structure based on the session_id.
        No retry or rotation logic here.
        """
        # In production, this would return the proxy URL with session_id appended
        # e.g. f"http://user-session-{session_id}:pass@proxy.provider.com:8000"
        return None
