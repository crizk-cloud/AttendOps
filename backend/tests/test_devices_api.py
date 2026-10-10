import logging
import time

import httpx
import pytest

from app.models import Device, Role
from app.security.crypto import decrypt_secret
from app.services import devices as svc
from tests.fake_dahua import FakeDahua

PW = "Dev1ce-Secret!"
ONLINE, WRONG_PW, OFFLINE = "10.9.0.1", "10.9.0.2", "10.9.0.3"


@pytest.fixture(autouse=True)
def fake_network(monkeypatch):
    fakes = {ONLINE: FakeDahua(password=PW), WRONG_PW: FakeDahua(password="something-else")}

    def unreachable(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    def factory(ip, port):
        fake = fakes.get(ip)
        return fake.transport() if fake else httpx.MockTransport(unreachable)

    monkeypatch.setattr(svc, "transport_factory", factory)
    return fakes


@pytest.fixture
def admin(make_user, login):
    make_user("admin@example.com", Role.admin)
    return login("admin@example.com")


def add(client, headers, ip=ONLINE, **kw):
    body = {"name": f"Door {ip}", "ip": ip, "username": "admin", "password": PW} | kw
    return client.post("/api/devices", headers=headers, json=body)


def wait_for_checks(timeout=5.0):
    deadline = time.monotonic() + timeout
    while svc.checking_ids() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not svc.checking_ids()


def test_register_identifies_device_and_encrypts_password(client, admin, db):
    r = add(client, admin)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "online" and d["model"] == "DHI-ASI2212J-PW"
    assert d["firmware"] == "1.000.0000000.1.R build 2023-03-15"
    assert d["last_seen_at"] is not None
    assert d["capabilities"]["history.read"]["state"] == "verified"
    assert d["capabilities"]["users.write"]["state"] == "unverified"
    assert "password" not in r.text.lower() and PW not in r.text
    stored = db.get(Device, d["id"])
    assert stored.encrypted_password != PW and decrypt_secret(stored.encrypted_password) == PW


def test_unreachable_device_is_saved_as_offline(client, admin):
    d = add(client, admin, ip=OFFLINE).json()
    assert d["status"] == "offline" and d["last_error"] == "Connection timed out"
    assert d["last_seen_at"] is None and d["model"] is None


def test_wrong_credentials_are_reported(client, admin):
    d = add(client, admin, ip=WRONG_PW).json()
    assert d["status"] == "auth_failed"


def test_duplicate_address_rejected(client, admin):
    add(client, admin)
    assert add(client, admin, name="again").status_code == 409


def test_invalid_ip_rejected(client, admin):
    assert add(client, admin, ip="not-an-ip").status_code == 422
    assert add(client, admin, ip="172.22.76.300").status_code == 422


def test_role_permissions(client, admin, make_user, login):
    dev = add(client, admin).json()
    make_user("op@example.com", Role.operator)
    make_user("view@example.com", Role.viewer)
    op, view = login("op@example.com"), login("view@example.com")

    listed = client.get("/api/devices", headers=view).json()
    assert listed[0]["username"] is None  # only admins see the device username
    assert client.get("/api/devices", headers=admin).json()[0]["username"] == "admin"

    assert add(client, view, ip="10.9.0.50").status_code == 403
    assert add(client, op, ip="10.9.0.50").status_code == 403
    assert client.post(f"/api/devices/{dev['id']}/check", headers=view).status_code == 403
    assert client.post(f"/api/devices/{dev['id']}/check", headers=op).status_code == 200
    assert client.post("/api/devices/check-all", headers=op).status_code == 202
    wait_for_checks()
    assert client.patch(f"/api/devices/{dev['id']}", headers=op, json={"name": "x"}).status_code == 403
    assert client.delete(f"/api/devices/{dev['id']}", headers=op).status_code == 403
    assert client.post("/api/devices/test-connection", headers=op,
                       json={"ip": ONLINE, "username": "admin", "password": PW}).status_code == 403


def test_test_connection_without_saving(client, admin, db):
    ok = client.post("/api/devices/test-connection", headers=admin,
                     json={"ip": ONLINE, "username": "admin", "password": PW}).json()
    assert ok["status"] == "online" and ok["model"] == "DHI-ASI2212J-PW"
    bad = client.post("/api/devices/test-connection", headers=admin,
                      json={"ip": ONLINE, "username": "admin", "password": "nope"}).json()
    assert bad["status"] == "auth_failed"
    assert db.query(Device).count() == 0


def test_test_connection_reuses_stored_password(client, admin):
    dev = add(client, admin).json()
    r = client.post("/api/devices/test-connection", headers=admin, json={"device_id": dev["id"]})
    assert r.json()["status"] == "online"


def test_update_keeps_password_unless_given_and_rechecks(client, admin, db):
    dev = add(client, admin, ip=WRONG_PW).json()
    r = client.patch(f"/api/devices/{dev['id']}", headers=admin, json={"name": "Main gate"})
    assert r.json()["name"] == "Main gate" and r.json()["status"] == "auth_failed"
    r = client.patch(f"/api/devices/{dev['id']}", headers=admin, json={"password": "something-else"})
    assert r.json()["status"] == "online"
    db.expire_all()
    assert decrypt_secret(db.get(Device, dev["id"]).encrypted_password) == "something-else"


def test_update_to_existing_address_rejected(client, admin):
    add(client, admin)
    other = add(client, admin, ip=OFFLINE).json()
    assert client.patch(f"/api/devices/{other['id']}", headers=admin, json={"ip": ONLINE}).status_code == 409


def test_bulk_add_with_shared_and_per_device_credentials(client, admin):
    add(client, admin)  # already registered -> skipped
    r = client.post("/api/devices/bulk", headers=admin, json={
        "default_username": "admin", "default_password": PW,
        "devices": [
            {"ip": ONLINE},
            {"ip": OFFLINE, "name": "Back door"},
            {"ip": WRONG_PW, "username": "admin", "password": "something-else"},
            {"ip": OFFLINE},  # duplicate within the batch
        ]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["created"]) == 2
    assert sorted(s["reason"] for s in body["skipped"]) == ["already registered", "already registered"]
    wait_for_checks()
    by_ip = {d["ip"]: d for d in client.get("/api/devices", headers=admin).json()}
    assert by_ip[OFFLINE]["name"] == "Back door" and by_ip[OFFLINE]["status"] == "offline"
    assert by_ip[WRONG_PW]["status"] == "online"  # its own credentials were used


def test_bulk_add_requires_credentials(client, admin):
    r = client.post("/api/devices/bulk", headers=admin, json={"devices": [{"ip": ONLINE}]})
    assert r.json() == {"created": [],
                        "skipped": [{"ip": f"{ONLINE}:80", "reason": "no username/password given"}]}


def test_check_all_isolates_failures(client, admin):
    for ip in (ONLINE, OFFLINE, WRONG_PW):
        add(client, admin, ip=ip)
    assert client.post("/api/devices/check-all", headers=admin).json() == {"queued": 3}
    wait_for_checks()
    statuses = {d["ip"]: d["status"] for d in client.get("/api/devices", headers=admin).json()}
    assert statuses == {ONLINE: "online", OFFLINE: "offline", WRONG_PW: "auth_failed"}


def test_disabled_devices_are_not_checked_by_check_all(client, admin):
    dev = add(client, admin).json()
    client.patch(f"/api/devices/{dev['id']}", headers=admin, json={"enabled": False})
    assert client.post("/api/devices/check-all", headers=admin).json() == {"queued": 0}


def test_delete_device(client, admin):
    dev = add(client, admin).json()
    assert client.delete(f"/api/devices/{dev['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/devices/{dev['id']}", headers=admin).status_code == 404


def test_password_never_logged(client, admin, caplog):
    caplog.set_level(logging.DEBUG)
    dev = add(client, admin).json()
    client.post(f"/api/devices/{dev['id']}/check", headers=admin)
    client.post("/api/devices/test-connection", headers=admin,
                json={"ip": WRONG_PW, "username": "admin", "password": PW})
    assert caplog.records, "expected some log output to inspect"
    assert PW not in caplog.text
