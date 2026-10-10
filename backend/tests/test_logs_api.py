from datetime import UTC, datetime

import pytest

from app.models import AccessLog, Device, Role
from app.security.crypto import encrypt_secret


def ts(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.fixture
def seeded(db):
    d1 = Device(name="Main gate", ip="10.2.0.1", username="admin", encrypted_password=encrypt_secret("x"))
    d2 = Device(name="Staff door", ip="10.2.0.2", username="admin", encrypted_password=encrypt_secret("x"))
    db.add_all([d1, d2])
    db.flush()
    rows = [
        # 2026-10-05 21:30 UTC = 2026-10-06 00:30 in Beirut (UTC+3): belongs to Oct 6 locally
        (d1, 1, ts(2026, 10, 5, 21, 30), "John Smith", "C001", "1001", "Entry", 1),
        (d1, 2, ts(2026, 10, 5, 20, 59), "John Smith", "C001", "1001", "Exit", 1),   # Oct 5, 23:59 Beirut
        (d1, 3, ts(2026, 10, 6, 8, 0), "Jane Doe", "C002", "1002", "Entry", 0),       # denied
        (d2, 1, ts(2026, 10, 6, 9, 0), "Ali 100%_Real", "C003", "1003", "Entry", 1),
        (d2, 2, ts(2026, 10, 7, 9, 0), "Jane Doe", "C002", "1002", "Exit", 1),
    ]
    for dev, rec, t, name, card, uid, typ, st in rows:
        db.add(AccessLog(device_id=dev.id, rec_no=rec, event_time=t, card_name=name, card_no=card,
                         device_user_id=uid, type=typ, status=st, method=1,
                         raw_payload={"RecNo": str(rec), "CardName": name, "Password": "[redacted]"}))
    db.commit()
    return d1, d2


@pytest.fixture
def viewer(make_user, login):
    make_user("v@example.com", Role.viewer)
    return login("v@example.com")


def ids(resp) -> list[tuple[str, int]]:
    return [(i["device_name"], i["rec_no"]) for i in resp.json()["items"]]


def test_requires_login(client):
    assert client.get("/api/logs").status_code == 401


def test_default_sort_newest_first(client, seeded, viewer):
    r = client.get("/api/logs", headers=viewer)
    assert r.json()["total"] == 5
    assert ids(r)[0] == ("Staff door", 2)


def test_date_filter_uses_beirut_days(client, seeded, viewer):
    r = client.get("/api/logs", headers=viewer, params={"date_from": "2026-10-06", "date_to": "2026-10-06"})
    assert sorted(ids(r)) == [("Main gate", 1), ("Main gate", 3), ("Staff door", 1)]
    r = client.get("/api/logs", headers=viewer, params={"date_to": "2026-10-05"})
    assert ids(r) == [("Main gate", 2)]


def test_search_by_name_card_and_user_id(client, seeded, viewer):
    assert len(ids(client.get("/api/logs", headers=viewer, params={"q": "jane"}))) == 2
    assert len(ids(client.get("/api/logs", headers=viewer, params={"q": "C001"}))) == 2
    assert len(ids(client.get("/api/logs", headers=viewer, params={"q": "1003"}))) == 1
    # LIKE wildcards in the search term are matched literally
    assert ids(client.get("/api/logs", headers=viewer, params={"q": "100%_"})) == [("Staff door", 1)]
    assert ids(client.get("/api/logs", headers=viewer, params={"q": "%"})) == [("Staff door", 1)]


def test_filters_device_type_result(client, seeded, viewer):
    d1, d2 = seeded
    assert client.get("/api/logs", headers=viewer, params={"device_id": d2.id}).json()["total"] == 2
    assert client.get("/api/logs", headers=viewer, params=[("device_id", d1.id), ("device_id", d2.id)]).json()[
        "total"] == 5
    assert client.get("/api/logs", headers=viewer, params={"type": "Exit"}).json()["total"] == 2
    denied = client.get("/api/logs", headers=viewer, params={"result": "denied"}).json()
    assert denied["total"] == 1 and denied["items"][0]["granted"] is False
    assert client.get("/api/logs", headers=viewer, params={"result": "granted"}).json()["total"] == 4
    assert client.get("/api/logs/types", headers=viewer).json() == ["Entry", "Exit"]


def test_pagination(client, seeded, viewer):
    p1 = client.get("/api/logs", headers=viewer, params={"page_size": 2, "page": 1, "sort": "asc"}).json()
    p3 = client.get("/api/logs", headers=viewer, params={"page_size": 2, "page": 3, "sort": "asc"}).json()
    assert p1["total"] == 5 and len(p1["items"]) == 2 and len(p3["items"]) == 1
    assert (p1["items"][0]["device_name"], p1["items"][0]["rec_no"]) == ("Main gate", 2)
    assert client.get("/api/logs", headers=viewer, params={"page_size": 1000}).status_code == 422


def test_detail_includes_raw_payload(client, seeded, viewer):
    first = client.get("/api/logs", headers=viewer).json()["items"][0]
    detail = client.get(f"/api/logs/{first['id']}", headers=viewer).json()
    assert detail["raw_payload"]["Password"] == "[redacted]"
    assert client.get("/api/logs/999999", headers=viewer).status_code == 404
