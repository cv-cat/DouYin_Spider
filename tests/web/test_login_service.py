from fastapi.testclient import TestClient

from web.app import create_app


def test_manual_cookie_save_updates_session(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.post(
        "/actions/login/cookies",
        data={"scope": "douyin", "cookie_str": "msToken=test; sessionid=abc"},
    )

    assert response.status_code == 200
    assert "manual cookie saved" in response.text
