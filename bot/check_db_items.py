import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def check_items():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_KEY")
        return

    supabase = create_client(url, key)
    try:
        response = supabase.table("auction_items").select("id, item_name, website_name, status, next_fetch_at").execute()
        items = response.data
        print(f"Total items in auction_items: {len(items)}")
        for i, item in enumerate(items[:5]):
            print(f"{i+1}. [{item.get('website_name')}] {item.get('item_name')} - Status: {item.get('status')} - Next: {item.get('next_fetch_at')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_items()
