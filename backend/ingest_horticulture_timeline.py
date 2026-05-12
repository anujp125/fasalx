"""
Ingestion script for horticulture crop timeline (sowing/transplanting/harvesting)
data by state and season.

Loads horticulture_crops_timeline_statewise.csv into MongoDB collection
`horticulture_crop_timeline`.

This data powers state-aware action plans in the recommendation engine.

Usage:
    cd backend
    ..\\venv\\Scripts\\python ingest_horticulture_timeline.py
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

CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "horticulture_crops_timeline_statewise.csv",
)


async def main():
    if not os.path.exists(CSV_PATH):
        logger.error(f"CSV not found at {CSV_PATH}")
        return

    logger.info(f"Connecting to MongoDB at {settings.MONGO_URL}...")
    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.MONGO_DB_NAME]
    collection = db.horticulture_crop_timeline

    # Drop existing data for clean re-ingestion
    await collection.drop()
    logger.info("Dropped existing horticulture_crop_timeline collection.")

    records = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = {
                "crop_name": row["crop_name"].strip(),
                "season": row["season"].strip(),
                "state": row["state"].strip(),
                "sowing": (row.get("sowing") or "").strip() or None,
                "transplanting": (row.get("transplanting") or "").strip() or None,
                "harvesting": (row.get("harvesting") or "").strip() or None,
                "created_at": datetime.now(),
            }
            records.append(doc)

    if records:
        result = await collection.insert_many(records)
        logger.info(f"Inserted {len(result.inserted_ids)} records.")

    # Create indexes for fast querying
    await collection.create_index([("crop_name", 1), ("state", 1), ("season", 1)])
    await collection.create_index([("crop_name", 1), ("season", 1)])

    # Summary
    pipeline = [
        {"$group": {
            "_id": "$crop_name",
            "states": {"$addToSet": "$state"},
            "seasons": {"$addToSet": "$season"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    print("\n--- Ingestion Summary ---")
    async for group in collection.aggregate(pipeline):
        crop = group["_id"]
        states = sorted(group["states"])
        seasons = sorted(group["seasons"])
        print(f"  {crop:12s} | {group['count']:2d} records | Seasons: {', '.join(seasons)}")
        print(f"  {'':12s} | States: {', '.join(states)}")

    client.close()
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
