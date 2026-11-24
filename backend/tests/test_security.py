import json

import pytest

from backend.app.domain.errors import AuthenticationFailed, ConfigurationError
from backend.app.security import authenticate_token, hash_api_token, protect_drive_file_id


def test_token_is_stored_as_scrypt_hash(settings, api_token):
    configured = settings.token_hashes()[0]
    assert api_token not in configured.token_hash
    assert configured.token_hash.startswith("scrypt$")
    assert authenticate_token(api_token, settings).tenant_id == "tenant-a"


def test_drive_id_is_hmac_protected_and_tenant_specific():
    raw = "drive-id-no-persistir"
    first = protect_drive_file_id("tenant-a", raw, b"h" * 32)
    second = protect_drive_file_id("tenant-b", raw, b"h" * 32)
    assert raw not in first
    assert len(first) == 64
    assert first != second


def test_hash_api_token_is_salted():
    first = hash_api_token("same-token", salt=b"1" * 16)
    second = hash_api_token("same-token", salt=b"2" * 16)
    assert first != second


@pytest.mark.parametrize(
    "token_hash",
    [
        "scrypt$1048576$8$1$YWFhYWFhYWFhYWFhYWFhYQ==$YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI=",
        "scrypt$16384$8$1$c2hvcnQ=$YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI=",
        "scrypt$16384$8$1$YWFhYWFhYWFhYWFhYWFhYQ==$c2hvcnQ=",
        "scrypt$16384$0$1$YWFhYWFhYWFhYWFhYWFhYQ==$YmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmJiYmI=",
    ],
)
def test_corrupt_or_excessive_scrypt_parameters_are_rejected(settings, token_hash):
    invalid = settings.model_copy(
        update={
            "api_token_hashes_json": json.dumps(
                [{"tenant_id": "tenant-a", "token_hash": token_hash}]
            )
        }
    )
    with pytest.raises(ConfigurationError, match="API_TOKEN_HASHES_INVALID"):
        invalid.token_hashes()


def test_credential_count_is_bounded(settings):
    too_many = settings.model_copy(
        update={"max_token_credentials": 1}
    )
    with pytest.raises(ConfigurationError, match="API_TOKEN_HASHES_INVALID"):
        too_many.token_hashes()


def test_token_header_length_is_bounded(settings):
    with pytest.raises(AuthenticationFailed, match="AUTHENTICATION_FAILED"):
        authenticate_token("x" * (settings.max_token_header_bytes + 1), settings)
