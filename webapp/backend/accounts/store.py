"""SQLite 账号存储。同步 sqlite3,handler 用 asyncio.to_thread 调用。"""
import json
import sqlite3
from datetime import datetime
from typing import Optional

from webapp.backend import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    cookies_json TEXT NOT NULL,
    ticket TEXT,
    ts_sign TEXT,
    client_cert TEXT,
    private_key TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    status TEXT DEFAULT 'unknown'
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    config.ensure_dirs()
    with _conn() as c:
        c.executescript(SCHEMA)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_account(label: str, cookies: dict, ticket: str = "", ts_sign: str = "",
                   client_cert: str = "", private_key: str = "", status: str = "valid") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO accounts(label, cookies_json, ticket, ts_sign, client_cert, private_key, created_at, status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (label, json.dumps(cookies, ensure_ascii=False), ticket or None, ts_sign or None,
             client_cert or None, private_key or None, _now(), status),
        )
        return cur.lastrowid


def update_account(account_id: int, **fields):
    allowed = {"label", "cookies_json", "ticket", "ts_sign", "client_cert",
               "private_key", "last_used_at", "status"}
    sets = [f"{k}=?" for k in fields if k in allowed]
    vals = [v for k, v in fields.items() if k in allowed]
    if not sets:
        return
    vals.append(account_id)
    with _conn() as c:
        c.execute(f"UPDATE accounts SET {', '.join(sets)} WHERE id=?", vals)


def delete_account(account_id: int):
    with _conn() as c:
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))


def list_accounts() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def get_account(account_id: int) -> Optional[dict]:
    with _conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        return dict(r) if r else None


def set_active(account_id: int):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('active_account_id', ?)",
                  (str(account_id),))


def get_active_id() -> Optional[int]:
    with _conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key='active_account_id'").fetchone()
        return int(r["value"]) if r else None


def touch(account_id: int):
    update_account(account_id, last_used_at=_now())
