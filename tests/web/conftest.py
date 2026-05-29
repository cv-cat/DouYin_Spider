import pytest
from fastapi.testclient import TestClient

from web.app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})


@pytest.fixture
def client(app):
    return TestClient(app)
