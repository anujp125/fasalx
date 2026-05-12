import asyncio
import csv
import logging
import os
import sys

# Add the app directory to the python path so we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), "app"))

from app.core.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mapping from CSV crop names to the Engine's Canonical Names
CROP_ALIAS_MAP = {
    "Paddy (Common)": "Paddy(Dhan)(Common)",
    "Paddy (Grade 'A')": "Paddy(Dhan)(Common)", # Group together
    "Rapeseed & mustard": "Mustard",
    "Masur": "Lentil (Masur)",
    "Cotton (Medium Staple)": "Cotton",
    "Cotton (Long Staple)": "Cotton",
    "Arhar": "Tur", # Usually Tur/Arhar
    "Moong": "Moong",
    "Urad": "Urad",
    "Groundnut": "Groundnut",
    "Soyabean": "Soyabean",
    "Wheat": "Wheat",
    "Barley": "Barley",
    "Gram": "Gram",
    "Maize": "Maize",
}

async def main():
    logger.info(f"Connecting to MongoDB at {settings.MONGO_URL}...")
    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.MONGO_DB_NAME]
    
    collection = db.msp_history
    
    # Drop existing data if re-running
    await collection.drop()
    logger.info("Dropped existing msp_history collection.")
    
    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "msp_21-25data.csv")
    
    if not os.path.exists(csv_path):
        logger.error(f"CSV file not found at {csv_path}")
        return
        
    records_inserted = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_crop_name = row["crop_name"].strip()
            # Map to canonical name if it exists, otherwise use raw name
            canonical_name = CROP_ALIAS_MAP.get(raw_crop_name, raw_crop_name)
            
            # If multiple varieties of Cotton/Paddy exist for the same year, we'll keep the highest value or just upsert.
            # Upsert logic based on crop_name + year to avoid duplicates if mapping merges them.
            
            doc = {
                "crop_name": canonical_name,
                "season": row["season"].strip(),
                "year": int(row["year"].strip()),
                "msp_value": float(row["msp_value"].strip())
            }
            
            # Since we mapped "Paddy (Common)" and "Paddy (Grade 'A')" to the same, 
            # let's just keep the max MSP if there's a collision.
            existing = await collection.find_one({"crop_name": canonical_name, "year": doc["year"]})
            if existing:
                if doc["msp_value"] > existing["msp_value"]:
                    await collection.update_one(
                        {"_id": existing["_id"]},
                        {"$set": {"msp_value": doc["msp_value"]}}
                    )
            else:
                await collection.insert_one(doc)
                records_inserted += 1
                
    # Create indexes for fast querying
    await collection.create_index([("crop_name", 1), ("year", -1)])
    
    logger.info(f"Successfully ingested MSP data. Created {records_inserted} unique crop-year records.")
    
if __name__ == "__main__":
    asyncio.run(main())
