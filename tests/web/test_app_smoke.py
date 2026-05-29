from fastapi.testclient import TestClient

from web.app import create_app


def test_overview_page_loads(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "DouYin_Spider Web UI" in response.text
