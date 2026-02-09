import os
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

def seed_test_items():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)
    
    user_id = "6ec3d806-a91a-413e-a54b-6bdce25e1dbd"
    
    items = [
        {
            "user_id": user_id,
            "site_key": "directbids",
            "url": "https://www.directbids.com/laboratory-auctions/lab-instrumentation-lot-abi-3100-genetic-analyzer-co2-incubator-centrifuge-ovens-freezers-3-pallets-jos5x7sz",
            "item_name": "[Local Test] DirectBids Lab Lot",
            "status": "active",
            "next_fetch_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "user_id": user_id,
            "site_key": "gcsurplus",
            "url": "https://gcsurplus.ca/mn-eng.cfm?snc=wfsav&sc=enc-bid&scn=575760&lcn=735514&lct=L&srchtype=&lci=&str=1&lotnf=1&frmsr=1&sf=ferm-clos&saleType=",
            "item_name": "[Local Test] GCSurplus Carbon",
            "status": "active",
            "next_fetch_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "user_id": user_id,
            "site_key": "troostwijk",
            "url": "https://www.troostwijkauctions.com/en/l/2013-covidien-forcetriad-electrosurgical-unit-A1-41113-1025?source=eyJ0eXBlIjoiY2F0ZWdvcmllcyIsInJhZGl1c0ZpbHRlckFwcGxpZWQiOmZhbHNlfQ%3D%3D",
            "item_name": "[Local Test] Troostwijk Covidien",
            "status": "active",
            "next_fetch_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "user_id": user_id,
            "site_key": "mazree",
            "url": "https://www.mazree.com/smart-auction-detail/098837e3-86d8-4676-abac-0a98693d43c5",
            "item_name": "[Local Test] Mazree Table",
            "status": "active",
            "next_fetch_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    for item in items:
        # Check if URL already exists to avoid duplicates
        existing = supabase.table("auction_items").select("id").eq("url", item["url"]).execute()
        if not existing.data:
            print(f"Adding {item['site_key']}...")
            supabase.table("auction_items").insert(item).execute()
        else:
            print(f"Updating {item['site_key']} to be due now...")
            supabase.table("auction_items").update({
                "next_fetch_at": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "locked_until": None
            }).eq("url", item["url"]).execute()

if __name__ == "__main__":
    seed_test_items()
