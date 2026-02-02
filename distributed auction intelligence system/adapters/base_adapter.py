import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class BaseAuctionAdapter(ABC):
    """
    Contract for data extraction. 
    Strictly stateless. No retries or heuristics allowed here.
    """

    def __init__(self, session_id: str = None, proxy_config: Dict[str, Any] = None):
        self.session_id = session_id
        self.proxy_config = proxy_config

    def get_proxy_config(self) -> Optional[Dict[str, str]]:
        """
        Helper to get a random proxy config (Playwright format)
        from local proxies.txt or PROXY_URL env var.
        """
        import os
        import random
        selected_proxy = None
        
        # 1. Try rotating from file
        if os.path.exists("proxies.txt"):
            try:
                with open("proxies.txt", "r") as f:
                    proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                if proxies:
                    selected_proxy = random.choice(proxies)
            except Exception:
                pass
        
        # 2. Fallback to Env Var
        if not selected_proxy:
            selected_proxy = os.getenv("PROXY_URL")
            
        if not selected_proxy:
            return None
            
        # Parse logic
        try:
            proxy_config = {}
            if "://" not in selected_proxy:
                selected_proxy = f"http://{selected_proxy}"

            if "@" in selected_proxy:
                # Use rsplit for safety with passwords
                auth_part, host_part = selected_proxy.split("://")[1].rsplit("@", 1)
                if ":" in auth_part:
                    username, password = auth_part.split(":", 1)
                    proxy_config["username"] = username
                    proxy_config["password"] = password
                proxy_config["server"] = f"http://{host_part}"
            else:
                proxy_config["server"] = selected_proxy
            return proxy_config
        except Exception:
            return None

    @abstractmethod
    async def fetch(self, url: str, preferred_method: int = 0) -> Optional[Dict[str, Any]]:
        """
        Extract data from the URL. 
        Returns a flat dict of fields or None.
        """
        pass
