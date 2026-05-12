"""
Backend package conftest.
Uses pytest_configure to set sys.path as early as possible (before
any test module import), ensuring 'app' resolves to backend/app/.
"""
import sys
import os

def pytest_configure(config):
    repo_root    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    backend_root  = os.path.join(repo_root, "backend")
    timeline_root = os.path.join(repo_root, "timeline_service")

    # Remove timeline_service to avoid 'app' collision
    if timeline_root in sys.path:
        sys.path.remove(timeline_root)

    # Put backend at front
    if backend_root in sys.path:
        sys.path.remove(backend_root)
    sys.path.insert(0, backend_root)

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
    
    try:
        import app.db.redis
        monkeypatch.setattr("app.db.redis.init_redis", AsyncMock())
        monkeypatch.setattr("app.db.redis.close_redis", AsyncMock())
    except ImportError:
        pass
