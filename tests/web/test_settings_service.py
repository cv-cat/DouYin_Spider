from web.services.settings_service import SettingsService


def test_settings_round_trip(tmp_path):
    service = SettingsService(tmp_path / "web-ui.sqlite3")
    service.save_many({"media_dir": "/tmp/media", "excel_dir": "/tmp/excel"})

    data = service.load()

    assert data["media_dir"] == "/tmp/media"
    assert data["excel_dir"] == "/tmp/excel"
