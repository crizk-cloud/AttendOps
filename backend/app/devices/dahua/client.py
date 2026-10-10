"""Low-level HTTP client for one Dahua device (HTTP Digest auth).

Security: the password is held only in this object for the duration of a call; it is never logged
and never placed in URLs or error messages. Proxy environment variables are ignored, because devices
are on the local network.
"""

import threading
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings

_semaphore: threading.BoundedSemaphore | None = None
_semaphore_lock = threading.Lock()


def device_slot() -> threading.BoundedSemaphore:
    """Process-wide limit on simultaneous device requests.

    The terminals accept only a few concurrent HTTP sessions, and dahua_attendance_logger.py polls
    the same devices, so we stay well below that.
    """
    global _semaphore
    with _semaphore_lock:
        if _semaphore is None:
            _semaphore = threading.BoundedSemaphore(get_settings().device_max_concurrency)
        return _semaphore


@dataclass
class DahuaResponse:
    status_code: int
    text: str
    elapsed_ms: int


class DahuaClient:
    def __init__(self, ip: str, port: int, username: str, password: str,
                 transport: httpx.BaseTransport | None = None):
        s = get_settings()
        self.base_url = f"http://{ip}:{port}"
        self._client = httpx.Client(
            base_url=self.base_url,
            auth=httpx.DigestAuth(username, password),
            timeout=httpx.Timeout(s.device_read_timeout, connect=s.device_connect_timeout),
            trust_env=False,
            transport=transport,
            headers={"User-Agent": "AttendOps"},
        )

    def __enter__(self) -> "DahuaClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: dict | None = None) -> DahuaResponse:
        """GET a CGI path. Raises httpx.TransportError for network failures."""
        with device_slot():
            started = time.monotonic()
            r = self._client.get(path, params=params)
            return DahuaResponse(r.status_code, r.text, round((time.monotonic() - started) * 1000))
