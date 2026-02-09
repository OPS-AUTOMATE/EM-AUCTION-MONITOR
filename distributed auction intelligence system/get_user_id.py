import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def get_user_id():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)
    response = supabase.table("auction_items").select("user_id").limit(1).execute()
    if response.data:
        print(response.data[0]['user_id'])
    else:
        print("None")

if __name__ == "__main__":
    get_user_id()
