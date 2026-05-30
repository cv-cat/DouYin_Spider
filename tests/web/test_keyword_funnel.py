from fastapi.testclient import TestClient
from requests import exceptions as requests_exceptions

from web.db import connect_db
from web.services.crawl_service import VerificationRequiredError
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
        self.lookup_calls = []

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
                    "desc": "三角洲找队友，来个固定车队",
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
                    "desc": "普通晒图",
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
        assert operation == "get_work_out_comment"
        self.comment_calls.append((payload["work_url"], payload.get("cursor", "0")))
        if payload.get("cursor", "0") != "0":
            return {"comments": [], "cursor": payload.get("cursor", "0"), "has_more": 0}
        return {
            "comments": [
                {
                    "cid": "comment-1",
                    "aweme_id": "aweme-1",
                    "text": "三角洲求带，今晚想上分",
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
            ],
            "cursor": "2",
            "has_more": 1,
        }

    def lookup_user(self, user_url):
        self.lookup_calls.append(user_url)
        sec_uid = user_url.rstrip("/").split("/")[-1].split("?")[0]
        profiles = {
            "sec-1001": {
                "user": {
                    "uid": "1001",
                    "sec_uid": "sec-1001",
                    "nickname": "Alice",
                    "signature": "author-1",
                    "following_count": 11,
                }
            },
            "sec-1002": {
                "user": {
                    "uid": "1002",
                    "sec_uid": "sec-1002",
                    "nickname": "Bob",
                    "signature": "comment-user",
                    "following_count": 22,
                }
            },
            "sec-1003": {
                "user": {
                    "uid": "1003",
                    "sec_uid": "sec-1003",
                    "nickname": "Carol",
                    "signature": "author-2",
                    "following_count": 33,
                }
            },
        }
        return profiles[sec_uid]


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


class VerifyBlockedCrawlService(DummyCrawlService):
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
        raise VerificationRequiredError("搜索关键词“装机” 时命中抖音验证，请先在浏览器完成验证后重试")


class CommentExplodesCrawlService(DummyCrawlService):
    def invoke(self, operation, payload):
        raise RuntimeError("comment fetch exploded")


class CommentSSLErrorCrawlService(DummyCrawlService):
    def invoke(self, operation, payload):
        if payload.get("cursor", "0") == "0":
            raise requests_exceptions.SSLError("EOF occurred in violation of protocol")
        return super().invoke(operation, payload)


def test_collect_task_persists_unique_author_and_comment_leads(tmp_path):
    crawl_service = DummyCrawlService()
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        crawl_service,
        DummyIMService(),
    )

    queued = service.queue_collect("装机", require_num="5", include_comments=True, comment_limit="10")

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        run_row = conn.execute(
            "select keyword, status, lead_count, processed_count, total_count, high_intent_count from keyword_runs where run_id = ?",
            (queued["run_id"],),
        ).fetchone()
        lead_rows = conn.execute(
            "select user_id, nickname, source_type, score, grade, matched_signals, risk_flags, message_status, comment_text, profile_json "
            "from keyword_leads where run_id = ? order by user_id",
            (queued["run_id"],),
        ).fetchall()

    assert queued["task_id"] == "task-1"
    assert run_row["keyword"] == "装机"
    assert run_row["status"] == "success"
    assert run_row["lead_count"] == 2
    assert run_row["processed_count"] == 2
    assert run_row["total_count"] == 2
    assert run_row["high_intent_count"] == 2
    assert [row["user_id"] for row in lead_rows] == ["1001", "1002"]
    assert [row["source_type"] for row in lead_rows] == ["search", "comment"]
    assert [row["grade"] for row in lead_rows] == ["A", "S"]
    assert [row["message_status"] for row in lead_rows] == ["pending", "pending"]
    assert [row["score"] for row in lead_rows] == [70, 90]
    assert "找队友" in lead_rows[0]["matched_signals"]
    assert lead_rows[1]["risk_flags"] == "[]"
    assert lead_rows[0]["comment_text"] == ""
    assert lead_rows[1]["comment_text"] == "三角洲求带，今晚想上分"
    assert '"following_count": 11' in lead_rows[0]["profile_json"]
    assert '"following_count": 22' in lead_rows[1]["profile_json"]
    assert crawl_service.lookup_calls == [
        "https://www.douyin.com/user/sec-1001",
        "https://www.douyin.com/user/sec-1002",
    ]


def test_collect_task_wide_mode_keeps_low_intent_leads(tmp_path):
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        DummyCrawlService(),
        DummyIMService(),
    )

    queued = service.queue_collect(
        "装机",
        require_num="5",
        include_comments=False,
        comment_limit="0",
        precision_mode="wide",
    )

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        run_row = conn.execute(
            "select lead_count, high_intent_count from keyword_runs where run_id = ?",
            (queued["run_id"],),
        ).fetchone()
        lead_rows = conn.execute(
            "select user_id, grade from keyword_leads where run_id = ? order by user_id",
            (queued["run_id"],),
        ).fetchall()

    assert run_row["lead_count"] == 2
    assert run_row["high_intent_count"] == 1
    assert [dict(row) for row in lead_rows] == [
        {"user_id": "1001", "grade": "A"},
        {"user_id": "1003", "grade": "C"},
    ]


