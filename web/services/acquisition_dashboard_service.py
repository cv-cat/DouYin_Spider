from __future__ import annotations

from datetime import UTC, date, datetime

from web.db import connect_db


class AcquisitionDashboardService:
    def __init__(self, db_path):
        self.db_path = db_path

    def summary(self):
        today_prefix = date.today().isoformat()
        with connect_db(self.db_path) as conn:
            today_leads = conn.execute(
                "select count(*) as c from keyword_leads where created_at like ?",
                (f"{today_prefix}%",),
            ).fetchone()["c"]
            total_leads = conn.execute("select count(*) as c from keyword_leads").fetchone()["c"]
            contacted_count = self._safe_count(
                conn,
                "select count(*) as c from keyword_leads where contact_status != 'not_contacted'",
            )
            replied_count = self._safe_count(
                conn,
                "select count(*) as c from keyword_leads where conversion_status in ('replied', 'contact_added', 'paid')",
            )
            paid_count = self._safe_count(
                conn,
                "select count(*) as c from keyword_leads where conversion_status = 'paid'",
            )
            running_tasks = conn.execute(
                "select count(*) as c from keyword_runs where status in ('queued', 'running')"
            ).fetchone()["c"]
            source_counts = {
                row["source_type"]: row["c"]
                for row in conn.execute(
                    "select source_type, count(*) as c from keyword_leads group by source_type order by c desc"
                ).fetchall()
            }
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "today_leads": today_leads,
            "total_leads": total_leads,
            "contacted_count": contacted_count,
            "replied_count": replied_count,
            "paid_count": paid_count,
            "running_tasks": running_tasks,
            "source_counts": source_counts,
        }

    def _safe_count(self, conn, query):
        try:
            return conn.execute(query).fetchone()["c"]
        except Exception:
            return 0
