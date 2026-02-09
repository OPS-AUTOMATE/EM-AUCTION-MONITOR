import os
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()

def force_due():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)
    
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    print(f"Forcing items to be due (Next: {past})")
    
    # Update active items
    supabase.table("auction_items").update({
        "next_fetch_at": past,
        "locked_until": None
    }).neq("status", "deleted").execute() # Hack to bypass "need a filter"

if __name__ == "__main__":
    force_due()
