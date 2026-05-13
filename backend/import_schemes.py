import json
import asyncio
import os
import sys

# Add the current directory to sys.path to allow importing from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from datetime import datetime, timezone
import uuid

async def import_schemes():
    with open('../agriculture_schemes.json', 'r', encoding='utf-8') as f:
        schemes_data = json.load(f)

    import certifi
    client = AsyncIOMotorClient(settings.MONGO_URL, tlsCAFile=certifi.where())
    db = client[settings.MONGO_DB_NAME]
    
    collection = db.schemes
    
    count = 0
    for scheme in schemes_data:
        # map fields
        scheme_id = str(uuid.uuid4())
        
        category = scheme.get('type', 'general').lower().replace(' ', '_')
        # Ensure category is somewhat reasonable
        
        is_active = scheme.get('status', 'Active').lower() == 'active'
        
        scheme_type = scheme.get('scheme_type', 'central').lower()
        if 'central' in scheme_type:
            scheme_type = 'central'
        elif 'state' in scheme_type:
            scheme_type = 'state'
            
        doc = {
            "_id": scheme_id,
            "title_en": scheme.get('scheme_name', ''),
            "title_hi": "",  # no hindi in json
            "description_en": scheme.get('description', '') + "\n\nBenefits: " + scheme.get('benefits', ''),
            "description_hi": "",
            "eligibility_en": scheme.get('eligibility_criteria', '') + "\n\nDocuments Required: " + ", ".join(scheme.get('documents_required', [])),
            "eligibility_hi": "",
            "how_to_apply_en": "",
            "how_to_apply_hi": "",
            "apply_link": scheme.get('direct_link', ''),
            "category": category,
            "scheme_type": scheme_type,
            "state_name": "", # Would need mapping if there are state schemes
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Upsert by title_en to avoid duplicates
        await collection.update_one(
            {"title_en": doc["title_en"]},
            {"$set": doc},
            upsert=True
        )
        count += 1
        
    print(f"Successfully imported {count} schemes into the database.")
    client.close()

if __name__ == "__main__":
    asyncio.run(import_schemes())
