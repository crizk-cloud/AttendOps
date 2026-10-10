"""TEST DOUBLE ONLY - an in-process fake Dahua device for httpx.MockTransport.

It performs a real Digest challenge/response so the client's auth flow is exercised. Response bodies
for recordFinder follow the format verified on the real devices; magicBox bodies follow Dahua's API
documentation and are NOT yet confirmed on our devices.
"""

import hashlib
import re
from collections.abc import Callable

import httpx

REALM = "Login to FAKE"
NONCE = "fakenonce"


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


class FakeDahua:
    def __init__(self, username: str = "admin", password: str = "secret", *,
                 model: str = "DHI-ASI2212J-PW", firmware: str = "1.000.0000000.1.R,build:2023-03-15",
                 serial: str = "8F0A1B2C3D", supports_user_api: bool = True):
        self.username, self.password = username, password
        self.routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: list[httpx.Request] = []
        self.auth_headers: list[str | None] = []  # snapshot per request (httpx mutates Request objects)
        self.model, self.firmware, self.serial = model, firmware, serial
        self.supports_user_api = supports_user_api
        # Access history held by the fake; recordFinder applies the same 1024 cap as the real devices.
        self.records: list[dict[str, str]] = []
        self.fail_after_queries: int | None = None  # simulate the device dropping off mid-sync
        self.history_queries = 0

    def add_records(self, times: list[int], **fields: str) -> list[dict[str, str]]:
        start = len(self.records) + 1
        new = [{"RecNo": str(start + i), "CreateTime": str(t), "UserID": str(1000 + (start + i) % 7),
                "CardName": fields.get("CardName", f"Person {(start + i) % 7}"), "CardNo": f"C{(start + i) % 7:04d}",
                "Type": fields.get("Type", "Entry"), "Method": "1", "Status": fields.get("Status", "1"),
                "Door": "0", "ReaderID": "1", "ErrorCode": "0", "Password": fields.get("Password", "")}
               for i, t in enumerate(times)]
        self.records.extend(new)
        return new

    def _find_records(self, request: httpx.Request) -> httpx.Response:
        self.history_queries += 1
        if self.fail_after_queries is not None and self.history_queries > self.fail_after_queries:
            raise httpx.ConnectError("Connection refused", request=request)
        p = request.url.params
        if not (p.get("StartTime", "").isdigit() and p.get("EndTime", "").isdigit()):
            return httpx.Response(400, text="Error\r\nBad Request!\r\n")  # like the real device
        s, e, count = int(p["StartTime"]), int(p["EndTime"]), min(int(p.get("count", 1024)), 1024)
        hits = sorted((r for r in self.records if s <= int(r["CreateTime"]) <= e), key=lambda r: int(r["CreateTime"]))
        hits = hits[:count]
        lines = [f"found={len(hits)}"] + [f"records[{i}].{k}={v}" for i, r in enumerate(hits) for k, v in r.items()]
        return httpx.Response(200, text="\r\n".join(lines) + "\r\n")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _authorized(self, request: httpx.Request) -> bool:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Digest "):
            return False
        f = dict(re.findall(r'(\w+)="?([^",]+)"?', header))
        ha1 = _md5(f"{self.username}:{REALM}:{self.password}")
        ha2 = _md5(f"{request.method}:{f.get('uri')}")
        expected = _md5(f"{ha1}:{NONCE}:{f.get('nc')}:{f.get('cnonce')}:auth:{ha2}")
        return f.get("username") == self.username and f.get("response") == expected

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.auth_headers.append(request.headers.get("Authorization"))
        if not self._authorized(request):
            return httpx.Response(401, headers={
                "WWW-Authenticate": f'Digest realm="{REALM}", qop="auth", nonce="{NONCE}", opaque="o"'})
        cgi = request.url.path.rsplit("/", 1)[-1]
        action = request.url.params.get("action", "")
        if (cgi, action) in self.routes:
            return self.routes[(cgi, action)](request)
        return self.default(cgi, action, request)

    def default(self, cgi: str, action: str, request: httpx.Request) -> httpx.Response:
        ok = lambda body: httpx.Response(200, text=body)  # noqa: E731
        bad = httpx.Response(400, text="Error\r\nBad Request!\r\n")
        if cgi == "magicBox.cgi":
            return {
                "getDeviceType": ok(f"type={self.model}\r\n"),
                "getSoftwareVersion": ok(f"version={self.firmware}\r\n"),
                "getSerialNo": ok(f"sn={self.serial}\r\n"),
            }.get(action, bad)
        if cgi == "recordFinder.cgi" and action == "find" and \
                request.url.params.get("name") == "AccessControlCardRec":
            return self._find_records(request)
        if cgi in ("AccessUser.cgi", "AccessCard.cgi") and self.supports_user_api:
            if action == "startFind":
                return ok("Token=12\r\nTotal=3\r\n")
            if action == "stopFind":
                return ok("OK\r\n")
        return bad
