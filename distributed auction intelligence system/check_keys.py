import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def check_keys():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)
    
    response = supabase.table("auction_items").select("site_key, item_name, status, website_name, error_message").execute()
    for item in response.data:
        if item.get('site_key') in ['directbids', 'gcsurplus', 'troostwijk', 'mazree']:
            print(f"KEY: {item.get('site_key')} | SITE: {item.get('website_name')} | NAME: {item.get('item_name')} | STATUS: {item.get('status')} | ERR: {item.get('error_message')}")

if __name__ == "__main__":
    check_keys()
