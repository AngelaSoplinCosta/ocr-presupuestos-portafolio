import threading
from contextlib import contextmanager
from collections.abc import Iterator


class SingleInstanceProcessingGate:
    """Serializa el motor dentro de un único proceso de API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @contextmanager
    def hold(self) -> Iterator[None]:
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()
