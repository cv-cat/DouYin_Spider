from web.db import connect_db, init_db
from web.services.rules_service import RulesService


def test_rules_service_reads_seeded_modes_and_templates(tmp_path):
    db_path = tmp_path / "web-ui.sqlite3"
    with connect_db(db_path) as conn:
        init_db(conn)

    service = RulesService(db_path)
    snapshot = service.defaults()

    assert snapshot["selected_modes"] == {
        "source_mode": "comments_first",
        "precision_mode": "precision",
        "risk_mode": "safe",
        "outreach_mode": "manual",
    }
    assert snapshot["score_threshold"] == 80
    assert any(template["template_key"] == "first_touch_intro" for template in snapshot["templates"])
    assert any(template["template_key"] == "high_intent_followup" for template in snapshot["templates"])
