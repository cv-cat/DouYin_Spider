import json

from fastapi.testclient import TestClient

from web.app import create_app
from web.services.crawl_service import CrawlService


def test_api_tools_page_loads(client):
    response = client.get("/api-tools")

    assert response.status_code == 200
    assert "接口工具" in response.text


def test_toolbox_crawl_action_dispatches_operation(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    calls = []

    class DummyCrawlService:
        def invoke(self, operation, payload):
            calls.append((operation, payload))
            return {"operation": operation, "payload": payload}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post(
        "/actions/toolbox/crawl",
        data={"operation": "get_my_uid"},
    )

    assert response.status_code == 200
    assert calls == [("get_my_uid", {})]
    assert "get_my_uid" in response.text


def test_toolbox_live_action_dispatches_operation(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    calls = []

    class DummyLiveService:
        def invoke(self, operation, payload):
            calls.append((operation, payload))
            return {"operation": operation, "payload": payload}

    app.state.live_service = DummyLiveService()
    client = TestClient(app)

    response = client.post(
        "/actions/toolbox/live",
        data={"operation": "get_rank_list", "room_id": "1"},
    )

    assert response.status_code == 200
    assert calls == [("get_rank_list", {"room_id": "1"})]
    assert "get_rank_list" in response.text


def test_crawl_service_invoke_maps_remaining_operations(tmp_path):
    calls = []

    class DummyAPI:
        def __getattr__(self, name):
            def method(auth, *args):
                calls.append((name, auth, args))
                return {"method": name, "args": list(args)}

            return method

    class DummySessionService:
        def load_auth(self, scope):
            return f"auth:{scope}"

    class DummyTaskManager:
        def submit(self, task_type, summary, runner):
            return runner()

    class DummyConfig:
        media_dir = "/tmp/media"
        excel_dir = "/tmp/excel"

    service = CrawlService(DummyConfig(), DummySessionService(), DummyTaskManager())
    service.api = DummyAPI()

    cases = [
        ("get_user_work_info", {"user_url": "u", "max_cursor": "9"}, "get_user_work_info", ("u", "9")),
        ("get_work_out_comment", {"work_url": "w", "cursor": "2"}, "get_work_out_comment", ("w", "2")),
        ("get_work_all_out_comment", {"work_url": "w"}, "get_work_all_out_comment", ("w",)),
        (
            "get_work_inner_comment",
            {"comment_json": json.dumps({"cid": "1"}), "cursor": "3", "count": "5"},
            "get_work_inner_comment",
            ({"cid": "1"}, "3", "5"),
        ),
        (
            "get_work_all_inner_comment",
            {"comment_json": json.dumps({"cid": "1"})},
            "get_work_all_inner_comment",
            ({"cid": "1"},),
        ),
        ("get_work_all_comment", {"work_url": "w"}, "get_work_all_comment", ("w",)),
        (
            "search_general_work",
            {
                "query": "q",
                "sort_type": "1",
                "publish_time": "7",
                "offset": "8",
                "search_range": "3",
                "filter_duration": "1-5",
                "content_type": "2",
            },
            "search_general_work",
            ("q", "1", "7", "8", "3", "1-5", "2"),
        ),
        ("search_some_user", {"query": "q", "num": "4"}, "search_some_user", ("q", 4)),
        (
            "search_user",
            {"query": "q", "offset": "1", "num": "25", "douyin_user_fans": "1000", "douyin_user_type": "verified"},
            "search_user",
            ("q", "1", "25", "1000", "verified"),
        ),
        ("search_live", {"query": "q", "offset": "2", "num": "6"}, "search_live", ("q", "2", "6")),
        ("search_some_live", {"query": "q", "num": "6"}, "search_some_live", ("q", 6)),
        ("get_user_favorite", {"sec_id": "sec", "max_cursor": "1", "num": "18"}, "get_user_favorite", ("sec", "1", "18")),
        ("get_my_uid", {}, "get_my_uid", ()),
        ("get_my_sec_uid", {}, "get_my_sec_uid", ()),
        (
            "move_collect_aweme",
            {"aweme_id": "a", "collect_name": "c", "collect_id": "cid"},
            "move_collect_aweme",
            ("a", "c", "cid"),
        ),
        (
            "remove_collect_aweme",
            {"aweme_id": "a", "collect_name": "c", "collect_id": "cid"},
            "remove_collect_aweme",
            ("a", "c", "cid"),
        ),
        ("get_collect_list", {}, "get_collect_list", ()),
        (
            "get_user_follower_list",
            {"user_id": "u", "sec_id": "sec", "max_time": "0", "count": "20"},
            "get_user_follower_list",
            ("u", "sec", "0", "20"),
        ),
        (
            "get_some_user_follower_list",
            {"user_id": "u", "sec_id": "sec", "num": "8"},
            "get_some_user_follower_list",
            ("u", "sec", 8),
        ),
        (
            "get_user_following_list",
            {"user_id": "u", "sec_id": "sec", "max_time": "0", "count": "20"},
            "get_user_following_list",
            ("u", "sec", "0", "20"),
        ),
        (
            "get_some_user_following_list",
            {"user_id": "u", "sec_id": "sec", "num": "8"},
            "get_some_user_following_list",
            ("u", "sec", 8),
        ),
        (
            "get_notice_list",
            {"min_time": "0", "max_time": "0", "count": "10", "notice_group": "700"},
            "get_notice_list",
            ("0", "0", "10", "700"),
        ),
        (
            "get_some_notice_list",
            {"num": "5", "notice_group": "700"},
            "get_some_notice_list",
            (5, "700"),
        ),
        ("get_feed", {"count": "20", "refresh_index": "2"}, "get_feed", ("20", "2")),
        ("get_device_id", {}, "get_device_id", ()),
        (
            "search_some_video_work",
            {"query": "q", "num": "6", "sort_type": "1", "publish_time": "7", "filter_duration": "1-5"},
            "search_some_video_work",
            ("q", 6, "1", "7", "1-5"),
        ),
        (
            "search_video_work",
            {"query": "q", "offset": "1", "count": "16", "sort_type": "2", "publish_time": "180", "filter_duration": "5-10000"},
            "search_video_work",
            ("q", "1", "16", "2", "180", "5-10000"),
        ),
    ]

    for operation, payload, expected_method, expected_args in cases:
        calls.clear()
        result = service.invoke(operation, payload)
        assert result["method"] == expected_method
        assert calls == [(expected_method, "auth:douyin", expected_args)]


def test_live_service_invoke_maps_remaining_operations(tmp_path):
    calls = []

    class DummyAPI:
        def __getattr__(self, name):
            def method(auth, *args):
                calls.append((name, auth, args))
                return {"method": name, "args": list(args)}

            return method

    class DummySessionService:
        def load_auth(self, scope):
            return f"auth:{scope}"

    class DummyTaskManager:
        runtimes = {}

        def submit(self, task_type, summary, runner):
            return runner()

    class DummyBroker:
        def publish(self, channel, payload):
            return None

    service = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")}).state.live_service
    service.sessions = DummySessionService()
    service.task_manager = DummyTaskManager()
    service.broker = DummyBroker()

    from web.services.live_service import DouyinAPI
    original = {
        "get_live_production": DouyinAPI.get_live_production,
        "get_all_live_production": DouyinAPI.get_all_live_production,
        "get_live_production_detail": DouyinAPI.get_live_production_detail,
        "get_rank_list": DouyinAPI.get_rank_list,
        "get_webcast_detail": DouyinAPI.get_webcast_detail,
    }

    try:
        DouyinAPI.get_live_production = DummyAPI().__getattr__("get_live_production")
        DouyinAPI.get_all_live_production = DummyAPI().__getattr__("get_all_live_production")
        DouyinAPI.get_live_production_detail = DummyAPI().__getattr__("get_live_production_detail")
        DouyinAPI.get_rank_list = DummyAPI().__getattr__("get_rank_list")
        DouyinAPI.get_webcast_detail = DummyAPI().__getattr__("get_webcast_detail")

        cases = [
            (
                "get_live_production",
                {"url": "u", "room_id": "1", "author_id": "2", "offset": "3"},
                "get_live_production",
                ("u", "1", "2", "3"),
            ),
            (
                "get_all_live_production",
                {"url": "u"},
                "get_all_live_production",
                ("u",),
            ),
            (
                "get_live_production_detail",
                {"url": "u", "ec_promotion_id": "11", "sec_author_id": "22", "live_room_id": "33"},
                "get_live_production_detail",
                ("u", "11", "22", "33"),
            ),
            (
                "get_rank_list",
                {"room_id": "1", "anchor_id": "2", "sec_anchor_id": "3"},
                "get_rank_list",
                ("1", "2", "3"),
            ),
            (
                "get_webcast_detail",
                {"user_id": "1", "room_id": "2", "url": "u"},
                "get_webcast_detail",
                ("1", "2", "u"),
            ),
        ]

        for operation, payload, expected_method, expected_args in cases:
            calls.clear()
            result = service.invoke(operation, payload)
            assert result["method"] == expected_method
            assert calls == [(expected_method, "auth:live", expected_args)]
    finally:
        for name, method in original.items():
            setattr(DouyinAPI, name, method)
