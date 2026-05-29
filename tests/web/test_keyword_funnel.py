from fastapi.testclient import TestClient

from web.db import connect_db
from web.services.keyword_funnel_service import KeywordFunnelService


class DummyTaskManager:
    def __init__(self):
        self.counter = 0

    def submit(self, task_type, summary, runner):
        self.counter += 1
        runner()
        return f"task-{self.counter}"


class DummyCrawlService:
    def __init__(self):
        self.comment_calls = []

    def search_general(
        self,
        query,
        require_num,
        sort_type,
        publish_time,
        filter_duration="",
        search_range="",
        content_type="",
    ):
        return [
            {
                "aweme_info": {
                    "aweme_id": "aweme-1",
                    "share_url": "https://www.douyin.com/video/aweme-1",
                    "desc": "first",
                    "author": {
                        "uid": "1001",
                        "sec_uid": "sec-1001",
                        "nickname": "Alice",
                        "signature": "author-1",
                        "avatar_thumb": {"url_list": ["https://img.example.com/1.jpg"]},
                    },
                }
            },
            {
                "aweme_info": {
                    "aweme_id": "aweme-2",
                    "share_url": "https://www.douyin.com/video/aweme-2",
                    "desc": "second",
                    "author": {
                        "uid": "1003",
                        "sec_uid": "sec-1003",
                        "nickname": "Carol",
                        "signature": "author-2",
                        "avatar_thumb": {"url_list": ["https://img.example.com/3.jpg"]},
                    },
                }
            },
        ]

    def invoke(self, operation, payload):
        assert operation == "get_work_all_out_comment"
        self.comment_calls.append(payload["work_url"])
        return [
            {
                "cid": "comment-1",
                "aweme_id": "aweme-1",
                "text": "need this",
                "user": {
                    "uid": "1002",
                    "sec_uid": "sec-1002",
                    "nickname": "Bob",
                    "signature": "comment-user",
                    "avatar_thumb": {"url_list": ["https://img.example.com/2.jpg"]},
                },
            },
            {
                "cid": "comment-2",
                "aweme_id": "aweme-1",
                "text": "repeat user",
                "user": {
                    "uid": "1001",
                    "sec_uid": "sec-1001",
                    "nickname": "Alice",
                    "signature": "author-1",
                    "avatar_thumb": {"url_list": ["https://img.example.com/1.jpg"]},
                },
            },
        ]


class DummyIMService:
    def __init__(self):
        self.created = []
        self.sent = []

    def create_conversation(self, to_user_id):
        self.created.append(to_user_id)
        return {
            "conversation_id": f"conv-{to_user_id}",
            "conversation_short_id": f"short-{to_user_id}",
            "ticket": f"ticket-{to_user_id}",
        }

    def send_message(self, conversation_id, conversation_short_id, ticket, content):
        self.sent.append((conversation_id, conversation_short_id, ticket, content))
        return {"detail": {"status": "ok"}}


def test_collect_task_persists_unique_author_and_comment_leads(tmp_path):
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyCrawlService(),
        DummyIMService(),
    )

    queued = service.queue_collect("装机", require_num="5", include_comments=True, comment_limit="10")

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        run_row = conn.execute(
            "select keyword, status, lead_count, processed_count, total_count, high_intent_count from keyword_runs where run_id = ?",
            (queued["run_id"],),
        ).fetchone()
        lead_rows = conn.execute(
            "select user_id, nickname, source_type, score, grade, matched_signals, risk_flags, message_status, comment_text "
            "from keyword_leads where run_id = ? order by user_id",
            (queued["run_id"],),
        ).fetchall()

    assert queued["task_id"] == "task-1"
    assert run_row["keyword"] == "装机"
    assert run_row["status"] == "success"
    assert run_row["lead_count"] == 3
    assert run_row["processed_count"] == 2
    assert run_row["total_count"] == 2
    assert run_row["high_intent_count"] == 0
    assert [row["user_id"] for row in lead_rows] == ["1001", "1002", "1003"]
    assert [row["source_type"] for row in lead_rows] == ["search", "comment", "search"]
    assert [row["grade"] for row in lead_rows] == ["C", "C", "C"]
    assert [row["message_status"] for row in lead_rows] == ["pending", "pending", "pending"]
    assert [row["score"] for row in lead_rows] == [20, 30, 20]
    assert lead_rows[0]["matched_signals"] == "[]"
    assert lead_rows[1]["risk_flags"] == "[]"
    assert lead_rows[0]["comment_text"] == ""
    assert lead_rows[1]["comment_text"] == "need this"


