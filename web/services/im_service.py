from datetime import UTC, datetime

from dy_apis.douyin_api import DouyinAPI
from dy_apis.douyin_recv_msg import DouyinRecvMsg
from web.db import connect_db, init_db


class IMService:
    def __init__(self, db_path, session_service, task_manager, broker, receiver_cls=DouyinRecvMsg):
        self.db_path = db_path
        self.sessions = session_service
        self.task_manager = task_manager
        self.broker = broker
        self.receiver_cls = receiver_cls
        with connect_db(self.db_path) as conn:
            init_db(conn)

    def _auth(self):
        auth = self.sessions.load_auth("douyin")
        if auth is None:
            raise RuntimeError("Missing douyin cookie")
        return auth

    def create_conversation(self, to_user_id):
        conversation_id, conversation_short_id, ticket = DouyinAPI.create_conversation(self._auth(), int(to_user_id))
        return {
            "conversation_id": conversation_id,
            "conversation_short_id": conversation_short_id,
            "ticket": ticket,
        }

    def get_conversation_detail(self, to_user_id, conversation_short_id):
        payload = DouyinAPI.get_conversation_list(self._auth(), int(to_user_id), int(conversation_short_id))
        return {"detail": payload}

    def send_message(self, conversation_id, conversation_short_id, ticket, content):
        payload = DouyinAPI.send_msg(self._auth(), conversation_id, conversation_short_id, ticket, content)
        return {"detail": payload}

    def start_receiver(self):
        def sink(payload):
            self.broker.publish("events", {"channel": "im", "payload": payload})

        runtime = self.receiver_cls(
            self._auth(),
            auto_reconnect=True,
            event_sink=sink,
            error_sink=lambda err: sink({"event_type": "error", "error": str(err)}),
            close_sink=lambda payload: sink({"event_type": "closed", "payload": payload}),
        )
        self.task_manager.runtimes["im:default"] = runtime
        with connect_db(self.db_path) as conn:
            conn.execute(
                "insert into im_receivers(scope, status, started_at, stopped_at, last_error) values(?, ?, ?, ?, ?) "
                "on conflict(scope) do update set status=excluded.status, started_at=excluded.started_at, stopped_at=excluded.stopped_at, last_error=excluded.last_error",
                ("default", "running", datetime.now(UTC).isoformat(), None, ""),
            )
            conn.commit()
        self.task_manager.submit("im.receive", "default", runtime.start)

    def stop_receiver(self):
        runtime = self.task_manager.runtimes.pop("im:default", None)
        if runtime:
            runtime.stop()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update im_receivers set status = ?, stopped_at = ? where scope = ?",
                ("stopped", datetime.now(UTC).isoformat(), "default"),
            )
            conn.commit()
