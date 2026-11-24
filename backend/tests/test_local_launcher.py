import pytest

from backend.app.config import Settings
from backend.app.domain.errors import ConfigurationError
from backend.run_local import server_options


def test_local_launcher_requires_explicit_mode():
    with pytest.raises(ConfigurationError, match="LOCAL_MODE_DISABLED"):
        server_options(Settings(local_mode_enabled=False))


def test_local_launcher_fixes_loopback_and_single_worker():
    assert server_options(Settings(local_mode_enabled=True)) == {
        "app": "backend.app.main:app",
        "host": "127.0.0.1",
        "port": 8000,
        "workers": 1,
    }
