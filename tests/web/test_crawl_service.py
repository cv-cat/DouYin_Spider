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


def test_user_lookup_action_returns_payload(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def lookup_user(self, user_url):
            return {"user_url": user_url, "nickname": "demo"}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post("/actions/crawl/user", data={"user_url": "https://www.douyin.com/user/demo"})

    assert response.status_code == 200
    assert "https://www.douyin.com/user/demo" in response.text


def test_search_action_returns_payload(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def search_general(self, query, require_num, sort_type, publish_time, filter_duration="", search_range="", content_type=""):
            return {"query": query, "require_num": require_num, "sort_type": sort_type, "publish_time": publish_time}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post(
        "/actions/crawl/search",
        data={"query": "测试", "require_num": "5", "sort_type": "1", "publish_time": "7"},
    )

    assert response.status_code == 200
    assert "测试" in response.text


def test_digg_action_returns_payload(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def digg(self, aweme_id, digg_type="1"):
            return {"aweme_id": aweme_id, "digg_type": digg_type}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post("/actions/crawl/digg", data={"aweme_id": "123", "digg_type": "1"})

    assert response.status_code == 200
    assert "123" in response.text


def test_publish_comment_action_returns_payload(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def publish_comment(self, aweme_id, content, reply_id=""):
            return {"aweme_id": aweme_id, "content": content, "reply_id": reply_id}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post(
        "/actions/crawl/comment",
        data={"aweme_id": "123", "content": "hello", "reply_id": ""},
    )

    assert response.status_code == 200
    assert "hello" in response.text


def test_collect_action_returns_payload(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def collect_aweme(self, aweme_id, action="1"):
            return {"aweme_id": aweme_id, "action": action}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post("/actions/crawl/collect", data={"aweme_id": "123", "action": "1"})

    assert response.status_code == 200
    assert "123" in response.text


def test_works_export_action_returns_task_id(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def queue_works_export(self, works_text, save_choice="all", excel_name=""):
            return "task-works"

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post(
        "/actions/crawl/works-export",
        data={"works_text": "https://www.douyin.com/video/1", "save_choice": "all", "excel_name": "demo"},
    )

    assert response.status_code == 200
    assert "task-works" in response.text


def test_search_export_action_returns_task_id(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def queue_search_export(
            self,
            query,
            require_num,
            save_choice,
            sort_type,
            publish_time,
            filter_duration="",
            search_range="",
            content_type="",
            excel_name="",
        ):
            return "task-search"

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post(
        "/actions/crawl/search-export",
        data={
            "query": "测试",
            "require_num": "5",
            "save_choice": "all",
            "sort_type": "0",
            "publish_time": "0",
            "excel_name": "demo",
        },
    )

    assert response.status_code == 200
    assert "task-search" in response.text
