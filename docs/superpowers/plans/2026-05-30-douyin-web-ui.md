# DouYin_Spider Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only Web UI for `DouYin_Spider` that wraps the existing crawler, login, live-room, and private-message capabilities without rewriting the capability layer.

**Architecture:** Add a thin `web/` application around the current repository using `FastAPI + Jinja2 + HTMX + SSE + SQLite`. Keep `dy_apis`, `dy_live`, `main.py`, and `builder/` as the capability layer, but make targeted callback-friendly changes to the live and IM websocket modules so the UI can consume structured events instead of raw `print` output.

**Tech Stack:** Python 3.14, FastAPI, Jinja2, Uvicorn, HTMX, native EventSource/SSE, SQLite, pytest, existing Playwright/request/websocket code.

---

## File Map

### Create

- `web/__init__.py`
  Import marker for the new package.
- `web/config.py`
  Local-only runtime settings and path helpers.
- `web/db.py`
  SQLite connection, schema bootstrap, and low-level persistence helpers.
- `web/models.py`
  Typed task/runtime/event payload shapes shared across routes and services.
- `web/app.py`
  FastAPI app factory and dependency wiring.
- `web/routes/pages.py`
  Server-rendered page routes.
- `web/routes/actions.py`
  Form/action endpoints for login, crawl, live, IM, tasks, and settings.
- `web/routes/streams.py`
  SSE endpoints for tasks and event feed.
- `web/services/session_service.py`
  Build `DouyinAuth` objects from persisted cookies and validate local auth state.
- `web/services/settings_service.py`
  Load/save local app settings from SQLite.
- `web/services/login_service.py`
  Wrap `DYLoginApi` for manual cookies, QR login tasks, and phone login tasks.
- `web/services/crawl_service.py`
  Wrap `Data_Spider` and `DouyinAPI` for direct lookups and batch jobs.
- `web/services/live_service.py`
  Wrap `DouyinLive` for room actions, listener lifecycle, and structured event emission.
- `web/services/im_service.py`
  Wrap `DouyinRecvMsg` for conversation actions, receiver lifecycle, and structured event emission.
- `web/tasks/broker.py`
  In-process publish/subscribe broker for SSE fan-out.
- `web/tasks/manager.py`
  Background task execution, state transitions, and runtime registry.
- `web/templates/base.html`
  Shared shell, navigation, and debug status area.
- `web/templates/overview.html`
  Dashboard summary page.
- `web/templates/login.html`
  Login center page.
- `web/templates/data_crawl.html`
  Crawl and interaction page.
- `web/templates/live_monitor.html`
  Live monitor page.
- `web/templates/private_messages.html`
  Private message page.
- `web/templates/tasks.html`
  Tasks and logs page.
- `web/templates/settings.html`
  Local settings page.
- `web/templates/components/error_panel.html`
  Raw exception and traceback renderer.
- `web/templates/components/task_rows.html`
  Task table partial.
- `web/templates/components/event_feed.html`
  Event feed partial.
- `web/static/app.css`
  Local-only admin UI styling.
- `web/static/app.js`
  EventSource wiring and HTMX helpers.
- `tests/conftest.py`
  Shared fixtures for app/db/temp paths.
- `tests/web/test_app_smoke.py`
  App creation and page smoke tests.
- `tests/web/test_db.py`
  Schema bootstrap and persistence tests.
- `tests/web/test_task_manager.py`
  Background task lifecycle tests.
- `tests/web/test_login_service.py`
  Login-center behavior tests.
- `tests/web/test_crawl_service.py`
  Crawl and interaction route tests.
- `tests/web/test_live_service.py`
  Live monitor lifecycle tests.
- `tests/web/test_im_service.py`
  IM lifecycle tests.
- `tests/web/test_settings_service.py`
  Settings persistence tests.

### Modify

- `requirements.txt`
  Add the web/runtime/test dependencies required by the new UI.
- `dy_live/server.py`
  Preserve script behavior while adding structured callbacks, explicit stop support, and restart control.
- `dy_apis/douyin_recv_msg.py`
  Preserve script behavior while adding structured callbacks, explicit stop support, and restart control.
- `README.md`
  Document the new local Web UI run path and validation scope.

## Task 1: Bootstrap the Web App Shell

**Files:**
- Create: `web/__init__.py`
- Create: `web/config.py`
- Create: `web/app.py`
- Create: `web/routes/pages.py`
- Create: `web/templates/base.html`
- Create: `web/templates/overview.html`
- Create: `web/static/app.css`
- Create: `tests/conftest.py`
- Test: `tests/web/test_app_smoke.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Write the failing smoke test**

```python
# tests/web/test_app_smoke.py
from fastapi.testclient import TestClient

from web.app import create_app


def test_overview_page_loads(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "DouYin_Spider Web UI" in response.text
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_app_smoke.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'web'`

- [ ] **Step 3: Add minimal dependencies and app skeleton**

```text
# requirements.txt
fastapi
jinja2
uvicorn
python-multipart
httpx
pytest
```

```python
# web/config.py
from pathlib import Path


class WebConfig:
    def __init__(self, overrides=None):
        overrides = overrides or {}
        project_root = Path(__file__).resolve().parents[1]
        datas_root = project_root / "datas"
        self.host = "127.0.0.1"
        self.port = int(overrides.get("PORT", 8000))
        self.db_path = Path(overrides.get("DB_PATH", project_root / "datas" / "web-ui.sqlite3"))
        self.media_dir = Path(overrides.get("MEDIA_DIR", datas_root / "media_datas"))
        self.excel_dir = Path(overrides.get("EXCEL_DIR", datas_root / "excel_datas"))
```

```python
# web/app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.config import WebConfig
from web.routes.pages import router as pages_router


def create_app(overrides=None) -> FastAPI:
    config = WebConfig(overrides)
    app = FastAPI(title="DouYin_Spider Web UI")
    app.state.config = config
    app.mount("/static", StaticFiles(directory="web/static"), name="static")
    app.include_router(pages_router)
    return app
```

```python
# web/routes/pages.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    return templates.TemplateResponse(
        "overview.html",
        {"request": request, "title": "DouYin_Spider Web UI"},
    )
