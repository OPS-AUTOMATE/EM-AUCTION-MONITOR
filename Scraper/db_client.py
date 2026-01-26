import os
import logging
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Configure logger for this module
logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
    
    # Simple log to confirm DB access
    logger.info("Database credentials found, connecting to Supabase...")
    return create_client(url, key)
