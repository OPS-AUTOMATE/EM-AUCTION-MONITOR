import asyncio
import logging
import sys
import os

# Add the current directory to path
sys.path.append(os.getcwd())

from adapters.directbids import DirectBidsAdapter
from adapters.gcsurplus import GCSurplusAdapter
from adapters.troostwijk import TroostwijkAdapter
from adapters.mazree import MazreeAdapter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VerifyNewAdapters")

async def test_adapters():
    logger.info("================================================================")
    logger.info("🧪 VERIFYING SELECTORS (DIRECTBIDS, GCSURPLUS, TROOSTWIJK, MAZREE)")
    logger.info("================================================================")

    # 1. DirectBids
    url_directbids = "https://www.directbids.com/laboratory-auctions/lab-instrumentation-lot-abi-3100-genetic-analyzer-co2-incubator-centrifuge-ovens-freezers-3-pallets-jos5x7sz"
    logger.info(f"🔍 Testing DirectBids Adapter...")
    directbids = DirectBidsAdapter()
    result = await directbids.fetch(url_directbids)
    if result:
        logger.info(f"   ✅ DirectBids Success:")
        logger.info(f"      Item: {result.get('item_name')}")
        logger.info(f"      Bid: {result.get('current_bid')}")
        logger.info(f"      Location: {result.get('location')}")
        logger.info(f"      Time: {result.get('time_left')}")
    else:
        logger.error(f"   ❌ DirectBids Failed")

    logger.info("-" * 60)

    # 2. GCSurplus
    url_gcsurplus = "https://gcsurplus.ca/mn-eng.cfm?snc=wfsav&sc=enc-bid&scn=575760&lcn=735514&lct=L&srchtype=&lci=&str=1&lotnf=1&frmsr=1&sf=ferm-clos&saleType="
    logger.info(f"🔍 Testing GCSurplus Adapter...")
    gcsurplus = GCSurplusAdapter()
    result = await gcsurplus.fetch(url_gcsurplus)
    if result:
        logger.info(f"   ✅ GCSurplus Success:")
        logger.info(f"      Item: {result.get('item_name')}")
        logger.info(f"      Bid: {result.get('current_bid')}")
        logger.info(f"      Location: {result.get('location')}")
        logger.info(f"      Time: {result.get('time_left')}")
    else:
        logger.error(f"   ❌ GCSurplus Failed")

    logger.info("-" * 60)

    # 3. Troostwijk
    url_troostwijk = "https://www.troostwijkauctions.com/en/l/2013-covidien-forcetriad-electrosurgical-unit-A1-41113-1025?source=eyJ0eXBlIjoiY2F0ZWdvcmllcyIsInJhZGl1c0ZpbHRlckFwcGxpZWQiOmZhbHNlfQ%3D%3D"
    logger.info(f"🔍 Testing Troostwijk Adapter...")
    troostwijk = TroostwijkAdapter()
    result = await troostwijk.fetch(url_troostwijk)
    if result:
        logger.info(f"   ✅ Troostwijk Success:")
        logger.info(f"      Item: {result.get('item_name')}")
        logger.info(f"      Bid: {result.get('current_bid')}")
        logger.info(f"      Location: {result.get('location')}")
        logger.info(f"      Time: {result.get('time_left')}")
    else:
        logger.error(f"   ❌ Troostwijk Failed")

    logger.info("-" * 60)

    # 4. Mazree
    url_mazree = "https://www.mazree.com/smart-auction-detail/098837e3-86d8-4676-abac-0a98693d43c5"
    logger.info(f"🔍 Testing Mazree Adapter...")
    mazree = MazreeAdapter()
    result = await mazree.fetch(url_mazree)
    if result:
        logger.info(f"   ✅ Mazree Success:")
        logger.info(f"      Item: {result.get('item_name')}")
        logger.info(f"      Bid: {result.get('current_bid')}")
        logger.info(f"      Location: {result.get('location')}")
        logger.info(f"      Time: {result.get('time_left')}")
    else:
        logger.error(f"   ❌ Mazree Failed")

    logger.info("================================================================")
    logger.info("🏁 VERIFICATION COMPLETE")
    logger.info("================================================================")

if __name__ == "__main__":
    asyncio.run(test_adapters())
