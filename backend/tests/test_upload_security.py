import hashlib
import os
from io import BytesIO
from pathlib import Path
from stat import S_IMODE
from uuid import uuid4

import pytest
from fastapi import UploadFile

from backend.app.config import Settings
from backend.app.domain.errors import InvalidUpload
from backend.app.infrastructure.storage.local import LocalJobStorage


@pytest.mark.parametrize(
    ("filename", "content", "mime", "expected"),
    [
        ("presupuesto.txt", b"%PDF-1.4\n", "application/pdf", "INVALID_EXTENSION"),
        ("../../cliente.pdf", b"%PDF-1.4\n", "application/pdf", "INVALID_FILENAME"),
        ("/tmp/cliente.pdf", b"%PDF-1.4\n", "application/pdf", "INVALID_FILENAME"),
        ("cliente.pdf", b"no es pdf", "application/pdf", "INVALID_PDF"),
        ("cliente.pdf", b"%PDF-1.4\n", "application/octet-stream", "INVALID_MIME_TYPE"),
    ],
)
def test_rejects_unsafe_uploads(client, auth_headers, filename, content, mime, expected):
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": (filename, content, mime)},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == expected


def test_rejects_file_over_limit(client, auth_headers):
    content = b"%PDF-1.4\n" + b"x" * (50 * 1024 * 1024)
    response = client.post(
        "/v1/jobs",
        headers=auth_headers,
        files={"file": ("grande.pdf", content, "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["error_code"] == "FILE_TOO_LARGE"


def test_default_upload_limit_is_50_mib_and_local_concurrency_is_one():
    assert Settings.model_fields["max_upload_bytes"].default == 50 * 1024 * 1024
    assert Settings.model_fields["max_active_requests"].default == 1


def test_storage_uses_internal_name_private_permissions_and_input_hash(tmp_path: Path):
    root = tmp_path / "private-jobs"
    storage = LocalJobStorage(root, 50 * 1024 * 1024, 1024)
    job_id = uuid4()
    content = b"%PDF-1.7\nsynthetic boundary test\n%%EOF\n"

    stored = storage.store_upload(
        job_id,
        UploadFile(
            file=BytesIO(content),
            filename="nombre-visible-del-cliente.pdf",
            headers={"content-type": "application/pdf"},
        ),
    )

    assert stored.safe_original_name == "nombre-visible-del-cliente.pdf"
    assert stored.content_sha256 == hashlib.sha256(content).hexdigest()
    assert storage.input_path(job_id).name == "source.pdf"
    assert storage.input_path(job_id).is_file()
    assert S_IMODE(os.stat(root).st_mode) == 0o700
    assert S_IMODE(os.stat(root / str(job_id)).st_mode) == 0o700
    assert S_IMODE(os.stat(root / str(job_id) / "input").st_mode) == 0o700
    assert S_IMODE(os.stat(root / str(job_id) / "work" / "ocr").st_mode) == 0o700
    assert S_IMODE(os.stat(root / str(job_id) / "output").st_mode) == 0o700
    assert S_IMODE(os.stat(storage.input_path(job_id)).st_mode) == 0o600


def test_storage_rejects_job_symlink_outside_private_root(tmp_path: Path):
    root = tmp_path / "private-jobs"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    job_id = uuid4()
    (root / str(job_id)).symlink_to(outside, target_is_directory=True)
    storage = LocalJobStorage(root, 50 * 1024 * 1024, 1024)

    with pytest.raises(InvalidUpload, match="UNSAFE_JOB_PATH"):
        storage.input_path(job_id)
