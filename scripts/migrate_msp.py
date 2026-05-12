import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_msp")

MSP_SOURCE_URLS = [
    "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2200996",
    "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2132109",
    "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2173567",
]

MSP_DATA = [
    {
        "crop_name": "Paddy(Dhan)(Common)",
        "display_name": "Paddy (Common)",
        "season": "Kharif",
        "marketing_season": "KMS 2025-26",
        "marketing_year": 2025,
        "msp_value": 2369,
    },
    {
        "crop_name": "Jowar (Hybrid)",
        "display_name": "Jowar (Hybrid)",
        "season": "Kharif",
        "marketing_season": "KMS 2025-26",
        "marketing_year": 2025,
        "msp_value": 3699,
    },
    {
        "crop_name": "Bajra",
        "display_name": "Bajra",
        "season": "Kharif",
        "marketing_season": "KMS 2025-26",
        "marketing_year": 2025,
        "msp_value": 2775,
    },
    {
        "crop_name": "Maize",
        "display_name": "Maize",
        "season": "Kharif",
        "marketing_season": "KMS 2025-26",
        "marketing_year": 2025,
        "msp_value": 2400,
    },
    {
        "crop_name": "Arhar",
        "display_name": "Arhar",
        "season": "Kharif",
        "marketing_season": "KMS 2025-26",
        "marketing_year": 2025,
        "msp_value": 8000,
    },
    {
        "crop_name": "Moong",
        "display_name": "Moong",
        "season": "Kharif",
        "marketing_season": "KMS 2025-26",
        "marketing_year": 2025,
        "msp_value": 8768,
    },
    {
        "crop_name": "Soyabean",
        "display_name": "Soyabean",
        "season": "Kharif",
        "marketing_season": "KMS 2025-26",
        "marketing_year": 2025,
        "msp_value": 5328,
    },
    {
        "crop_name": "Wheat",
        "display_name": "Wheat",
        "season": "Rabi",
        "marketing_season": "RMS 2026-27",
        "marketing_year": 2026,
        "msp_value": 2585,
    },
    {
        "crop_name": "Barley",
        "display_name": "Barley",
        "season": "Rabi",
        "marketing_season": "RMS 2026-27",
        "marketing_year": 2026,
        "msp_value": 2150,
    },
    {
        "crop_name": "Gram",
        "display_name": "Gram",
        "season": "Rabi",
        "marketing_season": "RMS 2026-27",
        "marketing_year": 2026,
        "msp_value": 5875,
    },
    {
        "crop_name": "Masur",
        "display_name": "Masur",
        "season": "Rabi",
        "marketing_season": "RMS 2026-27",
        "marketing_year": 2026,
        "msp_value": 7000,
    },
    {
        "crop_name": "Mustard",
        "display_name": "Rapeseed & mustard",
        "season": "Rabi",
        "marketing_season": "RMS 2026-27",
        "marketing_year": 2026,
        "msp_value": 6200,
    },
]


async def upsert_msp_data(db: AsyncIOMotorDatabase) -> int:
    now = datetime.now(timezone.utc)
    collection = db.crop_msp
    writes = 0

    for record in MSP_DATA:
        doc = {
            **record,
            "unit": "INR/quintal",
            "source": "PIB government MSP filing",
            "source_urls": MSP_SOURCE_URLS,
            "updated_at": now,
        }
        result = await collection.update_one(
            {
                "crop_name": record["crop_name"],
                "marketing_season": record["marketing_season"],
            },
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        if result.upserted_id or result.modified_count:
            writes += 1

    await collection.create_index([("crop_name", 1), ("marketing_year", -1)])
    await collection.create_index([("season", 1), ("marketing_year", -1)])
    await collection.create_index(
        [("crop_name", 1), ("marketing_season", 1)],
        unique=True,
        name="crop_msp_unique_crop_season",
    )
    return writes


async def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert FasalX MSP seed data into MongoDB.")
    parser.add_argument(
        "--refresh-latest",
        action="store_true",
        help="Reserved for scheduled runs that refresh from latest government filings before upsert.",
    )
    args = parser.parse_args()

    if args.refresh_latest:
        logger.info("Refreshing crop_msp with the latest curated PIB/CACP filing values in this migration.")

    mongo_url = os.getenv("MONGO_URL", settings.MONGO_URL)
    mongo_db_name = os.getenv("MONGO_DB_NAME", settings.MONGO_DB_NAME)
    logger.info("Connecting to MongoDB database '%s'", mongo_db_name)

    client = AsyncIOMotorClient(mongo_url)
    try:
        await client.admin.command("ping")
        writes = await upsert_msp_data(client[mongo_db_name])
        logger.info("MSP migration complete. Upserted or modified %s records in crop_msp.", writes)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
