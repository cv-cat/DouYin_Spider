from fastapi.testclient import TestClient

from web.db import connect_db
from web.app import create_app
from web.services.live_service import LiveService


def test_start_listener_registers_runtime(tmp_path):
    events = []

    class DummyLiveRuntime:
        def __init__(self, live_id, auth_, event_sink=None, error_sink=None, close_sink=None, restart_on_close=True):
            self.live_id = live_id
            self.event_sink = event_sink
            self.closed = False

        def start_ws(self):
            self.event_sink({"event_type": "chat", "content": "hello"})

        def stop(self):
            self.closed = True

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
            events.append((channel, payload))

    service = LiveService(
        tmp_path / "web-ui.sqlite3",
        DummySessionService(),
        DummyTaskManager(),
        DummyBroker(),
        live_cls=DummyLiveRuntime,
    )

    service.start_listener("123")

    assert any(channel == "events" for channel, _ in events)
    assert "live:123" in service.task_manager.runtimes
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        watcher = conn.execute("select status from live_watchers where room_id = ?", ("123",)).fetchone()
    assert watcher["status"] == "running"

    service.stop_listener("123")

    assert service.task_manager.runtimes == {}
    with connect_db(tmp_path / "web-ui.sqlite3") as conn:
        watcher = conn.execute("select status from live_watchers where room_id = ?", ("123",)).fetchone()
    assert watcher["status"] == "stopped"


def test_live_start_action_calls_service(app):
    calls = []

    class DummyLiveService:
        def start_listener(self, live_id):
            calls.append(live_id)

    app.state.live_service = DummyLiveService()
    client = TestClient(app)

    response = client.post("/actions/live/start", data={"live_id": "123"})

    assert response.status_code == 200
    assert calls == ["123"]
