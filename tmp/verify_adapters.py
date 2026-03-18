import sys
import os

# Add bot directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bot")))

try:
    from adapters.adapter_factory import detect_site_key, get_adapter
    
    test_urls = {
        "https://www.allsurplus.com/en/asset/41621/7484": "allsurplus",
        "https://www.equipnet.com/item-955747": "equipnet",
        "https://www.mazree.com/item/123": "mazree",
        "https://www.google.com": "mock"
    }
    
    print("--- Testing Site Key Detection ---")
    for url, expected in test_urls.items():
        detected = detect_site_key(url)
        print(f"URL: {url} -> Detected: {detected} (Expected: {expected})")
        
    print("\n--- Testing Adapter Retrieval ---")
    for site_key in ["allsurplus", "equipnet", "mazree"]:
        adapter_class = get_adapter(site_key)
        if adapter_class:
            print(f"Site Key: {site_key} -> Adapter Class: {adapter_class.__name__}")
        else:
            print(f"Site Key: {site_key} -> NOT FOUND")

except Exception as e:
    print(f"Error during verification: {e}")
    import traceback
    traceback.print_exc()
