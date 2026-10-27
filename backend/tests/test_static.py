import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def static_client(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setattr(get_settings(), "static_dir", str(tmp_path))
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


def test_serves_frontend_and_spa_routes(static_client):
    assert static_client.get("/").text == "<html>app</html>"
    assert static_client.get("/logs?date_from=2026-10-01").text == "<html>app</html>"  # client-side route
    assert static_client.get("/assets/app.js").text == "console.log(1)"
    assert static_client.get("/favicon.svg").text == "<svg/>"


def test_api_routes_still_work_and_unknown_api_is_404(static_client):
    assert static_client.get("/api/health").json()["database"] is True
    assert static_client.get("/api/nope").status_code == 404


def test_no_path_traversal(static_client):
    r = static_client.get("/../secret.txt")
    assert "nope" not in r.text
    r = static_client.get("/%2e%2e/secret.txt")
    assert "nope" not in r.text


def test_refresh_cookie_secure_flag_follows_setting(client, make_user, monkeypatch):
    make_user("a@example.com")
    body = {"email": "a@example.com", "password": "correct-horse-battery"}
    assert "Secure" not in client.post("/api/auth/login", json=body).headers["set-cookie"]
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    assert "Secure" in client.post("/api/auth/login", json=body).headers["set-cookie"]
