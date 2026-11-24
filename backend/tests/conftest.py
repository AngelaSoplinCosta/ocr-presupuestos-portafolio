import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.domain.models import EngineOutcome
from backend.app.infrastructure.database import Base, build_engine
from backend.app.main import create_app
from backend.app.security import hash_api_token


class SyntheticSuccessAdapter:
    def __init__(self, review: bool = False):
        self.review = review
        self.calls = 0

    def process(self, *, result_path, **_kwargs):
        self.calls += 1
        result_path.write_bytes(b"SYNTHETIC_XLSX_TEST_ONLY")
        return EngineOutcome(requires_review=self.review)


@pytest.fixture
def api_token() -> str:
    return "token-sintetico-pruebas"


@pytest.fixture
def second_api_token() -> str:
    return "token-otro-tenant"


@pytest.fixture
def settings(tmp_path: Path, api_token: str, second_api_token: str) -> Settings:
    token_hashes = [
        {"tenant_id": "tenant-a", "token_hash": hash_api_token(api_token, salt=b"a" * 16)},
        {
            "tenant_id": "tenant-b",
            "token_hash": hash_api_token(second_api_token, salt=b"b" * 16),
        },
    ]
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.sqlite3'}",
        job_storage_root=tmp_path / "jobs",
        max_upload_bytes=50 * 1024 * 1024,
        upload_chunk_bytes=64,
        result_retention_hours=24,
        id_hmac_secret="h" * 32,
        api_token_hashes_json=json.dumps(token_hashes),
    )


@pytest.fixture
def adapter() -> SyntheticSuccessAdapter:
    return SyntheticSuccessAdapter()


@pytest.fixture
def app(settings: Settings, adapter: SyntheticSuccessAdapter):
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return create_app(settings=settings, engine=engine, adapter=adapter)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as value:
        yield value


@pytest.fixture
def auth_headers(api_token: str) -> dict[str, str]:
    return {"X-API-Key": api_token, "X-Drive-File-Id": "drive-file-sintetico"}


@pytest.fixture
def synthetic_pdf() -> bytes:
    # Sólo satisface la validación de borde; nunca se entrega al motor.
    return b"%PDF-1.4\nSYNTHETIC_TEST_ONLY\n%%EOF\n"
