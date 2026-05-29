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
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def list_tables(db_path: Path | str):
    with connect_db(db_path) as conn:
        rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return [row["name"] for row in rows]
