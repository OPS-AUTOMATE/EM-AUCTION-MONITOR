import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def check_all():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)
    
    response = supabase.table("auction_items").select("website_name, item_name, status, last_scraped_at").execute()
    for item in response.data:
        print(f"[{item.get('website_name')}] {item.get('item_name')} - {item.get('status')} - Last: {item.get('last_scraped_at')}")

if __name__ == "__main__":
    check_all()
