"""Launcher seguro del piloto local: loopback y un único worker fijos."""

import uvicorn

from backend.app.config import Settings
from backend.app.domain.errors import ConfigurationError


def server_options(settings: Settings | None = None) -> dict[str, object]:
    chosen_settings = settings or Settings()
    if not chosen_settings.local_mode_enabled:
        raise ConfigurationError("LOCAL_MODE_DISABLED")
    return {
        "app": "backend.app.main:app",
        "host": "127.0.0.1",
        "port": 8000,
        "workers": 1,
    }


def main() -> None:
    uvicorn.run(**server_options())


if __name__ == "__main__":
    main()
