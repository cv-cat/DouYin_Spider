from datetime import datetime, timezone
import json

from dy_apis.douyin_api import DouyinAPI
from dy_live.server import DouyinLive
from web.db import connect_db, init_db

UTC = timezone.utc


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
            event = {"channel": "live", "room_id": live_id, "payload": payload}
            self._record_event(event)
            self.broker.publish("events", event)

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

    def _record_event(self, event):
        payload = event.get("payload") or {}
        event_type = str(payload.get("event_type") or "live")
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into event_feed(channel, event_type, payload, created_at) values(?, ?, ?, ?)",
                ("live", event_type, json.dumps(event, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )
            conn.commit()

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

    def invoke(self, operation, payload):
        auth = self._auth()
        dispatch = {
            "get_live_production": lambda: DouyinAPI.get_live_production(
                auth,
                payload["url"],
                payload["room_id"],
                payload["author_id"],
                payload.get("offset", "0"),
            ),
            "get_all_live_production": lambda: DouyinAPI.get_all_live_production(
                auth,
                payload["url"],
            ),
            "get_live_production_detail": lambda: DouyinAPI.get_live_production_detail(
                auth,
                payload["url"],
                payload["ec_promotion_id"],
                payload["sec_author_id"],
                payload["live_room_id"],
            ),
            "get_rank_list": lambda: DouyinAPI.get_rank_list(
                auth,
                payload["room_id"],
                payload["anchor_id"],
                payload["sec_anchor_id"],
            ),
            "get_webcast_detail": lambda: DouyinAPI.get_webcast_detail(
                auth,
                payload["user_id"],
                payload["room_id"],
                payload["url"],
            ),
        }
        if operation not in dispatch:
            raise ValueError(f"Unsupported live operation: {operation}")
        return dispatch[operation]()
