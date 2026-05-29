from web.db import connect_db, init_db, list_tables


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "web-ui.sqlite3"
    with connect_db(db_path) as conn:
        init_db(conn)

    assert {
        "settings",
        "auth_sessions",
        "tasks",
        "task_logs",
        "live_watchers",
        "im_receivers",
        "event_feed",
    }.issubset(set(list_tables(db_path)))
