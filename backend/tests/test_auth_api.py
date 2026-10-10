from app.api.auth import REFRESH_COOKIE
from app.models import Role


def test_health(client):
    r = client.get("/api/health")
    assert r.json() == {"status": "ok", "database": True, "timezone": "Asia/Beirut"}


def test_login_success_and_me(client, make_user, login):
    make_user("Op@Example.com", Role.operator)
    headers = login("op@example.com")  # email is case-insensitive
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == "op@example.com" and me["role"] == "operator"
    assert "password_hash" not in me


def test_login_sets_httponly_refresh_cookie(client, make_user):
    make_user("a@example.com")
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"})
    cookie = r.headers["set-cookie"]
    assert REFRESH_COOKIE in cookie and "HttpOnly" in cookie and "Path=/api/auth" in cookie
    assert "refresh" not in r.json()


def test_login_failures_are_indistinguishable(client, make_user):
    make_user("a@example.com")
    wrong_pw = client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope"})
    no_user = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_disabled_account_cannot_log_in(client, make_user):
    make_user("off@example.com", active=False)
    r = client.post("/api/auth/login", json={"email": "off@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client, make_user):
    make_user("a@example.com")
    client.post("/api/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"})
    refresh = client.cookies.get(REFRESH_COOKIE)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_refresh_rotates_and_detects_reuse(client, make_user, login):
    make_user("a@example.com")
    login("a@example.com")
    first = client.cookies.get(REFRESH_COOKIE)

    r = client.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    second = client.cookies.get(REFRESH_COOKIE)
    assert second != first

    # Replaying the old token revokes the whole family, including the newest token.
    client.cookies.set(REFRESH_COOKIE, first, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401
    client.cookies.set(REFRESH_COOKIE, second, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token(client, make_user, login):
    make_user("a@example.com")
    login("a@example.com")
    token = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set(REFRESH_COOKIE, token, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_change_password(client, make_user, login):
    make_user("a@example.com")
    h = login("a@example.com")
    bad = client.post("/api/auth/change-password", headers=h,
                      json={"current_password": "wrong", "new_password": "new-password-123"})
    assert bad.status_code == 400
    short = client.post("/api/auth/change-password", headers=h,
                        json={"current_password": "correct-horse-battery", "new_password": "short"})
    assert short.status_code == 422
    ok = client.post("/api/auth/change-password", headers=h,
                     json={"current_password": "correct-horse-battery", "new_password": "new-password-123"})
    assert ok.status_code == 204
    login("a@example.com", "new-password-123")
