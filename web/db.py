import sqlite3
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_OUTREACH_TEMPLATES = (
    (
        "first_touch_intro",
        "manual",
        "高意向首触达",
        "你好，看到你在关注三角洲上分/组队，这边可以先了解下你的需求，再给你安排合适方案。",
    ),
    (
        "high_intent_followup",
        "followup",
        "高意向二次跟进",
        "如果你方便的话，可以直接告诉我段位、常玩时段和目标，我这边给你整理一个更合适的方案。",
    ),
)

DEFAULT_ACQUISITION_RULES = (
    ("default_source_mode", "comments_first"),
    ("default_precision_mode", "precision"),
    ("default_risk_mode", "safe"),
    ("default_outreach_mode", "manual"),
    ("default_outreach_template_key", "first_touch_intro"),
    ("high_intent_score_threshold", "80"),
)


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
create table if not exists keyword_runs (
    run_id text primary key,
    task_id text,
    keyword text not null,
    status text not null,
    require_num integer not null,
    include_comments integer not null,
    comment_limit integer not null,
    source_mode text not null default 'comments_first',
    precision_mode text not null default 'precision',
    risk_mode text not null default 'safe',
    outreach_mode text not null default 'manual',
    total_count integer not null default 0,
    processed_count integer not null default 0,
    lead_count integer not null default 0,
    high_intent_count integer not null default 0,
    contacted_count integer not null default 0,
    replied_count integer not null default 0,
    summary text not null default '',
    created_at text not null,
    updated_at text not null
);
create table if not exists keyword_leads (
    id integer primary key autoincrement,
    run_id text not null,
    keyword text not null,
    source_type text not null,
    source_aweme_id text,
    source_url text,
    user_id text not null,
    sec_uid text,
    nickname text not null,
    signature text,
    avatar_url text,
    comment_text text not null default '',
    score integer not null default 0,
    grade text not null default 'C',
    score_reasons text not null default '[]',
    matched_signals text not null default '[]',
    review_status text not null default 'new',
    contact_status text not null default 'not_contacted',
    conversion_status text not null default 'new',
    risk_flags text not null default '[]',
    profile_json text not null default '{}',
    raw_payload text not null,
    dedupe_key text not null,
    message_status text not null,
    message_error text not null,
    created_at text not null,
    messaged_at text,
    unique(run_id, dedupe_key)
);
create table if not exists outreach_templates (
    id integer primary key autoincrement,
    template_key text not null unique,
    category text not null,
    title text not null,
    body text not null,
    enabled integer not null default 1
);
create table if not exists outreach_events (
    id integer primary key autoincrement,
    lead_id integer not null,
    mode text not null,
    template_key text,
    status text not null,
    note text not null default '',
    created_at text not null
);
create table if not exists acquisition_rules (
    rule_key text primary key,
    value text not null,
    updated_at text not null
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
    _ensure_column(conn, "keyword_runs", "source_mode", "text not null default 'comments_first'")
    _ensure_column(conn, "keyword_runs", "precision_mode", "text not null default 'precision'")
    _ensure_column(conn, "keyword_runs", "risk_mode", "text not null default 'safe'")
    _ensure_column(conn, "keyword_runs", "outreach_mode", "text not null default 'manual'")
    _ensure_column(conn, "keyword_runs", "total_count", "integer not null default 0")
    _ensure_column(conn, "keyword_runs", "processed_count", "integer not null default 0")
    _ensure_column(conn, "keyword_runs", "high_intent_count", "integer not null default 0")
    _ensure_column(conn, "keyword_runs", "contacted_count", "integer not null default 0")
    _ensure_column(conn, "keyword_runs", "replied_count", "integer not null default 0")
    _ensure_column(conn, "keyword_leads", "comment_text", "text not null default ''")
    _ensure_column(conn, "keyword_leads", "score", "integer not null default 0")
    _ensure_column(conn, "keyword_leads", "grade", "text not null default 'C'")
    _ensure_column(conn, "keyword_leads", "score_reasons", "text not null default '[]'")
    _ensure_column(conn, "keyword_leads", "matched_signals", "text not null default '[]'")
    _ensure_column(conn, "keyword_leads", "review_status", "text not null default 'new'")
    _ensure_column(conn, "keyword_leads", "contact_status", "text not null default 'not_contacted'")
    _ensure_column(conn, "keyword_leads", "conversion_status", "text not null default 'new'")
    _ensure_column(conn, "keyword_leads", "risk_flags", "text not null default '[]'")
    _ensure_column(conn, "keyword_leads", "profile_json", "text not null default '{}'")
    _seed_acquisition_defaults(conn)
    conn.commit()


def list_tables(db_path: Path | str):
    with connect_db(db_path) as conn:
        rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    return [row["name"] for row in rows]


def _ensure_column(conn, table_name, column_name, column_spec):
    rows = conn.execute(f"pragma table_info({table_name})").fetchall()
    existing = {row["name"] for row in rows}
    if column_name in existing:
        return
    conn.execute(f"alter table {table_name} add column {column_name} {column_spec}")


def _seed_acquisition_defaults(conn):
    now = datetime.now(UTC).isoformat()
    conn.executemany(
        "insert or ignore into acquisition_rules(rule_key, value, updated_at) values(?, ?, ?)",
        [(rule_key, value, now) for rule_key, value in DEFAULT_ACQUISITION_RULES],
    )
    conn.executemany(
        "insert or ignore into outreach_templates(template_key, category, title, body, enabled) values(?, ?, ?, ?, 1)",
        DEFAULT_OUTREACH_TEMPLATES,
    )
