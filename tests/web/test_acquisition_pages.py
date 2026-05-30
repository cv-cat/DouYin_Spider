from datetime import UTC, datetime

from fastapi.testclient import TestClient

from web.app import create_app
from web.db import connect_db


def test_acquisition_pages_load_and_are_linked(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    for path in [
        "/acquisition-dashboard",
        "/lead-pool",
        "/outreach-center",
        "/conversion-tracking",
        "/rules-center",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert 'class="ops-shell' in response.text

    home = client.get("/")
    assert "获客仪表盘" in home.text
    assert "线索池" in home.text
    assert "触达中心" in home.text
    assert "规则中心" in home.text
    assert 'class="shell-sidebar"' in home.text


def test_lead_pool_filters_grade_and_source(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        conn.execute(
            "insert into keyword_leads("
            "run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, "
            "comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, "
            "raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "三角洲上分",
                "comment",
                "aweme-1",
                "https://www.douyin.com/video/aweme-1",
                "user-1",
                "sec-1",
                "高意向用户",
                "",
                "",
                "三角洲求带上分",
                90,
                "S",
                '["intent:strong"]',
                '["求带"]',
                "priority",
                "not_contacted",
                "new",
                "[]",
                "{}",
                "user-1",
                "pending",
                "",
                "2026-05-30T00:00:00+00:00",
                None,
            ),
        )
        conn.execute(
            "insert into keyword_leads("
            "run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, "
            "comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, "
            "raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "三角洲组队",
                "search",
                "aweme-2",
                "https://www.douyin.com/video/aweme-2",
                "user-2",
                "sec-2",
                "普通用户",
                "",
                "",
                "",
                20,
                "C",
                "[]",
                "[]",
                "new",
                "not_contacted",
                "new",
                "[]",
                "{}",
                "user-2",
                "pending",
                "",
                "2026-05-30T00:00:00+00:00",
                None,
            ),
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/lead-pool?grade=S&source_type=comment")

    assert response.status_code == 200
    assert "高意向用户" in response.text
    assert "普通用户" not in response.text
    assert 'class="lead-card-grid"' in response.text
    assert 'href="https://www.douyin.com/user/sec-1"' in response.text
    assert 'href="https://www.douyin.com/video/aweme-1"' in response.text


def test_lead_pool_filters_by_time_range_and_intent_text(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        conn.execute(
            "insert into keyword_leads("
            "run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, "
            "comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, "
            "raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "三角洲求陪玩",
                "comment",
                "aweme-1",
                "https://www.douyin.com/video/aweme-1",
                "user-1",
                "sec-1",
                "高意向用户",
                "",
                "",
                "今晚求带上分",
                90,
                "S",
                '["source:comment","intent:strong"]',
                '["求带","上分"]',
                "priority",
                "not_contacted",
                "new",
                "[]",
                "{}",
                "user-1",
                "pending",
                "",
                "2026-05-30T10:00:00+00:00",
                None,
            ),
        )
        conn.execute(
            "insert into keyword_leads("
            "run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, "
            "comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, "
            "raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "三角洲求陪玩",
                "comment",
                "aweme-2",
                "https://www.douyin.com/video/aweme-2",
                "user-2",
                "sec-2",
                "普通线索",
                "",
                "",
                "哈哈哈哈",
                30,
                "C",
                '["source:comment"]',
                "[]",
                "new",
                "not_contacted",
                "new",
                "[]",
                "{}",
                "user-2",
                "pending",
                "",
                "2026-05-28T10:00:00+00:00",
                None,
            ),
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/lead-pool?created_from=2026-05-30&created_to=2026-05-30&intent_query=上分")

    assert response.status_code == 200
    assert "高意向用户" in response.text
    assert "普通线索" not in response.text


def test_lead_pool_renders_comment_time_and_default_send_action(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    create_time = 1717166400
    expected_label = datetime.fromtimestamp(create_time, UTC).astimezone().strftime("%Y-%m-%d %H:%M")
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        conn.execute(
            "insert into keyword_leads("
            "run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, "
            "comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, "
            "profile_json, raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-2",
                "三角洲求陪玩",
                "comment",
                "aweme-9",
                "https://www.douyin.com/video/aweme-9",
                "user-9",
                "sec-9",
                "评论用户",
                "晚上在线",
                "",
                "今晚求带上分",
                90,
                "S",
                '["source:comment","intent:strong"]',
                '["求带","上分"]',
                "priority",
                "not_contacted",
                "new",
                "[]",
                '{"user":{"following_count":12,"follower_count":99,"aweme_count":18,"total_favorited":345}}',
                f'{{"text":"今晚求带上分","create_time":{create_time}}}',
                "user-9",
                "pending",
                "",
                "2026-05-30T10:00:00+00:00",
                None,
            ),
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/lead-pool")

    assert response.status_code == 200
    assert "评论时间" in response.text
    assert expected_label in response.text
    assert "发送默认私信" in response.text
    assert "默认模板" in response.text
    assert 'hx-post="/actions/lead-pool/send-default"' in response.text
    assert 'name="created_from"' in response.text
    assert 'name="intent_query"' in response.text


def test_lead_pool_uses_simplified_workspace_layout(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        conn.execute(
            "insert into keyword_leads("
            "run_id, keyword, source_type, source_aweme_id, source_url, user_id, sec_uid, nickname, signature, avatar_url, "
            "comment_text, score, grade, score_reasons, matched_signals, review_status, contact_status, conversion_status, risk_flags, "
            "profile_json, raw_payload, dedupe_key, message_status, message_error, created_at, messaged_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-3",
                "三角洲求陪玩",
                "comment",
                "aweme-3",
                "https://www.douyin.com/video/aweme-3",
                "user-3",
                "sec-3",
                "测试线索",
                "",
                "",
                "求带",
                90,
                "S",
                '["source:comment","intent:strong"]',
                '["求带"]',
                "priority",
                "not_contacted",
                "new",
                "[]",
                "{}",
                '{"text":"求带","create_time":1717166400}',
                "user-3",
                "pending",
                "",
                "2026-05-30T10:00:00+00:00",
                None,
            ),
        )
        conn.commit()
    client = TestClient(app)

    response = client.get("/lead-pool")

    assert response.status_code == 200
    assert 'class="shell-sidebar-summary"' in response.text
    assert 'class="lead-pool-toolbar"' in response.text
    assert 'class="lead-card-toolbar"' in response.text
    assert "lead-card-stats" in response.text
