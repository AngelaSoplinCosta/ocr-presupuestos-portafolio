import json
import base64
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .domain.errors import ConfigurationError

SCRYPT_MIN_N = 2**14
SCRYPT_MAX_N = 2**18
SCRYPT_MIN_R = 8
SCRYPT_MAX_R = 16
SCRYPT_MIN_P = 1
SCRYPT_MAX_P = 4
SCRYPT_SALT_BYTES = 16
SCRYPT_DIGEST_BYTES = 32
TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class TokenHashConfig:
    tenant_id: str
    token_hash: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OCR_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite:////tmp/piloto-ocr-jobs.sqlite3"
    job_storage_root: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "piloto-ocr-jobs"
    )
    max_upload_bytes: int = 50 * 1024 * 1024
    max_request_bytes: int = 52 * 1024 * 1024
    upload_chunk_bytes: int = 1024 * 1024
    result_retention_hours: int = 24
    max_active_requests: int = 1
    max_token_credentials: int = 32
    max_token_header_bytes: int = 512
    local_mode_enabled: bool = False
    docs_enabled: bool = True
    id_hmac_secret: str = ""
    api_token_hashes_json: str = "[]"

    @field_validator(
        "max_upload_bytes",
        "max_request_bytes",
        "upload_chunk_bytes",
        "result_retention_hours",
        "max_active_requests",
        "max_token_credentials",
        "max_token_header_bytes",
    )
    @classmethod
    def positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("debe ser mayor que cero")
        return value

    def token_hashes(self) -> tuple[TokenHashConfig, ...]:
        try:
            raw = json.loads(self.api_token_hashes_json)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("API_TOKEN_HASHES_INVALID") from exc
        if not isinstance(raw, list):
            raise ConfigurationError("API_TOKEN_HASHES_INVALID")
        if not raw or len(raw) > self.max_token_credentials:
            raise ConfigurationError("API_TOKEN_HASHES_INVALID")
        parsed: list[TokenHashConfig] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ConfigurationError("API_TOKEN_HASHES_INVALID")
            tenant_id = item.get("tenant_id")
            token_hash = item.get("token_hash")
            if not isinstance(tenant_id, str) or not TENANT_PATTERN.fullmatch(tenant_id):
                raise ConfigurationError("API_TOKEN_HASHES_INVALID")
            if not isinstance(token_hash, str) or not self._valid_scrypt_hash(token_hash):
                raise ConfigurationError("API_TOKEN_HASHES_INVALID")
            parsed.append(TokenHashConfig(tenant_id=tenant_id, token_hash=token_hash))
        return tuple(parsed)

    def require_hmac_secret(self) -> bytes:
        secret = self.id_hmac_secret.encode("utf-8")
        if len(secret) < 32:
            raise ConfigurationError("ID_HMAC_SECRET_INVALID")
        return secret

    @staticmethod
    def _valid_scrypt_hash(encoded: str) -> bool:
        try:
            algorithm, n_text, r_text, p_text, salt_text, digest_text = encoded.split(
                "$", 5
            )
            n = int(n_text)
            r = int(r_text)
            p = int(p_text)
            salt = base64.b64decode(salt_text, altchars=b"-_", validate=True)
            digest = base64.b64decode(digest_text, altchars=b"-_", validate=True)
        except (UnicodeEncodeError, ValueError, TypeError):
            return False
        return (
            algorithm == "scrypt"
            and SCRYPT_MIN_N <= n <= SCRYPT_MAX_N
            and n & (n - 1) == 0
            and SCRYPT_MIN_R <= r <= SCRYPT_MAX_R
            and SCRYPT_MIN_P <= p <= SCRYPT_MAX_P
            and len(salt) == SCRYPT_SALT_BYTES
            and len(digest) == SCRYPT_DIGEST_BYTES
        )

    def validate_runtime(self) -> None:
        if not self.database_url.strip():
            raise ConfigurationError("DATABASE_URL_INVALID")
        self.require_hmac_secret()
        self.token_hashes()
        if self.max_request_bytes <= self.max_upload_bytes:
            raise ConfigurationError("REQUEST_LIMIT_INVALID")
        if self.upload_chunk_bytes > self.max_upload_bytes:
            raise ConfigurationError("UPLOAD_LIMIT_INVALID")
        if self.max_active_requests != 1:
            raise ConfigurationError("ACTIVE_REQUEST_LIMIT_INVALID")
        if self.max_token_header_bytes > 4096:
            raise ConfigurationError("TOKEN_HEADER_LIMIT_INVALID")
        if self.job_storage_root.resolve() == Path("/"):
            raise ConfigurationError("JOB_STORAGE_ROOT_INVALID")
