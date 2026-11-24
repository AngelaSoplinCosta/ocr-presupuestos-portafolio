import hashlib
import os
import re
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from ...domain.errors import ConfigurationError, InvalidUpload, StorageCleanupFailed
from ...domain.models import StoredUpload

PDF_SIGNATURE_SCAN_BYTES = 1024
SAFE_NAME_PATTERN = re.compile(r"^[^/\\\x00-\x1f\x7f]+$", re.UNICODE)


class LocalJobStorage:
    def __init__(self, root: Path, max_bytes: int, chunk_bytes: int):
        self.root = root.resolve()
        self.max_bytes = max_bytes
        self.chunk_bytes = chunk_bytes

    def validate_configuration(self) -> None:
        if self.root == Path("/") or self.max_bytes <= 0 or self.chunk_bytes <= 0:
            raise ConfigurationError("JOB_STORAGE_CONFIGURATION_INVALID")
        if self.chunk_bytes > self.max_bytes:
            raise ConfigurationError("JOB_STORAGE_CONFIGURATION_INVALID")

    def check_writable(self) -> bool:
        self.validate_configuration()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        probe = self.root / f".readiness-{uuid4()}"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                probe,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.write(descriptor, b"ready")
            return True
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if probe.exists():
                probe.unlink()

    def _job_root(self, job_id: UUID) -> Path:
        candidate = (self.root / str(job_id)).resolve()
        if candidate.parent != self.root:
            raise InvalidUpload("UNSAFE_JOB_PATH")
        return candidate

    @staticmethod
    def _safe_metadata_name(filename: str | None) -> str:
        value = (filename or "").strip()
        if not value or len(value) > 255 or not SAFE_NAME_PATTERN.fullmatch(value):
            raise InvalidUpload("INVALID_FILENAME")
        if Path(value).suffix.casefold() != ".pdf":
            raise InvalidUpload("INVALID_EXTENSION")
        return value

    def store_upload(self, job_id: UUID, upload: UploadFile) -> StoredUpload:
        safe_name = self._safe_metadata_name(upload.filename)
        if upload.content_type != "application/pdf":
            raise InvalidUpload("INVALID_MIME_TYPE")

        root = self._job_root(job_id)
        input_dir = root / "input"
        work_dir = root / "work" / "ocr"
        output_dir = root / "output"
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.root, 0o700)
            for directory in (root, input_dir, work_dir, output_dir):
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(directory, 0o700)

            target = input_dir / "source.pdf"
            digest = hashlib.sha256()
            total = 0
            prefix = bytearray()
            with target.open("xb") as handle:
                os.chmod(target, 0o600)
                while chunk := upload.file.read(self.chunk_bytes):
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise InvalidUpload("FILE_TOO_LARGE")
                    if len(prefix) < PDF_SIGNATURE_SCAN_BYTES:
                        missing = PDF_SIGNATURE_SCAN_BYTES - len(prefix)
                        prefix.extend(chunk[:missing])
                    digest.update(chunk)
                    handle.write(chunk)
            if total == 0 or not bytes(prefix).lstrip().startswith(b"%PDF-"):
                raise InvalidUpload("INVALID_PDF")
            return StoredUpload(
                job_id=job_id,
                content_sha256=digest.hexdigest(),
                safe_original_name=safe_name,
            )
        except Exception:
            try:
                self.remove_job(job_id)
            except Exception as cleanup_error:
                raise StorageCleanupFailed("UPLOAD_CLEANUP_FAILED") from cleanup_error
            raise
        finally:
            upload.file.close()

    def input_path(self, job_id: UUID) -> Path:
        return self._job_root(job_id) / "input" / "source.pdf"

    def work_directory(self, job_id: UUID) -> Path:
        return self._job_root(job_id) / "work" / "ocr"

    def result_path(self, job_id: UUID) -> Path:
        return self._job_root(job_id) / "output" / "result.xlsx"

    def review_path(self, job_id: UUID) -> Path:
        return self._job_root(job_id) / "output" / "review.json"

    def export_path(self, job_id: UUID) -> Path:
        return self._job_root(job_id) / "output" / "export.json"

    def export_result_path(self, job_id: UUID) -> Path:
        return self._job_root(job_id) / "output" / "export.xlsx"

    def _store_atomic(self, target: Path, payload: bytes) -> None:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(target.parent, 0o700)
        temporary = target.parent / f".{target.name}.{uuid4()}.tmp"
        try:
            with temporary.open("xb") as handle:
                os.chmod(temporary, 0o600)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def store_review(self, job_id: UUID, payload: bytes) -> None:
        self._store_atomic(self.review_path(job_id), payload)

    def store_export(self, job_id: UUID, payload: bytes) -> None:
        self._store_atomic(self.export_path(job_id), payload)

    def remove_export_result(self, job_id: UUID) -> None:
        self.export_result_path(job_id).unlink(missing_ok=True)

    def result_storage_key(self, job_id: UUID) -> str:
        return f"{job_id}/output/result.xlsx"

    def replace_job_upload(self, source_job_id: UUID, target_job_id: UUID) -> None:
        source = self._job_root(source_job_id)
        target = self._job_root(target_job_id)
        if not source.is_dir():
            raise FileNotFoundError("PROVISIONAL_UPLOAD_NOT_FOUND")
        if target.exists():
            shutil.rmtree(target)
        source.replace(target)

    def cleanup_transient(self, job_id: UUID) -> None:
        root = self._job_root(job_id)
        work = root / "work"
        if work.exists():
            shutil.rmtree(work)

    def remove_job(self, job_id: UUID) -> None:
        root = self._job_root(job_id)
        if root.exists():
            shutil.rmtree(root)
