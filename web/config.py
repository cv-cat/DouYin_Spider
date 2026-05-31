import os
from pathlib import Path


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class WebConfig:
    def __init__(self, overrides=None):
        overrides = overrides or {}
        project_root = Path(__file__).resolve().parents[1]
        datas_root = project_root / "datas"
        self.project_root = project_root
        self.host = str(overrides.get("HOST", os.environ.get("WEB_UI_HOST", "127.0.0.1")))
        self.port = int(overrides.get("PORT", os.environ.get("WEB_UI_PORT", 8000)))
        self.db_path = Path(overrides.get("DB_PATH", project_root / "datas" / "web-ui.sqlite3"))
        self.media_dir = Path(overrides.get("MEDIA_DIR", datas_root / "media_datas"))
        self.excel_dir = Path(overrides.get("EXCEL_DIR", datas_root / "excel_datas"))
        self.static_dir = Path(overrides.get("STATIC_DIR", project_root / "web" / "static"))
        self.templates_dir = Path(overrides.get("TEMPLATES_DIR", project_root / "web" / "templates"))
        self.use_system_proxy = _as_bool(overrides.get("USE_SYSTEM_PROXY"), default=False)
