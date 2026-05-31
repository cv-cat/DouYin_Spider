from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import traceback
import uuid

from web.db import connect_db, init_db

UTC = timezone.utc


class TaskManager:
    def __init__(self, db_path, broker=None):
        self.db_path = db_path
        self.broker = broker
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.runtimes = {}
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def submit(self, task_type, summary, runner):
        task_id = uuid.uuid4().hex
        started_at = datetime.now(UTC).isoformat()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into tasks(task_id, task_type, status, started_at, summary, error_summary) "
                "values(?, ?, ?, ?, ?, ?)",
                (task_id, task_type, "running", started_at, summary, ""),
            )
            conn.commit()
        self.executor.submit(self._run_task, task_id, task_type, runner)
        return task_id

    def _run_task(self, task_id, task_type, runner):
        try:
            result = runner()
            self._finish(task_id, task_type, "success", json.dumps({"result": result}, ensure_ascii=False), "")
        except Exception as exc:
            self._append_log(task_id, "error", traceback.format_exc())
            self._finish(task_id, task_type, "failed", "", f"{type(exc).__name__}: {exc}")

    def _finish(self, task_id, task_type, status, summary, error_summary):
        finished_at = datetime.now(UTC).isoformat()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update tasks set status = ?, finished_at = ?, summary = ?, error_summary = ? where task_id = ?",
                (status, finished_at, summary, error_summary, task_id),
            )
            conn.commit()
        if self.broker:
            self.broker.publish(
                "tasks",
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": status,
                    "summary": summary,
                    "error_summary": error_summary,
                },
            )

    def _append_log(self, task_id, level, message):
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into task_logs(task_id, created_at, level, message) values(?, ?, ?, ?)",
                (task_id, datetime.now(UTC).isoformat(), level, message),
            )
            conn.commit()

    def get_task(self, task_id):
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from tasks where task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
