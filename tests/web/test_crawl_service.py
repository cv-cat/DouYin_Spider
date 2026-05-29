from fastapi.testclient import TestClient

from web.app import create_app


def test_work_lookup_action_returns_payload(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def lookup_work(self, work_url):
            return {"work_url": work_url, "desc": "demo"}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post("/actions/crawl/work", data={"work_url": "https://www.douyin.com/video/123"})

    assert response.status_code == 200
    assert "https://www.douyin.com/video/123" in response.text
