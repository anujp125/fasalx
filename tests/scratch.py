import sys
import os

repo_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(repo_root, "..", "backend"))

from fastapi.testclient import TestClient
from app.main import app
from app.db.mongodb import db_instance, get_mongo_db
import app.api.routers.users as users_router
import app.db.mongodb as mongodb_module

print("db_instance ID in test:", id(db_instance))
print("db_instance ID in router:", id(users_router.get_mongo_db.__globals__.get("db_instance", mongodb_module.db_instance)))
print("db_instance ID in mongodb module:", id(mongodb_module.db_instance))

db_instance.db = "MOCKED_DB"
print("get_mongo_db() returns:", get_mongo_db())
print("router get_mongo_db() returns:", users_router.get_mongo_db())

client = TestClient(app)
resp = client.post("/api/v1/users/sync", headers={"Authorization": "Bearer fake"})
print("Response:", resp.status_code, resp.json())
