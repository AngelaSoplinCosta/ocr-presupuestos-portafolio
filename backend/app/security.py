import base64
import hashlib
import hmac
import secrets

from .config import (
    SCRYPT_DIGEST_BYTES,
    SCRYPT_MAX_N,
    SCRYPT_MAX_P,
    SCRYPT_MAX_R,
    SCRYPT_MIN_N,
    SCRYPT_MIN_P,
    SCRYPT_MIN_R,
    SCRYPT_SALT_BYTES,
    Settings,
)
from .domain.errors import AuthenticationFailed
from .domain.models import TenantPrincipal

SCRYPT_N = SCRYPT_MIN_N
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = SCRYPT_DIGEST_BYTES


def hash_api_token(token: str, *, salt: bytes | None = None) -> str:
    """Crea una representación scrypt apta para configuración; no registra el token."""
    chosen_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        token.encode("utf-8"),
        salt=chosen_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N,
        SCRYPT_R,
        SCRYPT_P,
        base64.urlsafe_b64encode(chosen_salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def _verify_token(token: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, expected_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        parsed_n = int(n)
        parsed_r = int(r)
        parsed_p = int(p)
        salt = base64.b64decode(salt_text, altchars=b"-_", validate=True)
        expected = base64.b64decode(expected_text, altchars=b"-_", validate=True)
        if not (
            SCRYPT_MIN_N <= parsed_n <= SCRYPT_MAX_N
            and parsed_n & (parsed_n - 1) == 0
            and SCRYPT_MIN_R <= parsed_r <= SCRYPT_MAX_R
            and SCRYPT_MIN_P <= parsed_p <= SCRYPT_MAX_P
            and len(salt) == SCRYPT_SALT_BYTES
            and len(expected) == SCRYPT_DIGEST_BYTES
        ):
            return False
        actual = hashlib.scrypt(
            token.encode("utf-8"),
            salt=salt,
            n=parsed_n,
            r=parsed_r,
            p=parsed_p,
            dklen=SCRYPT_DIGEST_BYTES,
        )
    except (UnicodeEncodeError, ValueError, TypeError, OverflowError):
        return False
    return hmac.compare_digest(actual, expected)


def authenticate_token(token: str | None, settings: Settings) -> TenantPrincipal:
    if not token or len(token.encode("utf-8")) > settings.max_token_header_bytes:
        raise AuthenticationFailed("AUTHENTICATION_FAILED")
    matched_tenants: set[str] = set()
    for configured in settings.token_hashes():
        if _verify_token(token, configured.token_hash):
            matched_tenants.add(configured.tenant_id)
    if len(matched_tenants) != 1:
        raise AuthenticationFailed("AUTHENTICATION_FAILED")
    return TenantPrincipal(tenant_id=matched_tenants.pop())


def protect_drive_file_id(tenant_id: str, drive_file_id: str, secret: bytes) -> str:
    if not drive_file_id or len(drive_file_id) > 1024:
        raise ValueError("identificador de Drive inválido")
    payload = tenant_id.encode("utf-8") + b"\0" + drive_file_id.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()
