from fastapi.testclient import TestClient

from web.db import connect_db
from web.services.im_service import IMService


def test_start_receiver_registers_runtime(tmp_path):
    published = []

    class DummyReceiver:
        def __init__(self, auth, auto_reconnect=True, event_sink=None, error_sink=None, close_sink=None):
            self.event_sink = event_sink
            self.stopped = False

        def start(self):
            self.event_sink({"event_type": "text", "content": "hello"})

        def stop(self):
            self.stopped = True

    class DummySessionService:
        def load_auth(self, scope):
            return object()

    class DummyTaskManager:
        runtimes = {}

        def submit(self, task_type, summary, runner):
            runner()
            return "task-1"

    class DummyBroker:
        def publish(self, channel, payload):
            published.append((channel, payload))

    service = IMService(
        tmp_path / "web-ui.sqlite3",
        DummySessionService(),
        DummyTaskManager(),
        DummyBroker(),
        receiver_cls=DummyReceiver,
    )

    service.start_receiver()

    assert any(channel == "events" for channel, _ in published)
    assert "im:default" in service.task_manager.runtimes
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        receiver = conn.execute("select status from im_receivers where scope = ?", ("default",)).fetchone()
        event = conn.execute("select channel, event_type, payload from event_feed").fetchone()
    assert receiver["status"] == "running"
    assert event["channel"] == "im"
    assert event["event_type"] == "text"
    assert "hello" in event["payload"]

    service.stop_receiver()

    assert service.task_manager.runtimes == {}
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        receiver = conn.execute("select status from im_receivers where scope = ?", ("default",)).fetchone()
    assert receiver["status"] == "stopped"


def test_im_start_action_calls_service(app):
    calls = []

    class DummyIMService:
        def start_receiver(self):
            calls.append("start")

    app.state.im_service = DummyIMService()
    client = TestClient(app)

    response = client.post("/actions/im/start")

    assert response.status_code == 200
    assert calls == ["start"]
