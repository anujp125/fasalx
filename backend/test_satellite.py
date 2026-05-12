"""
Test script for Sentinel Hub satellite integration.
Tests: token fetch, NDVI, and soil moisture (NDWI) for real Indian farm coordinates.
Run from: backend/
  ..\\venv\\Scripts\\python test_satellite.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

async def main():
    from app.engine.ingestors.satellite import _get_sentinel_token, get_field_health

    print("\n" + "="*60)
    print("  FasalX -- Sentinel Hub Integration Test")
    print("="*60 + "\n")

    # Step 1: Token
    print("[1/3] Requesting OAuth token from Sentinel Hub...")
    token = await _get_sentinel_token()
    if not token:
        print("  [FAIL]  Could not obtain token (check .env credentials)")
        return
    print(f"  [OK]  Token obtained  ({token[:20]}...)\n")

    # Step 2: Real farm coordinates
    test_coords = [
        ("Sehore, MP  (Wheat belt)", 23.20, 77.10),
        ("Jaisalmer, RJ  (Arid zone)", 26.92, 70.92),
        ("Purnia, Bihar (Alluvial)", 25.78, 87.47),
    ]

    for label, lat, lon in test_coords:
        print(f"[2/3] Fetching field health for: {label} ({lat}, {lon})")
        try:
            result = await get_field_health(lat=lat, lon=lon)
            print(f"  [OK]  NDVI          : {result['ndvi']}")
            print(f"  [OK]  Soil Moisture : {result['soil_moisture']}")
            print(f"  [OK]  Source        : {result['source']}")
        except Exception as e:
            print(f"  [FAIL]  {e}")
        print()

    print("[3/3] Test complete.")

if __name__ == "__main__":
    asyncio.run(main())
