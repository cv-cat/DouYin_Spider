from pathlib import Path


class WebConfig:
    def __init__(self, overrides=None):
        overrides = overrides or {}
        project_root = Path(__file__).resolve().parents[1]
        datas_root = project_root / "datas"
        self.host = "127.0.0.1"
        self.port = int(overrides.get("PORT", 8000))
        self.db_path = Path(overrides.get("DB_PATH", project_root / "datas" / "web-ui.sqlite3"))
        self.media_dir = Path(overrides.get("MEDIA_DIR", datas_root / "media_datas"))
        self.excel_dir = Path(overrides.get("EXCEL_DIR", datas_root / "excel_datas"))
