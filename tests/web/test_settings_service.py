from fastapi.testclient import TestClient

from web.app import create_app
from web.services.settings_service import SettingsService


def test_settings_round_trip(tmp_path):
    service = SettingsService(tmp_path / "web-ui.sqlite3")
    service.save_many({"media_dir": "/tmp/media", "excel_dir": "/tmp/excel"})

    data = service.load()

    assert data["media_dir"] == "/tmp/media"
    assert data["excel_dir"] == "/tmp/excel"


def test_settings_action_persists_values(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.post(
        "/actions/settings",
        data={"media_dir": "/tmp/media", "excel_dir": "/tmp/excel", "port": "8010"},
    )

    assert response.status_code == 200
    assert "settings saved" in response.text
    data = app.state.settings_service.load()
    assert data["media_dir"] == "/tmp/media"
    assert data["excel_dir"] == "/tmp/excel"
    assert data["port"] == 8010
