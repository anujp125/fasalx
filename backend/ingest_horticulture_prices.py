"""
Ingestion script for horticulture crop average price data.
Loads avg_prices_horticulture_crops_apr21-mar24_statewise_national.csv into MongoDB
collection `horticulture_price_history`.

This data powers the dynamic horticulture profitability scoring in the
recommendation engine (core.py -> _historical_horticulture_trend).

Usage:
    cd backend
    ..\venv\Scripts\python ingest_horticulture_prices.py
"""
import asyncio
import csv
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from app.core.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Month abbreviation -> month number for proper date sorting
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "avg_prices_horticulture_crops_apr21-mar24_statewise_national.csv",
)


async def main():
    if not os.path.exists(CSV_PATH):
        logger.error(f"CSV not found at {CSV_PATH}")
        return

    logger.info(f"Connecting to MongoDB at {settings.MONGO_URL}...")
    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.MONGO_DB_NAME]
    collection = db.horticulture_price_history

    # Drop existing data for clean re-ingestion
    await collection.drop()
    logger.info("Dropped existing horticulture_price_history collection.")

    records = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            crop_name = row["crop_name"].strip()
            state = row["state"].strip()
            year = int(row["year"].strip())
            month_abbr = row["month"].strip()
            price = float(row["price"].strip())
            month_num = MONTH_MAP.get(month_abbr, 1)

            # Build a proper datetime for reliable sorting
            record_date = datetime(year, month_num, 1)

            doc = {
                "crop_name": crop_name,
                "state": state,
                "year": year,
                "month": month_abbr,
                "month_num": month_num,
                "price": price,
                "date": record_date,
                "created_at": datetime.utcnow(),
            }
            records.append(doc)

    if records:
        result = await collection.insert_many(records)
        logger.info(f"Inserted {len(result.inserted_ids)} records.")

    # Create indexes for fast querying
    await collection.create_index([("crop_name", 1), ("date", -1)])
    await collection.create_index([("crop_name", 1), ("state", 1), ("date", -1)])
    await collection.create_index([("crop_name", 1), ("year", -1)])

    # Print summary
    pipeline = [
        {"$group": {
            "_id": {"crop": "$crop_name", "state": "$state"},
            "count": {"$sum": 1},
            "min_price": {"$min": "$price"},
            "max_price": {"$max": "$price"},
            "avg_price": {"$avg": "$price"},
        }},
        {"$sort": {"_id.crop": 1, "_id.state": 1}},
    ]
    print("\n--- Ingestion Summary ---")
    async for group in collection.aggregate(pipeline):
        crop = group["_id"]["crop"]
        state = group["_id"]["state"]
        count = group["count"]
        print(
            f"  {crop:12s} | {state:25s} | {count:3d} records | "
            f"Rs {group['min_price']:,.0f} - {group['max_price']:,.0f} "
            f"(avg Rs {group['avg_price']:,.0f})"
        )

    # Quick trend test: print computed trends for All-India Average
    print("\n--- All-India Price Trends ---")
    for crop in ("Onion", "Potato", "Tomato"):
        cursor = (
            collection.find({"crop_name": crop, "state": "All-India Average"})
            .sort("date", -1)
            .limit(24)
        )
        recs = [doc async for doc in cursor]
        if len(recs) >= 2:
            latest = recs[0]["price"]
            oldest = recs[-1]["price"]
            trend = round(((latest - oldest) / oldest) * 100, 2)
            print(
                f"  {crop:12s}: Latest Rs {latest:,.0f} -> Oldest Rs {oldest:,.0f} "
                f"| Trend: {trend:+.2f}%"
            )
        else:
            print(f"  {crop:12s}: Not enough records")

    client.close()
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
