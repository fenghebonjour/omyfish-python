"""API integration fixtures: app + isolated per-test SQLite database.

engine.py binds DATABASE_URL at import time and hardcodes the SQLite path to
data/observations.db, so tests rebind the module-level engine/Session to a
temp-file database instead of touching the real one.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


NOT_A_FISH = {
    "predictions": [],
    "uncertain": True,
    "is_fish": False,
    "message": "That doesn't look like a fish — try a clear photo of a fish.",
}


class StubAIService:
    """Canned predictions — keeps API tests independent of model checkpoints."""

    mode = "stub"

    def __init__(self, predictions=None, response=None):
        self.response = response
        self.predictions = predictions if predictions is not None else [{
            "species": "walleye",
            "confidence": 0.91,
            "metadata": {"scientific_name": "Sander vitreus"},
        }]

    def predict(self, image, top_k=3):
        if self.response is not None:
            return self.response
        return {
            "predictions": self.predictions[:top_k],
            "uncertain": False,
            "is_fish": True,
            "message": None,
        }


@pytest.fixture
def client(tmp_path, monkeypatch):
    import apps.omyfish_api.db.engine as eng
    from apps.omyfish_api.dependencies import get_ai_service
    from apps.omyfish_api.main import app

    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(eng, "engine", test_engine)
    monkeypatch.setattr(eng, "Session", sessionmaker(bind=test_engine))
    monkeypatch.setattr(eng, "_db_initialized", False)
    eng.ensure_db()

    app.dependency_overrides[get_ai_service] = lambda: StubAIService()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def not_a_fish_client(client):
    """Same app, but the AI stub rejects every upload as not-a-fish."""
    from apps.omyfish_api.dependencies import get_ai_service
    from apps.omyfish_api.main import app

    app.dependency_overrides[get_ai_service] = lambda: StubAIService(response=NOT_A_FISH)
    return client


@pytest.fixture
def auth_headers(client):
    """Register + login a user; returns (headers, user_id)."""
    client.post("/auth/register", json={"email": "angler@example.com", "password": "pw12345"})
    token = client.post(
        "/auth/login", json={"email": "angler@example.com", "password": "pw12345"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    return headers, user_id
