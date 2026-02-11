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
            # Sticky session: verify if still valid? No, just map consistent index.
            # Convert session_id (hash) to int to index into proxy list
            try:
                idx = int(session_id, 16) % len(proxies)
                selected_proxy = proxies[idx]
            except:
                selected_proxy = random.choice(proxies)
        else:
            selected_proxy = random.choice(proxies)
            
        # Parse into Dict for Playwright / Adapter use
        try:
            proxy_config = {}
            if "://" not in selected_proxy:
                selected_proxy = f"http://{selected_proxy}"

            if "@" in selected_proxy:
                # Use rsplit for safety with passwords containing '@'? No, usually valid.
                # Format: scheme://user:pass@host:port
                auth_part, host_part = selected_proxy.split("://")[1].rsplit("@", 1)
                if ":" in auth_part:
                    username, password = auth_part.split(":", 1)
                    proxy_config["username"] = username
                    proxy_config["password"] = password
                proxy_config["server"] = f"http://{host_part}"
            else:
                proxy_config["server"] = selected_proxy
            return proxy_config
        except Exception as e:
            logger.error(f"Error parsing proxy '{selected_proxy}': {e}")
            return None
