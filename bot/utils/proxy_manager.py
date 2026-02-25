import hashlib
import logging
from typing import List, Optional, Dict

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
    def get_proxy_config(session_id: str = None):
        """
        Returns a proxy config structure based on the session_id (sticky) or random.
        Parses from local proxies.txt.
        """
        import os
        import random
        
        proxies = []
        if os.path.exists("proxies.txt"):
            try:
                with open("proxies.txt", "r") as f:
                    proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            except Exception as e:
                logger.error(f"Error reading proxies.txt: {e}")
        
        # Fallback to Env Var
        if not proxies:
            env_proxy = os.getenv("PROXY_URL")
            if env_proxy:
                proxies = [env_proxy]
                
        if not proxies:
            return None
            
        # Selection Logic
        selected_proxy = None
        if session_id:
            try:
                idx = int(session_id, 16) % len(proxies)
                selected_proxy = proxies[idx]
            except:
                selected_proxy = random.choice(proxies)
        else:
            selected_proxy = random.choice(proxies)
            
        return self.parse_proxy_to_config(selected_proxy)

    @staticmethod
    def get_all_proxies() -> List[str]:
        """Returns a list of raw proxy strings from proxies.txt."""
        import os
        proxies = []
        if os.path.exists("proxies.txt"):
            try:
                with open("proxies.txt", "r") as f:
                    proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            except Exception as e:
                logger.error(f"Error reading proxies.txt: {e}")
        return proxies

    @classmethod
    def parse_proxy_to_config(cls, proxy_str: str) -> Optional[Dict[str, str]]:
        """
        Parses a raw proxy string into a config dict.
        Supports:
        - scheme://user:pass@host:port
        - host:port:user:pass
        - host:port
        """
        if not proxy_str: return None
        try:
            proxy_config = {}
            
            # 1. Handle Colon Format (host:port:user:pass)
            if "://" not in proxy_str and proxy_str.count(":") == 3:
                parts = proxy_str.split(":")
                proxy_config["server"] = f"http://{parts[0]}:{parts[1]}"
                proxy_config["username"] = parts[2]
                proxy_config["password"] = parts[3]
                return proxy_config

            # 2. Handle standard URI formats
            if "://" not in proxy_str:
                proxy_str = f"http://{proxy_str}"

            if "@" in proxy_str:
                scheme, remainder = proxy_str.split("://", 1)
                auth_part, host_part = remainder.rsplit("@", 1)
                if ":" in auth_part:
                    username, password = auth_part.split(":", 1)
                    proxy_config["username"] = username
                    proxy_config["password"] = password
                proxy_config["server"] = f"{scheme}://{host_part}"
            else:
                proxy_config["server"] = proxy_str
                
            return proxy_config
        except Exception as e:
            logger.error(f"Error parsing proxy '{proxy_str}': {e}")
            return None
