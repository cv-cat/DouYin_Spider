# DouYin_Spider Web UI Design

Date: 2026-05-30
Repo: `/Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github`
Status: Approved for planning, not yet implemented

## 1. Context

This repository currently exposes Douyin capabilities through Python scripts and modules:

- `main.py` for content crawling flows
- `dy_apis/login_api.py` for QR-code and phone login flows
- `dy_live/server.py` for live-room listening and live interactions
- `dy_apis/douyin_recv_msg.py` for private-message receiving
- `dy_apis/douyin_api.py` as the main upstream API wrapper

The repository does not currently contain a usable Web UI. The goal is to add a local-only browser interface without rewriting the existing capability layer.

## 2. Goals

The first Web UI version should:

- run only on `localhost`
- expose the main existing repository capabilities in one place
- support login management, data crawling, live-room monitoring, and private-message operations
- distinguish fast one-shot actions from long-running background tasks
- persist task state and listener state across page refreshes
- favor debugging visibility over end-user polish

## 3. Constraints

- Keep the existing Python capability modules as the source of truth.
- Do not refactor unrelated crawler logic.
- Do not create a public-facing product surface.
- Default to local debugging behavior because the UI is explicitly limited to `localhost`.
- If this UI is later exposed to LAN or public access, raw exception exposure must be removed before release.

## 4. Options Considered

### Option A: `FastAPI + Jinja2 + HTMX + SSE + SQLite`

Pros:

- minimal frontend complexity
- Python-native and easy to integrate with the existing repository
- server-rendered pages stay simple
- SSE is enough for task state, login polling, live events, and message updates
- SQLite is sufficient for local persistence

Cons:

- less interactive than a full SPA
- background runtime management still needs careful design

### Option B: `FastAPI + Jinja2` with mostly in-memory state

Pros:

- lowest initial implementation cost
- fewer persistence concerns

Cons:

- loses task state and listener state on restart
- weaker debugging history
- poorer fit for long-running live and IM processes

### Option C: separate frontend SPA plus backend API

Pros:

- strongest UI flexibility
- easier to scale into a richer product later

Cons:

- introduces substantial frontend overhead
- unnecessary for a local-only admin tool
- highest integration and maintenance cost

### Chosen Option

Option A is the chosen design. It is the smallest approach that still supports persistence, real-time updates, and long-running process control.

## 5. V1 Scope

### Included Pages

- `Overview`
- `Login Center`
- `Data Crawl`
- `Live Monitor`
- `Private Messages`
- `Tasks & Logs`
- `Settings`

### Page Responsibilities

#### Overview

- show current login/session summary
- show active live listeners and IM receivers
- show recent tasks and recent failures

#### Login Center

- display cookie status
- save manual cookies
- trigger QR-code login flow
- trigger phone-code login flow
- show login task progress and result

#### Data Crawl

- perform user/profile/content lookup
- fetch comments, replies, followers, following, favorites, collections, notices, and search results
- merge interaction actions into this page instead of creating a separate interaction module
- allow one-shot operations directly on the page
- send batch fetch/export operations to background tasks

#### Live Monitor

- query room metadata
- send live chat messages
- send live like actions
- start and stop room listeners as background tasks
- display incoming live events in real time

#### Private Messages

- list conversations
- open conversation details
- create a conversation
- send messages
- start and stop the realtime receiver as a background runtime
- display incoming messages in real time

#### Tasks & Logs

- show all task records
- filter by status and type
- inspect task logs and errors
- cancel tasks when supported

#### Settings

- local app settings
- storage path settings
- port and runtime settings
- debug display toggles if needed later

### Explicitly Out of Scope for V1

- multi-user access
- LAN/public deployment hardening
- fine-grained permission control
- redesigning upstream crawler APIs
- mobile-responsive product-quality UI

## 6. Interaction Rules

### Foreground Actions

These execute immediately in the request/response flow:

- cookie validation and manual cookie save
- single-item detail lookup
- list-query previews with small result sets
- live room info lookup
- send live chat
- send live like
- list conversations
- open conversation detail
- create conversation
- send private message

### Background Actions

These always run as managed tasks:

- QR-code login polling
- phone login initialization and verification loops
- batch crawl/export jobs
- live-room listener start/stop lifecycle
- private-message realtime receiver lifecycle
- any loop, retry loop, or continuously running process

## 7. Architecture

The Web UI should be added as a thin layer on top of the current repository.

### Proposed Structure

- `web/app.py`
- `web/routes/`
- `web/templates/`
- `web/static/`
- `web/services/`
- `web/tasks/`
- `web/db.py`
- `web/models.py`

