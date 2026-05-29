import pytest

from web.app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
