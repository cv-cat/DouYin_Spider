from datetime import UTC, datetime

from dy_apis.douyin_api import DouyinAPI
from dy_live.server import DouyinLive
from web.db import connect_db, init_db


class LiveService:
    def __init__(self, db_path, session_service, task_manager, broker, live_cls=DouyinLive):
        self.db_path = db_path
        self.sessions = session_service
        self.task_manager = task_manager
        self.broker = broker
        self.live_cls = live_cls
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def _auth(self):
        auth = self.sessions.load_auth("live")
        if auth is None:
            auth = self.sessions.load_auth("douyin")
        if auth is None:
            raise RuntimeError("Missing live cookie")
        return auth

    def lookup_room(self, live_id):
        return DouyinAPI.get_live_info(self._auth(), live_id)

    def send_room_message(self, room_id, content):
        return DouyinAPI.sendMsgInRoom(self._auth(), room_id, content)

    def like_room(self, room_id, count="1"):
        return DouyinAPI.diggLiveRoom(self._auth(), room_id, count)

    def start_listener(self, live_id):
        def sink(payload):
            self.broker.publish("events", {"channel": "live", "payload": payload})

        runtime = self.live_cls(
            live_id,
            self._auth(),
            event_sink=sink,
            error_sink=lambda err: sink({"event_type": "error", "error": str(err)}),
            restart_on_close=True,
        )
        self.task_manager.runtimes[f"live:{live_id}"] = runtime
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into live_watchers(room_id, status, started_at, stopped_at, last_error) values(?, ?, ?, ?, ?) "
                "on conflict(room_id) do update set status=excluded.status, started_at=excluded.started_at, stopped_at=excluded.stopped_at, last_error=excluded.last_error",
                (live_id, "running", datetime.now(UTC).isoformat(), None, ""),
            )
            conn.commit()
        self.task_manager.submit("live.listen", live_id, runtime.start_ws)

    def stop_listener(self, live_id):
        runtime = self.task_manager.runtimes.pop(f"live:{live_id}", None)
        if runtime:
            runtime.stop()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update live_watchers set status = ?, stopped_at = ? where room_id = ?",
                ("stopped", datetime.now(UTC).isoformat(), live_id),
            )
            conn.commit()
