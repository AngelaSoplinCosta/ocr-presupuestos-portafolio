from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.infrastructure.database import build_engine
from backend.app.main import create_app


def test_live_and_ready_are_separate(client):
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    assert live.status_code == 200
    assert live.json() == {"status": "live", "error_code": None}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "error_code": None}


def test_ready_rejects_missing_schema(settings, adapter):
    missing_schema_settings = settings.model_copy(
        update={"database_url": "sqlite:///:memory:"}
    )
    app = create_app(
        settings=missing_schema_settings,
        engine=build_engine(missing_schema_settings.database_url),
        adapter=adapter,
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["error_code"] == "DATABASE_SCHEMA_NOT_READY"


def test_documentation_can_be_disabled(settings, adapter):
    disabled = Settings(**{**settings.model_dump(), "docs_enabled": False})
    engine = build_engine(disabled.database_url)
    app = create_app(settings=disabled, engine=engine, adapter=adapter)
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_invalid_mandatory_configuration_is_reported_at_startup(settings, adapter):
    invalid = settings.model_copy(update={"id_hmac_secret": "short"})
    app = create_app(
        settings=invalid,
        engine=build_engine(invalid.database_url),
        adapter=adapter,
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["error_code"] == "ID_HMAC_SECRET_INVALID"
