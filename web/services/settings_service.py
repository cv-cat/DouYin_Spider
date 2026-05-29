import json

from web.db import connect_db, init_db


class SettingsService:
    def __init__(self, db_path):
        self.db_path = db_path
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def load(self):
        with connect_db(self.db_path) as conn:
            rows = conn.execute("select key, value from settings").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}

    def save_many(self, values):
        with connect_db(self.db_path) as conn:
            for key, value in values.items():
                conn.execute(
                    "insert into settings(key, value) values(?, ?) "
                    "on conflict(key) do update set value=excluded.value",
                    (key, json.dumps(value)),
                )
            conn.commit()
