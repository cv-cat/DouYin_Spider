from fastapi.testclient import TestClient

from web.app import create_app


def test_core_pages_load(client):
    for path in ["/", "/login", "/data-crawl", "/keyword-funnel", "/live-monitor", "/private-messages", "/tasks", "/settings"]:
        response = client.get(path)
        assert response.status_code == 200
    assert "DouYin_Spider Web UI" in client.get("/").text
    assert 'id="app-toast-stack"' in client.get("/").text


def test_create_app_is_independent_from_cwd(monkeypatch, tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    monkeypatch.chdir(outside_dir)

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "DouYin_Spider Web UI" in response.text
