from app.models import Role


def test_only_admin_can_manage_accounts(client, make_user, login):
    make_user("admin@example.com", Role.admin)
    make_user("op@example.com", Role.operator)
    make_user("view@example.com", Role.viewer)
    for email in ("op@example.com", "view@example.com"):
        h = login(email)
        assert client.get("/api/app-users", headers=h).status_code == 403
        assert client.post("/api/app-users", headers=h, json={
            "email": "x@example.com", "password": "long-enough-pw"}).status_code == 403
    assert len(client.get("/api/app-users", headers=login("admin@example.com")).json()) == 3


def test_admin_creates_user_who_can_log_in(client, make_user, login):
    make_user("admin@example.com", Role.admin)
    h = login("admin@example.com")
    r = client.post("/api/app-users", headers=h, json={
        "email": "New@Example.com", "password": "long-enough-pw", "role": "operator"})
    assert r.status_code == 201 and r.json()["email"] == "new@example.com"
    assert client.post("/api/app-users", headers=h, json={
        "email": "new@example.com", "password": "long-enough-pw"}).status_code == 409
    login("new@example.com", "long-enough-pw")


def test_cannot_remove_last_admin(client, make_user, login):
    admin = make_user("admin@example.com", Role.admin)
    h = login("admin@example.com")
    assert client.patch(f"/api/app-users/{admin.id}", headers=h, json={"role": "viewer"}).status_code == 409
    assert client.patch(f"/api/app-users/{admin.id}", headers=h, json={"is_active": False}).status_code == 409
    make_user("admin2@example.com", Role.admin)
    assert client.patch(f"/api/app-users/{admin.id}", headers=h, json={"role": "viewer"}).status_code == 200


def test_role_change_applies_to_existing_access_token(client, make_user, login):
    make_user("admin@example.com", Role.admin)
    other = make_user("admin2@example.com", Role.admin)
    h_other = login("admin2@example.com")
    assert client.get("/api/app-users", headers=h_other).status_code == 200
    client.patch(f"/api/app-users/{other.id}", headers=login("admin@example.com"), json={"role": "viewer"})
    assert client.get("/api/app-users", headers=h_other).status_code == 403


def test_disabling_user_ends_their_session(client, make_user, login):
    make_user("admin@example.com", Role.admin)
    victim = make_user("v@example.com")
    h_victim = login("v@example.com")
    client.patch(f"/api/app-users/{victim.id}", headers=login("admin@example.com"), json={"is_active": False})
    assert client.get("/api/auth/me", headers=h_victim).status_code == 401