```

```html
<!-- web/templates/base.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <title>{{ title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <link rel="stylesheet" href="/static/app.css">
  </head>
  <body>
    <header class="shell-header">
      <h1>DouYin_Spider Web UI</h1>
      <nav>
        <a href="/">概览</a>
      </nav>
    </header>
    <main>{% block content %}{% endblock %}</main>
  </body>
</html>
```

```html
<!-- web/templates/overview.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>概览</h2>
  <p>本地调试入口已启动。</p>
</section>
{% endblock %}
```

```css
/* web/static/app.css */
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; background: #f4efe5; color: #1c1917; }
.shell-header { display: flex; justify-content: space-between; align-items: center; padding: 20px 28px; background: linear-gradient(135deg, #f97316, #fb7185); color: #fff7ed; }
.shell-header a { color: inherit; margin-left: 16px; text-decoration: none; }
.panel { margin: 24px; padding: 20px; border-radius: 16px; background: #fffaf0; box-shadow: 0 12px 32px rgba(28, 25, 23, 0.08); }
```

```python
# tests/conftest.py
import pytest

from web.app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_app_smoke.py -v`

Expected: PASS with `1 passed`

- [ ] **Step 5: Commit the shell bootstrap**

```bash
git add requirements.txt web/__init__.py web/config.py web/app.py web/routes/pages.py web/templates/base.html web/templates/overview.html web/static/app.css tests/conftest.py tests/web/test_app_smoke.py
git commit -m "feat: bootstrap local web ui shell"
```

## Task 2: Add SQLite Schema, Local Settings, and Session Persistence

**Files:**
- Create: `web/db.py`
- Create: `web/models.py`
- Create: `web/services/settings_service.py`
- Create: `web/services/session_service.py`
- Test: `tests/web/test_db.py`
- Test: `tests/web/test_settings_service.py`
- Modify: `web/app.py`
- Modify: `web/routes/pages.py`

- [ ] **Step 1: Write failing persistence tests**

```python
# tests/web/test_db.py
from web.db import connect_db, init_db, list_tables


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "web-ui.sqlite3"
    with connect_db(db_path) as conn:
        init_db(conn)

    assert {
        "settings",
        "auth_sessions",
        "tasks",
        "task_logs",
        "live_watchers",
        "im_receivers",
        "event_feed",
    }.issubset(set(list_tables(db_path)))
```

```python
# tests/web/test_settings_service.py
from web.services.settings_service import SettingsService


def test_settings_round_trip(tmp_path):
    service = SettingsService(tmp_path / "web-ui.sqlite3")
    service.save_many({"media_dir": "/tmp/media", "excel_dir": "/tmp/excel"})

    data = service.load()

    assert data["media_dir"] == "/tmp/media"
    assert data["excel_dir"] == "/tmp/excel"
```

- [ ] **Step 2: Run the persistence tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_db.py tests/web/test_settings_service.py -v`

Expected: FAIL with import errors for `web.db` and `web.services.settings_service`

- [ ] **Step 3: Implement schema bootstrap and storage services**

```python
# web/db.py
import sqlite3
from pathlib import Path


SCHEMA = """
create table if not exists settings (
    key text primary key,
    value text not null
);
create table if not exists auth_sessions (
    scope text primary key,
    cookie_str text not null,
    status text not null,
    updated_at text not null
);
create table if not exists tasks (
    task_id text primary key,
    task_type text not null,
    status text not null,
    started_at text not null,
    finished_at text,
    summary text,
    error_summary text
);
create table if not exists task_logs (
    id integer primary key autoincrement,
    task_id text not null,
    created_at text not null,
    level text not null,
    message text not null
);
create table if not exists live_watchers (
    room_id text primary key,
    status text not null,
    started_at text,
    stopped_at text,
    last_error text
);
create table if not exists im_receivers (
    scope text primary key,
    status text not null,
    started_at text,
    stopped_at text,
    last_error text
);
create table if not exists event_feed (
    id integer primary key autoincrement,
    channel text not null,
    event_type text not null,
    payload text not null,
    created_at text not null
);
"""


def connect_db(db_path: Path | str):
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def list_tables(db_path):
    with connect_db(db_path) as conn:
        rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return [row["name"] for row in rows]
```

```python
# web/models.py
from dataclasses import dataclass


@dataclass(slots=True)
class AuthSessionRecord:
    scope: str
    cookie_str: str
    status: str
    updated_at: str
```

```python
# web/services/settings_service.py
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
```

```python
# web/services/session_service.py
from datetime import datetime, UTC

from builder.auth import DouyinAuth
from web.db import connect_db, init_db


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
            row = conn.execute("select cookie_str from auth_sessions where scope = ?", (scope,)).fetchone()
        if not row:
            return None
        auth = DouyinAuth()
        auth.perepare_auth(row["cookie_str"], "", "")
        return auth
```

```python
# web/app.py
from web.db import connect_db, init_db
from web.services.session_service import SessionService
from web.services.settings_service import SettingsService


def create_app(overrides=None) -> FastAPI:
    config = WebConfig(overrides)
    app = FastAPI(title="DouYin_Spider Web UI")
    with connect_db(config.db_path) as conn:
        init_db(conn)
    app.state.settings_service = SettingsService(config.db_path)
    app.state.session_service = SessionService(config.db_path)
```

- [ ] **Step 4: Extend the overview page to read persisted state**

```python
# web/routes/pages.py
@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    settings_data = request.app.state.settings_service.load()
    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "title": "DouYin_Spider Web UI",
            "settings_data": settings_data,
        },
    )
```

```html
<!-- web/templates/overview.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>概览</h2>
  <p>本机地址固定为 127.0.0.1。</p>
  <pre>{{ settings_data }}</pre>
</section>
{% endblock %}
```

- [ ] **Step 5: Run the persistence test slice**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_db.py tests/web/test_settings_service.py tests/web/test_app_smoke.py -v`

Expected: PASS with `3 passed`

- [ ] **Step 6: Commit schema and persistence**

```bash
git add web/db.py web/models.py web/services/settings_service.py web/services/session_service.py web/app.py web/routes/pages.py web/templates/overview.html tests/web/test_db.py tests/web/test_settings_service.py
git commit -m "feat: add local sqlite state for web ui"
```

## Task 3: Build the Task Manager and SSE Broker

**Files:**
- Create: `web/tasks/broker.py`
- Create: `web/tasks/manager.py`
- Create: `web/routes/streams.py`
- Create: `web/templates/components/task_rows.html`
- Create: `web/templates/components/event_feed.html`
- Create: `web/static/app.js`
- Test: `tests/web/test_task_manager.py`
- Modify: `web/app.py`
- Modify: `web/routes/pages.py`

- [ ] **Step 1: Write failing task lifecycle tests**

```python
# tests/web/test_task_manager.py
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
```

- [ ] **Step 2: Run the task-manager test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_task_manager.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'web.tasks.manager'`

- [ ] **Step 3: Implement background task execution and broker fan-out**

```python
# web/tasks/broker.py
from collections import defaultdict
from queue import Queue


class EventBroker:
    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, channel):
        queue = Queue()
        self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel, queue):
        if queue in self._subscribers[channel]:
            self._subscribers[channel].remove(queue)

    def publish(self, channel, payload):
        for queue in list(self._subscribers[channel]):
            queue.put(payload)
```

```python
# web/tasks/manager.py
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
import json
import traceback
import uuid

from web.db import connect_db, init_db


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
                "insert into tasks(task_id, task_type, status, started_at, summary, error_summary) values(?, ?, ?, ?, ?, ?)",
                (task_id, task_type, "running", started_at, summary, ""),
            )
            conn.commit()
        self.executor.submit(self._run_task, task_id, runner)
        return task_id

    def _run_task(self, task_id, runner):
        try:
            result = runner()
            self._finish(task_id, "success", json.dumps({"result": result}, ensure_ascii=False), "")
        except Exception as exc:
            self._append_log(task_id, "error", traceback.format_exc())
            self._finish(task_id, "failed", "", f"{type(exc).__name__}: {exc}")

    def _finish(self, task_id, status, summary, error_summary):
        finished_at = datetime.now(UTC).isoformat()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update tasks set status = ?, finished_at = ?, summary = ?, error_summary = ? where task_id = ?",
                (status, finished_at, summary, error_summary, task_id),
            )
            conn.commit()
        if self.broker:
            self.broker.publish("tasks", {"task_id": task_id, "status": status})

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
```

```python
# web/routes/streams.py
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/streams")


@router.get("/tasks")
def task_stream(request: Request):
    queue = request.app.state.broker.subscribe("tasks")

    def event_generator():
        try:
            while True:
                payload = queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            request.app.state.broker.unsubscribe("tasks", queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/events")
def event_stream(request: Request):
    queue = request.app.state.broker.subscribe("events")

    def event_generator():
        try:
            while True:
                payload = queue.get()
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            request.app.state.broker.unsubscribe("events", queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

```html
<!-- web/templates/components/task_rows.html -->
<table class="task-table">
  <thead>
    <tr><th>任务ID</th><th>类型</th><th>状态</th><th>摘要</th></tr>
  </thead>
  <tbody>
    {% for task in tasks %}
    <tr>
      <td>{{ task["task_id"] }}</td>
      <td>{{ task["task_type"] }}</td>
      <td>{{ task["status"] }}</td>
      <td>{{ task["summary"] }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
```

```html
<!-- web/templates/components/event_feed.html -->
<div id="event-feed" class="event-feed"></div>
```

```javascript
// web/static/app.js
document.addEventListener("DOMContentLoaded", () => {
  const taskFeed = document.querySelector("[data-task-feed]");
  if (taskFeed) {
    const source = new EventSource("/streams/tasks");
    source.onmessage = () => {
      htmx.ajax("GET", "/tasks?partial=rows", { target: "[data-task-feed]", swap: "innerHTML" });
    };
  }

  const eventFeed = document.querySelector("#event-feed");
  if (eventFeed) {
    const eventSource = new EventSource("/streams/events");
    eventSource.onmessage = (event) => {
      const line = document.createElement("pre");
      line.textContent = event.data;
      eventFeed.prepend(line);
    };
  }
});
```

- [ ] **Step 4: Wire broker and task manager into the app**

```python
# web/app.py
from web.routes.streams import router as streams_router
from web.tasks.broker import EventBroker
from web.tasks.manager import TaskManager


def create_app(overrides=None) -> FastAPI:
    config = WebConfig(overrides)
    app = FastAPI(title="DouYin_Spider Web UI")
    app.state.broker = EventBroker()
    app.state.task_manager = TaskManager(config.db_path, broker=app.state.broker)
    app.include_router(streams_router)
```

- [ ] **Step 5: Run the task-manager tests**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_task_manager.py tests/web/test_app_smoke.py -v`

Expected: PASS with `2 passed`

- [ ] **Step 6: Commit task infrastructure**

```bash
git add web/tasks/broker.py web/tasks/manager.py web/routes/streams.py web/templates/components/task_rows.html web/templates/components/event_feed.html web/static/app.js web/app.py tests/web/test_task_manager.py
git commit -m "feat: add background task manager and sse broker"
```

## Task 4: Implement the Login Center

**Files:**
- Create: `web/services/login_service.py`
- Create: `web/routes/actions.py`
- Create: `web/templates/login.html`
- Test: `tests/web/test_login_service.py`
- Modify: `web/routes/pages.py`
- Modify: `web/templates/base.html`
- Modify: `web/services/session_service.py`
- Modify: `web/app.py`

- [ ] **Step 1: Write failing login-center tests**

```python
# tests/web/test_login_service.py
from fastapi.testclient import TestClient

from web.app import create_app


def test_manual_cookie_save_updates_session(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.post(
        "/actions/login/cookies",
        data={"scope": "douyin", "cookie_str": "msToken=test; sessionid=abc"},
    )

    assert response.status_code == 200
    assert "manual cookie saved" in response.text
```

- [ ] **Step 2: Run the login test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_login_service.py -v`

Expected: FAIL with `404 != 200`

- [ ] **Step 3: Implement the login service with injectable API wrapper**

```python
# web/services/login_service.py
from web.services.session_service import SessionService
from dy_apis.login_api import DYLoginApi


class LoginService:
    def __init__(self, db_path, task_manager, broker, api_cls=DYLoginApi):
        self.sessions = SessionService(db_path)
        self.task_manager = task_manager
        self.broker = broker
        self.api_cls = api_cls

    def save_manual_cookie(self, scope, cookie_str):
        self.sessions.save_cookie(scope, cookie_str, status="manual")
        self.broker.publish("events", {"channel": "login", "message": "manual cookie saved"})
        return {"ok": True, "message": "manual cookie saved"}

    def start_qr_login(self):
        def runner():
            api = self.api_cls()
            auth = __import__("asyncio").run(api.dyGenerateInitData(headless=True))
            qr_payload = api.dyGenerateQRcode(auth)
            token = qr_payload["data"]["token"]
            for _ in range(60):
                result = api.dyCheckQrCodeLogin(auth, token)
                status = result["data"]["status"]
                if status == "3":
                    self.sessions.save_cookie("douyin", auth.cookie_str, status="qr-success")
                    return {"status": status}
            raise TimeoutError("QR login polling timed out")

        return self.task_manager.submit("login.qr", "qr login", runner)

    def start_phone_code_request(self, phone_num):
        def runner():
            api = self.api_cls()
            auth = __import__("asyncio").run(api.dyGenerateInitData(headless=True))
            result = api.dyGeneratePhoneVerificationCode(phone_num, auth)
            self.sessions.save_cookie("douyin", auth.cookie_str, status="phone-code-requested")
            return result

        return self.task_manager.submit("login.phone.request_code", phone_num, runner)

    def finish_phone_login(self, phone_num, code):
        def runner():
            api = self.api_cls()
            auth = self.sessions.load_auth("douyin")
            if auth is None:
                raise RuntimeError("Missing phone-login bootstrap cookie")
            result, auth = api.dyPhoneLogin(phone_num, code, auth)
            self.sessions.save_cookie("douyin", auth.cookie_str, status="phone-login-success")
            return result

        return self.task_manager.submit("login.phone.finish", phone_num, runner)
```

```python
# web/routes/actions.py
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/actions")


@router.post("/login/cookies", response_class=HTMLResponse)
def save_manual_cookie(request: Request, scope: str = Form(...), cookie_str: str = Form(...)):
    result = request.app.state.login_service.save_manual_cookie(scope, cookie_str)
    return HTMLResponse(result["message"])
```

```python
# web/routes/pages.py
@router.get("/login", response_class=HTMLResponse)
def login_center(request: Request):
    sessions = request.app.state.session_service
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "登录中心", "douyin_auth": sessions.load_auth("douyin")},
    )
```

```html
<!-- web/templates/login.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>登录中心</h2>
  <form hx-post="/actions/login/cookies" hx-target="#login-result">
    <input type="hidden" name="scope" value="douyin">
    <textarea name="cookie_str" rows="6" placeholder="贴入 www.douyin.com cookie"></textarea>
    <button type="submit">保存 Cookie</button>
  </form>
  <form hx-post="/actions/login/qr" hx-target="#login-result">
    <button type="submit">启动二维码登录</button>
  </form>
  <form hx-post="/actions/login/phone/request-code" hx-target="#login-result">
    <input type="text" name="phone_num" placeholder="手机号">
    <button type="submit">发送验证码</button>
  </form>
  <form hx-post="/actions/login/phone/confirm" hx-target="#login-result">
    <input type="text" name="phone_num" placeholder="手机号">
    <input type="text" name="code" placeholder="验证码">
    <button type="submit">提交验证码登录</button>
  </form>
  <div id="login-result"></div>
</section>
{% endblock %}
```

- [ ] **Step 4: Add QR and phone-login background actions**

```python
# web/routes/actions.py
@router.post("/login/qr", response_class=HTMLResponse)
def start_qr_login(request: Request):
    task_id = request.app.state.login_service.start_qr_login()
    return HTMLResponse(f"QR login task queued: {task_id}")


@router.post("/login/phone/request-code", response_class=HTMLResponse)
def request_phone_code(request: Request, phone_num: str = Form(...)):
    task_id = request.app.state.login_service.start_phone_code_request(phone_num)
    return HTMLResponse(f"Phone code task queued: {task_id}")


@router.post("/login/phone/confirm", response_class=HTMLResponse)
def confirm_phone_login(request: Request, phone_num: str = Form(...), code: str = Form(...)):
    task_id = request.app.state.login_service.finish_phone_login(phone_num, code)
    return HTMLResponse(f"Phone login confirm task queued: {task_id}")
```

```python
# web/app.py
from web.routes.actions import router as actions_router
from web.services.login_service import LoginService


def create_app(overrides=None) -> FastAPI:
    config = WebConfig(overrides)
    app = FastAPI(title="DouYin_Spider Web UI")
    with connect_db(config.db_path) as conn:
        init_db(conn)
    app.state.config = config
    app.state.broker = EventBroker()
    app.state.task_manager = TaskManager(config.db_path, broker=app.state.broker)
    app.state.settings_service = SettingsService(config.db_path)
    app.state.session_service = SessionService(config.db_path)
    app.state.login_service = LoginService(config.db_path, app.state.task_manager, app.state.broker)
    app.mount("/static", StaticFiles(directory="web/static"), name="static")
    app.include_router(pages_router)
    app.include_router(streams_router)
    app.include_router(actions_router)
    return app
```

- [ ] **Step 5: Run the login test slice**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_login_service.py tests/web/test_app_smoke.py -v`

Expected: PASS with `2 passed`

- [ ] **Step 6: Commit the login center**

```bash
git add web/services/login_service.py web/routes/actions.py web/routes/pages.py web/templates/login.html web/templates/base.html web/app.py tests/web/test_login_service.py
git commit -m "feat: add login center to web ui"
```

## Task 5: Implement Data Crawl and Interaction Actions

**Files:**
- Create: `web/services/crawl_service.py`
- Create: `web/templates/data_crawl.html`
- Test: `tests/web/test_crawl_service.py`
- Modify: `web/routes/pages.py`
- Modify: `web/routes/actions.py`
- Modify: `web/templates/base.html`
- Modify: `web/app.py`

- [ ] **Step 1: Write failing crawl-route tests**

```python
# tests/web/test_crawl_service.py
from fastapi.testclient import TestClient

from web.app import create_app


def test_work_lookup_action_returns_payload(tmp_path, monkeypatch):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})

    class DummyCrawlService:
        def lookup_work(self, work_url):
            return {"work_url": work_url, "desc": "demo"}

    app.state.crawl_service = DummyCrawlService()
    client = TestClient(app)

    response = client.post("/actions/crawl/work", data={"work_url": "https://www.douyin.com/video/123"})

    assert response.status_code == 200
    assert "https://www.douyin.com/video/123" in response.text
```

- [ ] **Step 2: Run the crawl-route test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_crawl_service.py -v`

Expected: FAIL with `404 != 200`

- [ ] **Step 3: Implement direct lookups and batch-task submission**

```python
# web/services/crawl_service.py
from main import Data_Spider
from dy_apis.douyin_api import DouyinAPI


class CrawlService:
    def __init__(self, config, session_service, task_manager):
        self.config = config
        self.sessions = session_service
        self.task_manager = task_manager
        self.data_spider = Data_Spider()
        self.api = DouyinAPI()

    def _auth(self):
        auth = self.sessions.load_auth("douyin")
        if auth is None:
            raise RuntimeError("Missing douyin cookie")
        return auth

    def lookup_work(self, work_url):
        return self.data_spider.spider_work(self._auth(), work_url)

    def lookup_user(self, user_url):
        return self.api.get_user_info(self._auth(), user_url)

    def search_general(self, query, require_num, sort_type, publish_time, filter_duration="", search_range="", content_type=""):
        return self.api.search_some_general_work(
            self._auth(), query, int(require_num), sort_type, publish_time, filter_duration, search_range, content_type
        )

    def queue_user_export(self, user_url, save_choice="all"):
        base_path = {"media": str(self.config.media_dir), "excel": str(self.config.excel_dir)}
        return self.task_manager.submit(
            "crawl.user_all",
            user_url,
            lambda: self.data_spider.spider_user_all_work(self._auth(), user_url, base_path, save_choice),
        )

    def digg(self, aweme_id, digg_type="1"):
        return self.api.digg(self._auth(), aweme_id, digg_type)

    def publish_comment(self, aweme_id, content, reply_id=""):
        return self.api.publish_comment(self._auth(), aweme_id, content, reply_id)

    def collect_aweme(self, aweme_id, action="1"):
        return self.api.collect_aweme(self._auth(), aweme_id, action)
```

```python
# web/routes/actions.py
@router.post("/crawl/work", response_class=HTMLResponse)
def crawl_work(request: Request, work_url: str = Form(...)):
    payload = request.app.state.crawl_service.lookup_work(work_url)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/crawl/user-all", response_class=HTMLResponse)
def crawl_user_all(request: Request, user_url: str = Form(...), save_choice: str = Form("all")):
    task_id = request.app.state.crawl_service.queue_user_export(user_url, save_choice)
    return HTMLResponse(f"user export task queued: {task_id}")
```

```html
<!-- web/templates/data_crawl.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>数据抓取</h2>
  <form hx-post="/actions/crawl/work" hx-target="#crawl-result">
    <input type="text" name="work_url" placeholder="作品链接">
    <button type="submit">查询作品</button>
  </form>
  <form hx-post="/actions/crawl/user-all" hx-target="#crawl-result">
    <input type="text" name="user_url" placeholder="用户主页链接">
    <input type="hidden" name="save_choice" value="all">
    <button type="submit">后台导出用户全部作品</button>
  </form>
  <div id="crawl-result"></div>
</section>
{% endblock %}
```

- [ ] **Step 4: Add the data-crawl page route and menu entry**

```python
# web/routes/pages.py
@router.get("/data-crawl", response_class=HTMLResponse)
def data_crawl_page(request: Request):
    return templates.TemplateResponse(
        "data_crawl.html",
        {"request": request, "title": "数据抓取"},
    )
```

```html
<!-- web/templates/base.html -->
<nav>
  <a href="/">概览</a>
  <a href="/login">登录中心</a>
  <a href="/data-crawl">数据抓取</a>
</nav>
```

```python
# web/app.py, inside create_app()
from web.services.crawl_service import CrawlService

app.state.crawl_service = CrawlService(config, app.state.session_service, app.state.task_manager)
```

- [ ] **Step 5: Run the crawl test slice**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_crawl_service.py tests/web/test_app_smoke.py -v`

Expected: PASS with `2 passed`

- [ ] **Step 6: Commit crawl and interaction actions**

```bash
git add web/services/crawl_service.py web/templates/data_crawl.html web/routes/pages.py web/routes/actions.py web/templates/base.html web/app.py tests/web/test_crawl_service.py
git commit -m "feat: add crawl and interaction page"
```

## Task 6: Implement the Live Monitor with Structured Event Callbacks

**Files:**
- Create: `web/services/live_service.py`
- Create: `web/templates/live_monitor.html`
- Test: `tests/web/test_live_service.py`
- Modify: `dy_live/server.py`
- Modify: `web/routes/pages.py`
- Modify: `web/routes/actions.py`
- Modify: `web/app.py`
- Modify: `web/templates/base.html`

- [ ] **Step 1: Write failing live-service tests**

```python
# tests/web/test_live_service.py
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

    class DummyBroker:
        def publish(self, channel, payload):
            events.append((channel, payload))

    service = LiveService(tmp_path / "web-ui.sqlite3", DummySessionService(), DummyTaskManager(), DummyBroker(), live_cls=DummyLiveRuntime)
    room_id = "123"

    service.start_listener(room_id)

    assert any(channel == "events" for channel, _ in events)
```

- [ ] **Step 2: Run the live-service test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_live_service.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'web.services.live_service'`

- [ ] **Step 3: Retrofit `DouyinLive` with callbacks and explicit stop**

```python
# dy_live/server.py
class DouyinLive:
    def __init__(self, live_id, auth_, event_sink=None, error_sink=None, close_sink=None, restart_on_close=True):
        self.auth_ = auth_
        self.live_id = live_id
        self.event_sink = event_sink
        self.error_sink = error_sink
        self.close_sink = close_sink
        self.restart_on_close = restart_on_close
        self._stopped = False
        self.ws = None

    def emit(self, payload):
        if self.event_sink:
            self.event_sink(payload)
            return
        print(payload)

    def stop(self):
        self._stopped = True
        if self.ws:
            self.ws.close()

    def on_message(self, ws, message):
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            origin_bytes = gzip.decompress(frame.payload)
            response = Live_pb2.LiveResponse()
            response.ParseFromString(origin_bytes)
            if response.needAck:
                ack = Live_pb2.PushFrame()
                ack.payloadType = "ack"
                ack.payload = response.internalExt.encode("utf-8")
                ack.logId = frame.logId
                ws.send(ack.SerializeToString(), opcode=0x02)
            for item in response.messagesList:
                if item.method == "WebcastChatMessage":
                    chat = Live_pb2.ChatMessage()
                    chat.ParseFromString(item.payload)
                    self.emit({"event_type": "chat", "user": chat.user.nickname, "content": chat.content})
                elif item.method == "WebcastLikeMessage":
                    like = Live_pb2.LikeMessage()
                    like.ParseFromString(item.payload)
                    self.emit({"event_type": "like", "user": like.user.nickname, "count": like.count, "total": like.total})
                elif item.method == "WebcastGiftMessage":
                    gift = Live_pb2.GiftMessage()
                    gift.ParseFromString(item.payload)
                    self.emit({"event_type": "gift", "user": gift.user.nickname, "gift": gift.gift.name, "combo": gift.comboCount})
        except Exception as error:
            if self.error_sink:
                self.error_sink(error)
            else:
                print(str(error))

    def on_error(self, ws, error):
        if self.error_sink:
            self.error_sink(error)
        else:
            print(error)

    def on_close(self, ws, close_status_code, close_msg):
        if self.close_sink:
            self.close_sink({"status_code": close_status_code, "message": close_msg})
        if not self._stopped and self.restart_on_close:
            self.start_ws()
```

- [ ] **Step 4: Wrap live actions and listener lifecycle in `LiveService`**

```python
# web/services/live_service.py
from datetime import datetime, UTC

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

        runtime = self.live_cls(live_id, self._auth(), event_sink=sink, error_sink=lambda err: sink({"event_type": "error", "error": str(err)}), restart_on_close=True)
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
```

- [ ] **Step 5: Add live page routes and actions**

```python
# web/routes/pages.py
@router.get("/live-monitor", response_class=HTMLResponse)
def live_monitor_page(request: Request):
    return templates.TemplateResponse(
        "live_monitor.html",
        {"request": request, "title": "直播监听"},
    )
```

```python
# web/routes/actions.py
@router.post("/live/lookup", response_class=HTMLResponse)
def lookup_live_room(request: Request, live_id: str = Form(...)):
    payload = request.app.state.live_service.lookup_room(live_id)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/live/start", response_class=HTMLResponse)
def start_live_listener(request: Request, live_id: str = Form(...)):
    request.app.state.live_service.start_listener(live_id)
    return HTMLResponse(f"live listener started: {live_id}")


@router.post("/live/stop", response_class=HTMLResponse)
def stop_live_listener(request: Request, live_id: str = Form(...)):
    request.app.state.live_service.stop_listener(live_id)
    return HTMLResponse(f"live listener stopped: {live_id}")


@router.post("/live/send-message", response_class=HTMLResponse)
def send_live_message(request: Request, room_id: str = Form(...), content: str = Form(...)):
    payload = request.app.state.live_service.send_room_message(room_id, content)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/live/like", response_class=HTMLResponse)
def like_live_room(request: Request, room_id: str = Form(...), count: str = Form("1")):
    payload = request.app.state.live_service.like_room(room_id, count)
    return HTMLResponse(f"<pre>{payload}</pre>")
```

```html
<!-- web/templates/live_monitor.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>直播监听</h2>
  <form hx-post="/actions/live/lookup" hx-target="#live-result">
    <input type="text" name="live_id" placeholder="直播间 short id">
    <button type="submit">查询房间信息</button>
  </form>
  <form hx-post="/actions/live/start" hx-target="#live-result">
    <input type="text" name="live_id" placeholder="直播间 short id">
    <button type="submit">启动监听</button>
  </form>
  <form hx-post="/actions/live/stop" hx-target="#live-result">
    <input type="text" name="live_id" placeholder="直播间 short id">
    <button type="submit">停止监听</button>
  </form>
  <form hx-post="/actions/live/send-message" hx-target="#live-result">
    <input type="text" name="room_id" placeholder="room_id">
    <input type="text" name="content" placeholder="弹幕内容">
    <button type="submit">发送弹幕</button>
  </form>
  <form hx-post="/actions/live/like" hx-target="#live-result">
    <input type="text" name="room_id" placeholder="room_id">
    <input type="text" name="count" value="1">
    <button type="submit">点赞直播间</button>
  </form>
  <div id="live-result"></div>
  {% include "components/event_feed.html" %}
</section>
{% endblock %}
```

```python
# web/app.py, inside create_app()
from web.services.live_service import LiveService

app.state.live_service = LiveService(config.db_path, app.state.session_service, app.state.task_manager, app.state.broker)
```

- [ ] **Step 6: Run the live-service tests**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_live_service.py -v`

Expected: PASS with `1 passed`

- [ ] **Step 7: Commit the live monitor**

```bash
git add dy_live/server.py web/services/live_service.py web/templates/live_monitor.html web/routes/pages.py web/routes/actions.py web/templates/base.html web/app.py tests/web/test_live_service.py
git commit -m "feat: add live monitor page"
```

## Task 7: Implement Private Messages with Structured Receiver Callbacks

**Files:**
- Create: `web/services/im_service.py`
- Create: `web/templates/private_messages.html`
- Test: `tests/web/test_im_service.py`
- Modify: `dy_apis/douyin_recv_msg.py`
- Modify: `web/routes/pages.py`
- Modify: `web/routes/actions.py`
- Modify: `web/app.py`
- Modify: `web/templates/base.html`

- [ ] **Step 1: Write failing IM-service tests**

```python
# tests/web/test_im_service.py
from web.services.im_service import IMService


def test_start_receiver_registers_runtime(tmp_path):
    published = []

    class DummyReceiver:
        def __init__(self, auth, auto_reconnect=True, event_sink=None, error_sink=None, close_sink=None):
            self.event_sink = event_sink

        def start(self):
            self.event_sink({"event_type": "text", "content": "hello"})

        def stop(self):
            return None

    class DummySessionService:
        def load_auth(self, scope):
            return object()

    class DummyTaskManager:
        runtimes = {}

    class DummyBroker:
        def publish(self, channel, payload):
            published.append((channel, payload))

    service = IMService(tmp_path / "web-ui.sqlite3", DummySessionService(), DummyTaskManager(), DummyBroker(), receiver_cls=DummyReceiver)
    service.start_receiver()

    assert any(channel == "events" for channel, _ in published)
```

- [ ] **Step 2: Run the IM-service test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_im_service.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'web.services.im_service'`

- [ ] **Step 3: Retrofit `DouyinRecvMsg` with callbacks and stop support**

```python
# dy_apis/douyin_recv_msg.py
class DouyinRecvMsg:
    def __init__(self, auth: DouyinAuth, auto_reconnect=True, event_sink=None, error_sink=None, close_sink=None):
        self.auto_reconnect = auto_reconnect
        self.event_sink = event_sink
        self.error_sink = error_sink
        self.close_sink = close_sink
        self._stopped = False
        self.auth = auth
        self.ws = None
        deviceId = DouyinAPI.get_device_id(auth=self.auth)
        accessKey = f"{self.fpId + self.appKey + deviceId}f8a69f1719916z"
        accessKey = hashlib.md5(accessKey.encode(encoding="UTF-8")).hexdigest()
        params = Params()
        (params
         .add_param("aid", "6383")
         .add_param("device_platform", "douyin_pc")
         .add_param("fpid", self.fpId)
         .add_param("device_id", deviceId)
         .add_param("token", self.auth.cookie["sessionid"])
         .add_param("access_key", accessKey))
        self.url = f"wss://frontier-im.douyin.com/ws/v2?{params.toString()}"

    def emit(self, payload):
        if self.event_sink:
            self.event_sink(payload)
            return
        print(payload)

    def stop(self):
        self._stopped = True
        if self.ws:
            self.ws.close()

    def on_message(self, ws, message):
        frame = Live_pb2.PushFrame()
        frame.ParseFromString(message)
        if frame.payloadType == "pb":
            response = Response_pb2.Response()
            response.ParseFromString(frame.payload)
            sender = response.body.new_message_notify.message.sender
            conversation_id = response.body.new_message_notify.message.conversation_id
            msg_type = response.body.new_message_notify.message.message_type
            content = json.loads(response.body.new_message_notify.message.content)
            if msg_type == 7:
                self.emit({"event_type": "text", "conversation_id": conversation_id, "sender": sender, "content": content["text"]})
            elif msg_type == 27:
                self.emit({"event_type": "image", "conversation_id": conversation_id, "sender": sender, "content": content["resource_url"]["origin_url_list"][0]})

    def on_error(self, ws, error):
        if self.error_sink:
            self.error_sink(error)
        if (type(error) == ConnectionRefusedError or type(error) == websocket._exceptions.WebSocketConnectionClosedException) and self.auto_reconnect and not self._stopped:
            self.start()
```

- [ ] **Step 4: Wrap conversation actions and receiver lifecycle in `IMService`**

```python
# web/services/im_service.py
from datetime import datetime, UTC

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
        return DouyinAPI.create_conversation(self._auth(), int(to_user_id))

    def get_conversation_detail(self, to_user_id, conversation_short_id):
        return DouyinAPI.get_conversation_list(self._auth(), int(to_user_id), int(conversation_short_id))

    def send_message(self, conversation_id, conversation_short_id, ticket, content):
        return DouyinAPI.send_msg(self._auth(), conversation_id, conversation_short_id, ticket, content)

    def start_receiver(self):
        def sink(payload):
            self.broker.publish("events", {"channel": "im", "payload": payload})

        runtime = self.receiver_cls(self._auth(), auto_reconnect=True, event_sink=sink, error_sink=lambda err: sink({"event_type": "error", "error": str(err)}))
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
```

- [ ] **Step 5: Add IM page routes and actions**

```python
# web/routes/pages.py
@router.get("/private-messages", response_class=HTMLResponse)
def private_messages_page(request: Request):
    return templates.TemplateResponse(
        "private_messages.html",
        {"request": request, "title": "私信中心"},
    )
```

```python
# web/routes/actions.py
@router.post("/im/start", response_class=HTMLResponse)
def start_im_receiver(request: Request):
    request.app.state.im_service.start_receiver()
    return HTMLResponse("im receiver started")


@router.post("/im/stop", response_class=HTMLResponse)
def stop_im_receiver(request: Request):
    request.app.state.im_service.stop_receiver()
    return HTMLResponse("im receiver stopped")


@router.post("/im/conversation/create", response_class=HTMLResponse)
def create_im_conversation(request: Request, to_user_id: str = Form(...)):
    payload = request.app.state.im_service.create_conversation(to_user_id)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/im/conversation/detail", response_class=HTMLResponse)
def get_im_conversation_detail(request: Request, to_user_id: str = Form(...), conversation_short_id: str = Form(...)):
    payload = request.app.state.im_service.get_conversation_detail(to_user_id, conversation_short_id)
    return HTMLResponse(f"<pre>{payload}</pre>")


@router.post("/im/send", response_class=HTMLResponse)
def send_im_message(
    request: Request,
    conversation_id: str = Form(...),
    conversation_short_id: str = Form(...),
    ticket: str = Form(...),
    content: str = Form(...),
):
    payload = request.app.state.im_service.send_message(conversation_id, conversation_short_id, ticket, content)
    return HTMLResponse(f"<pre>{payload}</pre>")
```

```html
<!-- web/templates/private_messages.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>私信中心</h2>
  <form hx-post="/actions/im/start" hx-target="#im-result">
    <button type="submit">启动实时接收</button>
  </form>
  <form hx-post="/actions/im/stop" hx-target="#im-result">
    <button type="submit">停止实时接收</button>
  </form>
  <form hx-post="/actions/im/conversation/create" hx-target="#im-result">
    <input type="text" name="to_user_id" placeholder="to_user_id">
    <button type="submit">创建会话</button>
  </form>
  <form hx-post="/actions/im/conversation/detail" hx-target="#im-result">
    <input type="text" name="to_user_id" placeholder="to_user_id">
    <input type="text" name="conversation_short_id" placeholder="conversation_short_id">
    <button type="submit">查询会话详情</button>
  </form>
  <form hx-post="/actions/im/send" hx-target="#im-result">
    <input type="text" name="conversation_id" placeholder="conversation_id">
    <input type="text" name="conversation_short_id" placeholder="conversation_short_id">
    <input type="text" name="ticket" placeholder="ticket">
    <input type="text" name="content" placeholder="消息内容">
    <button type="submit">发送私信</button>
  </form>
  <div id="im-result"></div>
  {% include "components/event_feed.html" %}
</section>
{% endblock %}
```

```python
# web/app.py, inside create_app()
from web.services.im_service import IMService

app.state.im_service = IMService(config.db_path, app.state.session_service, app.state.task_manager, app.state.broker)
```

- [ ] **Step 6: Run the IM-service tests**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_im_service.py -v`

Expected: PASS with `1 passed`

- [ ] **Step 7: Commit the private-message page**

```bash
git add dy_apis/douyin_recv_msg.py web/services/im_service.py web/templates/private_messages.html web/routes/pages.py web/routes/actions.py web/templates/base.html web/app.py tests/web/test_im_service.py
git commit -m "feat: add private message page"
```

## Task 8: Finish Tasks, Settings, README, and End-to-End Verification

**Files:**
- Create: `web/templates/tasks.html`
- Create: `web/templates/settings.html`
- Create: `web/templates/components/error_panel.html`
- Modify: `web/routes/pages.py`
- Modify: `web/routes/actions.py`
- Modify: `web/static/app.js`
- Modify: `web/templates/base.html`
- Modify: `web/templates/overview.html`
- Modify: `web/app.py`
- Modify: `README.md`
- Test: `tests/web/test_app_smoke.py`

- [ ] **Step 1: Extend the smoke test to all pages**

```python
# tests/web/test_app_smoke.py
import pytest
from fastapi.testclient import TestClient

from web.app import create_app


@pytest.mark.parametrize(
    "path",
    ["/", "/login", "/data-crawl", "/live-monitor", "/private-messages", "/tasks", "/settings"],
)
def test_pages_load(tmp_path, path):
    app = create_app({"DB_PATH": str(tmp_path / "web-ui.sqlite3")})
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 200
```

- [ ] **Step 2: Run the smoke suite to verify the missing pages fail**

Run: `source .venv/bin/activate && python -m pytest tests/web/test_app_smoke.py -v`

Expected: FAIL for `/tasks` and `/settings`

- [ ] **Step 3: Implement tasks/logs pages and settings persistence actions**

```python
# web/routes/pages.py
@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request):
    partial = request.query_params.get("partial")
    task_manager = request.app.state.task_manager
    with connect_db(request.app.state.config.db_path) as conn:
        rows = conn.execute("select * from tasks order by started_at desc").fetchall()
    template_name = "components/task_rows.html" if partial == "rows" else "tasks.html"
    return templates.TemplateResponse(template_name, {"request": request, "tasks": [dict(row) for row in rows]})


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    settings_data = request.app.state.settings_service.load()
    return templates.TemplateResponse("settings.html", {"request": request, "settings_data": settings_data})
```

```python
# web/routes/actions.py
@router.post("/settings", response_class=HTMLResponse)
def save_settings(request: Request, media_dir: str = Form(...), excel_dir: str = Form(...), port: int = Form(...)):
    request.app.state.settings_service.save_many({"media_dir": media_dir, "excel_dir": excel_dir, "port": port})
    return HTMLResponse("settings saved; restart app to apply port change")
```

```html
<!-- web/templates/tasks.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>任务与日志</h2>
  <div data-task-feed>{% include "components/task_rows.html" %}</div>
</section>
{% endblock %}
```

```html
<!-- web/templates/settings.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>设置</h2>
  <form hx-post="/actions/settings" hx-target="#settings-result">
    <input type="text" name="media_dir" value="{{ settings_data.get('media_dir', '') }}">
    <input type="text" name="excel_dir" value="{{ settings_data.get('excel_dir', '') }}">
    <input type="number" name="port" value="{{ settings_data.get('port', 8000) }}">
    <button type="submit">保存</button>
  </form>
  <div id="settings-result"></div>
</section>
{% endblock %}
```

```html
<!-- web/templates/base.html -->
<nav>
  <a href="/">概览</a>
  <a href="/login">登录中心</a>
  <a href="/data-crawl">数据抓取</a>
  <a href="/live-monitor">直播监听</a>
  <a href="/private-messages">私信中心</a>
  <a href="/tasks">任务与日志</a>
  <a href="/settings">设置</a>
</nav>
```

- [ ] **Step 4: Add overview summaries and raw-error panel**

```html
<!-- web/templates/components/error_panel.html -->
{% if error_text %}
<details class="panel error-panel" open>
  <summary>原始异常</summary>
  <pre>{{ error_text }}</pre>
</details>
{% endif %}
```

```python
# web/routes/pages.py
@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    with connect_db(request.app.state.config.db_path) as conn:
        auth_row = conn.execute("select status from auth_sessions where scope = 'douyin'").fetchone()
        live_count = conn.execute("select count(*) as c from live_watchers where status = 'running'").fetchone()["c"]
        im_count = conn.execute("select count(*) as c from im_receivers where status = 'running'").fetchone()["c"]
        failed_count = conn.execute("select count(*) as c from tasks where status = 'failed'").fetchone()["c"]
    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "title": "DouYin_Spider Web UI",
            "auth_status": auth_row["status"] if auth_row else "missing",
            "live_count": live_count,
            "im_count": im_count,
            "failed_count": failed_count,
        },
    )
```

```html
<!-- web/templates/overview.html -->
{% extends "base.html" %}
{% block content %}
<section class="panel">
  <h2>概览</h2>
  <ul>
    <li>登录状态: {{ auth_status }}</li>
    <li>活跃直播监听: {{ live_count }}</li>
    <li>活跃私信接收: {{ im_count }}</li>
    <li>最近失败任务: {{ failed_count }}</li>
  </ul>
</section>
{% endblock %}
```

- [ ] **Step 5: Update the README with the Web UI run path**

````md
## Web UI

```bash
source .venv/bin/activate
uvicorn web.app:create_app --factory --host 127.0.0.1 --port 8000
```

- 仅绑定 `127.0.0.1`
- 页面会直接展示原始异常和 traceback，仅适用于本机调试
- 没有有效 cookie 时，页面链路可验证，业务结果不可验证
````

- [ ] **Step 6: Run the full validation suite**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/web -v
python - <<'PY'
from fastapi.testclient import TestClient
from web.app import create_app

app = create_app({"DB_PATH": "datas/web-ui-smoke.sqlite3"})
client = TestClient(app)
for path in ["/", "/login", "/data-crawl", "/live-monitor", "/private-messages", "/tasks", "/settings"]:
    response = client.get(path)
    print(path, response.status_code)
PY
```

Expected:

- pytest reports all `tests/web` passing
- smoke script prints `200` for every page

- [ ] **Step 7: Commit the final pages and docs**

```bash
git add web/templates/tasks.html web/templates/settings.html web/templates/components/error_panel.html web/routes/pages.py web/routes/actions.py web/static/app.js web/templates/base.html web/templates/overview.html README.md tests/web/test_app_smoke.py
git commit -m "feat: finish local web ui admin surface"
```
