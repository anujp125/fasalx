"""
Timeline service package conftest.
Uses pytest_configure to set sys.path as early as possible, ensuring
'app' resolves to timeline_service/app/, not backend/app/.
"""
import sys
import os

def pytest_configure(config):
    repo_root     = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    timeline_root = os.path.join(repo_root, "timeline_service")
    backend_root  = os.path.join(repo_root, "backend")

    # Remove backend to avoid 'app' collision
    if backend_root in sys.path:
        sys.path.remove(backend_root)

    # Put timeline_service at front
    if timeline_root in sys.path:
        sys.path.remove(timeline_root)
    sys.path.insert(0, timeline_root)

    # Clear any cached 'app' modules to prevent cross-contamination
    for key in list(sys.modules.keys()):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]

import pytest
from unittest.mock import AsyncMock

@pytest.fixture(autouse=True)
def prevent_lifespan_db_init(monkeypatch):
    """Prevent TestClient lifespan from overwriting mock databases."""
    import app.db.mongodb
    monkeypatch.setattr("app.db.mongodb.init_mongo", AsyncMock())
    monkeypatch.setattr("app.db.mongodb.close_mongo", AsyncMock())
