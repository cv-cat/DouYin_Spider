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