### Responsibilities

#### `web/routes/`

- HTTP endpoints
- page rendering endpoints
- SSE endpoints
- form and action endpoints

#### `web/services/`

Adapters over existing modules, not replacements.

- `login_service.py` wraps `DYLoginApi`
- `crawl_service.py` wraps `Data_Spider` and `DouyinAPI`
- `live_service.py` wraps `DouyinLive`
- `im_service.py` wraps `DouyinRecvMsg`
- `settings_service.py` manages local configuration storage

#### `web/tasks/`

- task manager
- task execution registry
- runtime instance registry for listeners/receivers
- thread or event-loop bridging for blocking and async flows

#### `web/db.py` and `web/models.py`

- SQLite connection setup
- schema initialization
- simple persistence models for local state

## 8. State and Persistence

SQLite is the persistence layer for the local UI.

### Proposed Tables

- `settings`
- `auth_sessions`
- `tasks`
- `task_logs`
- `live_watchers`
- `im_receivers`
- `event_feed`

### Table Purpose

#### `settings`

- local UI configuration
- selected port
- filesystem options

#### `auth_sessions`

- current cookie snapshot
- login type
- update time
- validity check result

#### `tasks`

- task id
- task type
- status
- start/end timestamps
- summary payload
- error summary

#### `task_logs`

- task log lines
- structured progress events
- traceback text when failures occur

#### `live_watchers`

- room id
- runtime status
- start time
- stop time
- last error

#### `im_receivers`

- receiver status
- start time
- stop time
- last error

#### `event_feed`

- unified live events and IM events for UI display
- recent event history for page refresh recovery

## 9. Runtime Model

The current repository mixes blocking requests, Playwright flows, async flows, and long-lived sockets. The UI runtime should not force a full rewrite into one concurrency model.

### Execution Strategy

- short synchronous operations run directly inside request handlers or thin service wrappers
- blocking long-running tasks run in managed background threads
- async-only flows get a dedicated managed event loop owned by the task layer
- live listeners and IM receivers are tracked both in SQLite and in an in-memory runtime registry

### Restart Expectations

- completed task history persists
- active runtime records persist as state records
- after process restart, the UI should show previous runtime state as stopped or stale until explicitly restarted
- V1 does not attempt automatic listener resurrection on restart

## 10. Realtime UI Updates

The UI will use:

- `Jinja2` for initial page rendering
- `HTMX` for lightweight interaction and partial updates
- `SSE` for task progress, login polling state, live events, IM events, and status panels

This avoids a full frontend framework while still allowing live updates where they matter.

## 11. Error Handling

This UI is intentionally designed for local debugging on `localhost`, not for exposure to other users.

### Error Visibility Rules

- page-level failures may show both a readable label and the raw exception text
- background task failures should expose exception type, message, and full traceback in the task detail view
- live and IM runtime failures should expose the latest raw disconnect or runtime exception text in the page status area

### Risk Note

If the UI is ever moved beyond `localhost`, this raw exception behavior must be removed before doing so.

## 12. Validation Strategy

Validation is required before calling the UI usable.

### Layer 1: startup validation

- app import succeeds
- database initialization succeeds
- HTTP server starts successfully

### Layer 2: page smoke validation

- `Overview` loads
- `Login Center` loads
- `Data Crawl` loads
- `Live Monitor` loads
- `Private Messages` loads
- `Tasks & Logs` loads
- `Settings` loads

### Layer 3: task-chain validation

- create task
- task status changes over time
- task logs append
- UI reflects status/log changes live

### Layer 4: capability integration validation

- at least one short action must call a real existing service wrapper
- at least one background action must call a real existing service wrapper
- if valid cookies are unavailable, validation must be reported as transport-chain verified but business-result unverified

## 13. Delivery Sequence

Implementation should be staged in this order:

1. bootstrap the web app shell and SQLite schema
2. build the shared layout, navigation, and task/event infrastructure
3. wire `Login Center`
4. wire `Data Crawl`
5. wire `Live Monitor`
6. wire `Private Messages`
7. finish `Tasks & Logs` and `Settings`
8. run smoke and integration validation

## 14. Non-Goals

This design does not attempt to:

- solve upstream Douyin API stability
- remove existing repository limitations around cookies or signatures
- harden security for external access
- redesign repository business logic
- support distributed workers or Redis

## 15. Final Design Summary

Build a local-only Web UI using `FastAPI + Jinja2 + HTMX + SSE + SQLite`, keep the current crawler modules as the capability layer, split fast actions from background runtimes, persist task and listener state locally, and expose raw exception details because the tool is intended for local debugging on `localhost`.
