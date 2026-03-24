import asyncio
import logging
import os
import sys
import json
from datetime import datetime

# Add current directory to path for clean imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adapters.mazree import MazreeAdapter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_scraper(url: str):
    print(f"\n--- Mazree Local Test Mode ---")
    print(f"Target URL: {url}")
    
    # 1. Check for session file
    session_path = os.path.join(os.path.dirname(__file__), ".sessions", "mazree_session.json")
    if not os.path.exists(session_path):
        print(f"WARNING: Session file not found at {session_path}")
        print("Please run 'python bot/save_mazree_session.py' first.")
        # We can still continue, it will try automated login
    else:
        print(f"SUCCESS: Found session file. Using authenticated state.")

    adapter = MazreeAdapter()
    
    # Execute fetch
    print("\nStarting extraction (this may take 15-20 seconds due to Angular hydration)...")
    result = await adapter.fetch(url)
    
    if result:
        print("\n--- EXTRACTION SUCCESS ---")
        print(json.dumps(result, indent=4))
        
        # Additional validation
        if result['item_name'] == "Unknown Item" or "The place to buy" in result['item_name']:
            print("\nALERT: Scraper caught the homepage/tagline instead of the item!")
            print("Check 'debug_mazree_test.png' to see the page state.")
        else:
            print("\nSUCCESS: Item correctly identified.")
    else:
        print("\n--- EXTRACTION FAILED ---")
        print("Check logs above for errors.")

if __name__ == "__main__":
    # Example URL (replace with any Mazree item URL you want to test)
    sample_url = "https://www.mazree.com/buyers/listing-detail/1e23093a-bf08-4ae2-8184-3c40e190f08f"
    
    # Use command line arg if provided
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else sample_url
    
    try:
        asyncio.run(test_scraper(test_url))
    except KeyboardInterrupt:
        pass
