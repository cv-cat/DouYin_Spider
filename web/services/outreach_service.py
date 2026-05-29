from __future__ import annotations

from web.db import connect_db


DEFAULT_OUTREACH_MODES = [
    {"key": "manual", "label": "人工审核"},
    {"key": "semi_auto", "label": "半自动触达"},
    {"key": "batch", "label": "批量私信"},
]


class OutreachService:
    def __init__(self, db_path):
        self.db_path = db_path

    def list_modes(self):
        return DEFAULT_OUTREACH_MODES

    def list_templates(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "select template_key, category, title, body, enabled from outreach_templates "
                "where enabled = 1 order by id asc"
            ).fetchall()
        return [dict(row) for row in rows]

    def queue_preview(self, limit=20):
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "select id, run_id, keyword, nickname, user_id, source_type, comment_text, message_status "
                "from keyword_leads order by id desc limit ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
