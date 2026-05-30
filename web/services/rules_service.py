from __future__ import annotations

from web.db import connect_db


DEFAULT_SOURCE_MODES = [
    {"key": "comments_first", "label": "评论区优先"},
    {"key": "search_first", "label": "搜索优先"},
    {"key": "live_first", "label": "直播补充"},
]

DEFAULT_PRECISION_MODES = [
    {"key": "precision", "label": "少而准"},
    {"key": "balanced", "label": "平衡"},
    {"key": "wide", "label": "多而广"},
]

DEFAULT_RISK_MODES = [
    {"key": "safe", "label": "安全优先"},
    {"key": "balanced", "label": "平衡"},
    {"key": "aggressive", "label": "激进"},
]


class RulesService:
    def __init__(self, db_path):
        self.db_path = db_path

    def defaults(self):
        selected_modes = self._selected_modes()
        templates = self._templates()
        must_have_terms = ["求带", "陪玩", "上分"]
        secondary_terms = ["找队友", "找搭子", "车队"]
        support_terms = ["段位", "卡关", "上不去", "想赢"]
        return {
            "source_modes": DEFAULT_SOURCE_MODES,
            "precision_modes": DEFAULT_PRECISION_MODES,
            "risk_modes": DEFAULT_RISK_MODES,
            "selected_modes": selected_modes,
            "score_threshold": self._score_threshold(),
            "templates": templates,
            "must_have_terms": must_have_terms,
            "secondary_terms": secondary_terms,
            "support_terms": support_terms,
            "keyword_tag_groups": [
                {"label": "强意图", "terms": must_have_terms},
                {"label": "组队意图", "terms": secondary_terms},
                {"label": "痛点辅助", "terms": support_terms},
            ],
        }

    def _selected_modes(self):
        values = self._rule_map()
        return {
            "source_mode": values.get("default_source_mode", "comments_first"),
            "precision_mode": values.get("default_precision_mode", "precision"),
            "risk_mode": values.get("default_risk_mode", "safe"),
            "outreach_mode": values.get("default_outreach_mode", "manual"),
        }

    def _score_threshold(self):
        values = self._rule_map()
        try:
            return int(values.get("high_intent_score_threshold", "80"))
        except ValueError:
            return 80

    def _templates(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "select template_key, category, title, body, enabled from outreach_templates order by id asc"
            ).fetchall()
        return [dict(row) for row in rows]

    def _rule_map(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "select rule_key, value from acquisition_rules order by rule_key asc"
            ).fetchall()
        return {row["rule_key"]: row["value"] for row in rows}
