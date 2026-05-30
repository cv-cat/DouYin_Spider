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
