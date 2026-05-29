import time

from web.tasks.manager import TaskManager


def test_task_manager_records_success(tmp_path):
    manager = TaskManager(tmp_path / "web-ui.sqlite3")

    task_id = manager.submit("echo", "test", lambda: "ok")

    deadline = time.time() + 2
    while time.time() < deadline:
        task = manager.get_task(task_id)
        if task["status"] == "success":
            break
        time.sleep(0.05)

    assert manager.get_task(task_id)["status"] == "success"


def test_task_manager_publishes_failure_payload_for_frontend(tmp_path):
    class DummyBroker:
        def __init__(self):
            self.events = []

        def publish(self, channel, payload):
            self.events.append((channel, payload))

    manager = TaskManager(tmp_path / "web-ui.sqlite3", broker=DummyBroker())

    task_id = manager.submit("crawl.search_export", "demo", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    deadline = time.time() + 2
    while time.time() < deadline:
        task = manager.get_task(task_id)
        if task["status"] == "failed":
            break
        time.sleep(0.05)

    channel, payload = manager.broker.events[-1]
    assert channel == "tasks"
    assert payload["task_id"] == task_id
    assert payload["task_type"] == "crawl.search_export"
    assert payload["status"] == "failed"
    assert payload["error_summary"] == "RuntimeError: boom"
