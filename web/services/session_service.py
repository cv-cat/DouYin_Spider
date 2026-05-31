from datetime import datetime, timezone

from builder.auth import DouyinAuth
from web.db import connect_db, init_db

UTC = timezone.utc


class SessionService:
    def __init__(self, db_path):
        self.db_path = db_path
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def save_cookie(self, scope, cookie_str, status="unknown"):
        now = datetime.now(UTC).isoformat()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into auth_sessions(scope, cookie_str, status, updated_at) values(?, ?, ?, ?) "
                "on conflict(scope) do update set cookie_str=excluded.cookie_str, status=excluded.status, updated_at=excluded.updated_at",
                (scope, cookie_str, status, now),
            )
            conn.commit()

    def load_auth(self, scope):
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select cookie_str from auth_sessions where scope = ?",
                (scope,),
            ).fetchone()
        if not row:
            return None
        auth = DouyinAuth()
        auth.perepare_auth(row["cookie_str"], "", "")
        return auth