def test_bulk_message_task_sends_pending_leads_for_run(tmp_path):
    crawl_service = DummyCrawlService()
    im_service = DummyIMService()
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        crawl_service,
        im_service,
    )
    queued = service.queue_collect("装机", require_num="5", include_comments=False, comment_limit="0")

    result = service.queue_bulk_message(queued["run_id"], "你好，我这边有方案", limit="1")

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        lead_rows = conn.execute(
            "select user_id, message_status, message_error from keyword_leads where run_id = ? order by id",
            (queued["run_id"],),
        ).fetchall()

    assert result["task_id"] == "task-2"
    assert im_service.created == ["1001"]
    assert im_service.sent == [("conv-1001", "short-1001", "ticket-1001", "你好，我这边有方案")]
    assert [row["message_status"] for row in lead_rows] == ["sent", "pending"]
    assert all(row["message_error"] == "" for row in lead_rows)


def test_keyword_collect_action_returns_run_and_task_ids(tmp_path):
    from web.app import create_app

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyKeywordFunnelService:
        def queue_collect(
            self,
            keyword,
            require_num,
            include_comments=False,
            comment_limit="20",
            source_mode="comments_first",
            precision_mode="precision",
            risk_mode="safe",
            outreach_mode="manual",
        ):
            return {"run_id": "run-1", "task_id": "task-1", "keyword": keyword}

        def list_runs(self):
            return []

        def list_leads(self, run_id=""):
            return []

    app.state.keyword_funnel_service = DummyKeywordFunnelService()
    client = TestClient(app)

    response = client.post(
        "/actions/keyword-funnel/collect",
        data={"keyword": "装机", "require_num": "5", "include_comments": "on", "comment_limit": "8"},
    )

    assert response.status_code == 200
    assert "run-1" in response.text
    assert "task-1" in response.text


def test_keyword_funnel_page_contains_auto_refresh_regions(tmp_path):
    from web.app import create_app

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.get("/keyword-funnel")

    assert response.status_code == 200
    assert 'hx-get="/keyword-funnel?partial=runs"' in response.text
    assert 'hx-trigger="load, every 2s"' in response.text
    assert 'hx-get="/keyword-funnel?partial=leads"' in response.text
    assert "评论内容" in response.text
    assert 'name="source_mode"' in response.text
    assert 'name="precision_mode"' in response.text
    assert 'name="risk_mode"' in response.text
    assert 'name="outreach_mode"' in response.text
    assert "评论区优先" in response.text
    assert "人工审核" in response.text


def test_keyword_bulk_message_action_returns_task_id(tmp_path):
    from web.app import create_app

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyKeywordFunnelService:
        def queue_bulk_message(self, run_id, content, limit=""):
            return {"run_id": run_id, "task_id": "task-9", "content": content}

        def list_runs(self):
            return []

        def list_leads(self, run_id=""):
            return []

    app.state.keyword_funnel_service = DummyKeywordFunnelService()
    client = TestClient(app)

    response = client.post(
        "/actions/keyword-funnel/message",
        data={"run_id": "run-1", "content": "你好", "limit": "10"},
    )

    assert response.status_code == 200
    assert "task-9" in response.text


def test_keyword_collect_action_passes_strategy_modes(tmp_path):
    from web.app import create_app

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyKeywordFunnelService:
        def __init__(self):
            self.called = None

        def queue_collect(
            self,
            keyword,
            require_num,
            include_comments=False,
            comment_limit="20",
            source_mode="comments_first",
            precision_mode="precision",
            risk_mode="safe",
            outreach_mode="manual",
        ):
            self.called = {
                "keyword": keyword,
                "require_num": require_num,
                "include_comments": include_comments,
                "comment_limit": comment_limit,
                "source_mode": source_mode,
                "precision_mode": precision_mode,
                "risk_mode": risk_mode,
                "outreach_mode": outreach_mode,
            }
            return {"run_id": "run-1", "task_id": "task-1", "keyword": keyword}

        def list_runs(self):
            return []

        def list_leads(self, run_id=""):
            return []

    dummy = DummyKeywordFunnelService()
    app.state.keyword_funnel_service = dummy
    client = TestClient(app)

    response = client.post(
        "/actions/keyword-funnel/collect",
        data={
            "keyword": "三角洲求带",
            "require_num": "8",
            "include_comments": "on",
            "comment_limit": "6",
            "source_mode": "comments_first",
            "precision_mode": "precision",
            "risk_mode": "safe",
            "outreach_mode": "manual",
        },
    )

    assert response.status_code == 200
    assert dummy.called == {
        "keyword": "三角洲求带",
        "require_num": "8",
        "include_comments": True,
        "comment_limit": "6",
        "source_mode": "comments_first",
        "precision_mode": "precision",
        "risk_mode": "safe",
        "outreach_mode": "manual",
    }