def test_collect_task_stops_comment_pagination_at_limit(tmp_path):
    crawl_service = DummyCrawlService()
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        crawl_service,
        DummyIMService(),
    )

    queued = service.queue_collect(
        "装机",
        require_num="5",
        include_comments=True,
        comment_limit="1",
    )

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        run_row = conn.execute(
            "select lead_count from keyword_runs where run_id = ?",
            (queued["run_id"],),
        ).fetchone()

    assert run_row["lead_count"] == 2
    assert crawl_service.comment_calls == [
        ("https://www.douyin.com/video/aweme-1", "0"),
        ("https://www.douyin.com/video/aweme-2", "0"),
    ]


def test_collect_task_skips_comment_ssl_error_and_keeps_run_success(tmp_path):
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        CommentSSLErrorCrawlService(),
        DummyIMService(),
    )

    queued = service.queue_collect("装机", require_num="5", include_comments=True, comment_limit="10")

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        run_row = conn.execute(
            "select status, lead_count, summary from keyword_runs where run_id = ?",
            (queued["run_id"],),
        ).fetchone()
        lead_rows = conn.execute(
            "select user_id from keyword_leads where run_id = ? order by user_id",
            (queued["run_id"],),
        ).fetchall()

    assert run_row["status"] == "success"
    assert run_row["lead_count"] == 1
    assert [row["user_id"] for row in lead_rows] == ["1001"]
    assert "评论抓取失败" in run_row["summary"]


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
    assert [row["message_status"] for row in lead_rows] == ["sent"]
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
    assert "默认关键词标签" in response.text
    assert 'data-keyword-chip="求带"' in response.text
    assert 'data-keyword-input' in response.text


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


def test_collect_task_marks_verification_required_for_frontend(tmp_path):
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        VerifyBlockedCrawlService(),
        DummyIMService(),
    )

    try:
        service.queue_collect("装机", require_num="5", include_comments=False, comment_limit="0")
    except VerificationRequiredError:
        pass

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        run_row = conn.execute(
            "select status, summary from keyword_runs order by created_at desc limit 1"
        ).fetchone()

    assert run_row["status"] == "verification_required"
    assert "请先在浏览器完成验证后重试" in run_row["summary"]


def test_keyword_run_table_surfaces_verification_required_message(tmp_path):
    from web.app import create_app

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        conn.execute(
            "insert into keyword_runs("
            "run_id, task_id, keyword, status, require_num, include_comments, comment_limit, "
            "source_mode, precision_mode, risk_mode, outreach_mode, total_count, processed_count, lead_count, "
            "high_intent_count, contacted_count, replied_count, summary, created_at, updated_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-verify",
                "task-verify",
                "装机",
                "verification_required",
                5,
                0,
                0,
                "comments_first",
                "precision",
                "safe",
                "manual",
                0,
                0,
                0,
                0,
                0,
                0,
                "搜索关键词“装机” 时命中抖音验证，请先在浏览器完成验证后重试",
                "2026-05-30T00:00:00+00:00",
                "2026-05-30T00:00:00+00:00",
            ),
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/keyword-funnel?partial=runs")

    assert response.status_code == 200
    assert "需要人工验证" in response.text
    assert "请先在浏览器完成验证后重试" in response.text


def test_keyword_run_table_surfaces_missing_requirements_and_next_steps(tmp_path):
    from web.app import create_app

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        conn.execute(
            "insert into keyword_runs("
            "run_id, task_id, keyword, status, require_num, include_comments, comment_limit, "
            "source_mode, precision_mode, risk_mode, outreach_mode, total_count, processed_count, lead_count, "
            "high_intent_count, contacted_count, replied_count, summary, created_at, updated_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-missing-cookie",
                "task-cookie",
                "三角洲",
                "failed",
                10,
                1,
                20,
                "comments_first",
                "precision",
                "safe",
                "manual",
                0,
                0,
                0,
                0,
                0,
                0,
                "RuntimeError: Missing douyin cookie",
                "2026-05-30T00:00:00+00:00",
                "2026-05-30T00:00:00+00:00",
            ),
        )
        conn.execute(
            "insert into keyword_runs("
            "run_id, task_id, keyword, status, require_num, include_comments, comment_limit, "
            "source_mode, precision_mode, risk_mode, outreach_mode, total_count, processed_count, lead_count, "
            "high_intent_count, contacted_count, replied_count, summary, created_at, updated_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-ssl",
                "task-ssl",
                "三角洲",
                "failed",
                10,
                1,
                20,
                "comments_first",
                "precision",
                "safe",
                "manual",
                2,
                1,
                1,
                1,
                0,
                0,
                "SSLError: EOF occurred in violation of protocol",
                "2026-05-30T00:00:00+00:00",
                "2026-05-30T00:00:00+00:00",
            ),
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/keyword-funnel?partial=runs")

    assert response.status_code == 200
    assert "缺少 douyin 登录态" in response.text
    assert "先到登录中心保存 douyin Cookie" in response.text
    assert "评论抓取连接异常" in response.text
    assert "可直接重试，或关闭评论抓取后继续" in response.text


def test_collect_persists_found_author_before_comment_failure(tmp_path):
    service = KeywordFunnelService(
        tmp_path / "web-ui.sqlite3",
        DummyTaskManager(),
        CommentExplodesCrawlService(),
        DummyIMService(),
    )

    try:
        service.queue_collect("装机", require_num="5", include_comments=True, comment_limit="10")
    except RuntimeError:
        pass

    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        run_row = conn.execute(
            "select status, lead_count, summary from keyword_runs order by created_at desc limit 1"
        ).fetchone()
        lead_rows = conn.execute(
            "select nickname, source_type from keyword_leads order by id"
        ).fetchall()

    assert run_row["status"] == "failed"
    assert run_row["lead_count"] == 1
    assert [dict(row) for row in lead_rows] == [{"nickname": "Alice", "source_type": "search"}]
