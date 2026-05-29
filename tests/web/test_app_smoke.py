from fastapi.testclient import TestClient

from web.app import create_app
from web.db import connect_db


def test_core_pages_load(client):
    for path in ["/", "/login", "/data-crawl", "/keyword-funnel", "/live-monitor", "/private-messages", "/tasks", "/settings"]:
        response = client.get(path)
        assert response.status_code == 200
    assert "DouYin_Spider Web UI" in client.get("/").text
    assert 'id="app-toast-stack"' in client.get("/").text


def test_create_app_is_independent_from_cwd(monkeypatch, tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    monkeypatch.chdir(outside_dir)

    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "DouYin_Spider Web UI" in response.text


def test_tasks_page_shows_keyword_run_progress(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        conn.execute(
            "insert into tasks(task_id, task_type, status, started_at, summary, error_summary) values(?, ?, ?, ?, ?, ?)",
            ("task-1", "keyword.collect", "running", "2026-05-30T00:00:00+00:00", "三角洲", ""),
        )
        conn.execute(
            "insert into keyword_runs("
            "run_id, task_id, keyword, status, require_num, include_comments, comment_limit, "
            "source_mode, precision_mode, risk_mode, outreach_mode, total_count, processed_count, lead_count, "
            "high_intent_count, contacted_count, replied_count, summary, created_at, updated_at"
            ") values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-1",
                "task-1",
                "三角洲",
                "running",
                10,
                1,
                20,
                "comments_first",
                "precision",
                "safe",
                "manual",
                10,
                0,
                0,
                0,
                0,
                0,
                "正在处理第 1/10 条作品：抓取评论",
                "2026-05-30T00:00:00+00:00",
                "2026-05-30T00:00:00+00:00",
            ),
        )
        conn.commit()

    client = TestClient(app)
    response = client.get("/tasks")

    assert response.status_code == 200
    assert "0/10" in response.text
    assert "正在处理第 1/10 条作品：抓取评论" in response.text
