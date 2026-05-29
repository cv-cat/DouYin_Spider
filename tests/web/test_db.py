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
        "keyword_runs",
        "keyword_leads",
    }.issubset(set(list_tables(db_path)))


def test_connect_db_creates_parent_directory(tmp_path):
    db_path = tmp_path / "nested" / "web-ui.sqlite3"

    with connect_db(db_path) as conn:
        init_db(conn)

    assert db_path.exists()


def test_init_db_creates_acquisition_schema_and_seed_defaults(tmp_path):
    db_path = tmp_path / "web-ui.sqlite3"

    with connect_db(db_path) as conn:
        init_db(conn)
        run_columns = {
            row["name"]
            for row in conn.execute("pragma table_info(keyword_runs)").fetchall()
        }
        lead_columns = {
            row["name"]
            for row in conn.execute("pragma table_info(keyword_leads)").fetchall()
        }
        rule_rows = conn.execute(
            "select rule_key, value from acquisition_rules order by rule_key"
        ).fetchall()
        template_rows = conn.execute(
            "select template_key, category, enabled from outreach_templates order by template_key"
        ).fetchall()

    workflow_tables = set(list_tables(db_path))

    assert {
        "source_mode",
        "precision_mode",
        "risk_mode",
        "outreach_mode",
        "high_intent_count",
        "contacted_count",
        "replied_count",
    }.issubset(run_columns)
    assert {
        "comment_text",
        "score",
        "grade",
        "score_reasons",
        "matched_signals",
        "review_status",
        "contact_status",
        "conversion_status",
        "risk_flags",
    }.issubset(lead_columns)
    assert {
        "outreach_templates",
        "outreach_events",
        "acquisition_rules",
    }.issubset(workflow_tables)
    assert {
        ("default_outreach_mode", "manual"),
        ("default_precision_mode", "precision"),
        ("default_risk_mode", "safe"),
        ("default_source_mode", "comments_first"),
    }.issubset({(row["rule_key"], row["value"]) for row in rule_rows})
    assert {
        ("first_touch_intro", "manual", 1),
        ("high_intent_followup", "followup", 1),
    }.issubset(
        {
            (row["template_key"], row["category"], row["enabled"])
            for row in template_rows
        }
    )
