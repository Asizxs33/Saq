"""Хранилище данных SAQ: расследования, чат, наводки, входы и т.д.

По умолчанию — локальный SQLite-файл (data/phylax.sqlite3), без сети и
внешних зависимостей. Если задать DATABASE_URL (или AUTH_DB_URL — тот же
Postgres, что уже используется для общих аккаунтов в auth_store.py), ВСЕ
данные переезжают в этот Postgres — так сайт, друг с мобильным
приложением и любой другой сервер SAQ видят одну и ту же базу.

Таблица users сюда намеренно НЕ входит — ею полностью владеет
auth_store.py (он уже умеет Postgres и создаёт users первым, до того как
остальные таблицы попытаются сослаться на неё через FOREIGN KEY).

Совместимость со старым кодом: registry.py/quota.py/main.py написаны под
sqlite3 (плейсхолдеры "?", conn.execute(...).lastrowid, dict(row) на
результате). Чтобы не переписывать SQL в дюжине мест, PgConnection ниже
эмулирует этот интерфейс поверх psycopg — конвертирует "?" в "%s",
подставляет Postgres-эквивалент datetime('now', ...) и сама подставляет
RETURNING id для INSERT, чтобы .lastrowid работал как в sqlite3.
"""

import os
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "phylax.sqlite3"

PG_URL = (os.getenv("DATABASE_URL") or os.getenv("AUTH_DB_URL") or "").strip()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- История переписки с Aqyl. Раньше диалог жил только в памяти процесса и
-- пропадал при перезапуске бэкенда; теперь он привязан к аккаунту, так что
-- одну и ту же историю видно и на сайте, и в мобильном приложении.
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    investigation_id INTEGER REFERENCES investigations(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);

-- Учёт расхода лимита: бесплатному пользователю — N запросов в сутки,
-- админу — без ограничений. Пишем каждое обращение к агенту.
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_usage_user_time ON usage_log(user_id, created_at);

-- Когда пользователь заходил — для админки ("последний вход", история
-- входов). Пишем при каждом успешном /auth/login и /auth/register.
CREATE TABLE IF NOT EXISTS login_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_login_log_user_time ON login_log(user_id, created_at);

CREATE TABLE IF NOT EXISTS investigations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    query_type TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    risk_flags TEXT NOT NULL,
    connectors_run TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saq_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id INTEGER NOT NULL REFERENCES investigations(id),
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    value_lower TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_value_lower ON saq_entities(value_lower);

CREATE TABLE IF NOT EXISTS tips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target TEXT NOT NULL,
    note TEXT NOT NULL,
    contact TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    risk_score INTEGER,
    investigation_id INTEGER REFERENCES investigations(id),
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT NOT NULL DEFAULT 'web'
);

-- domains auto-surfaced by the CertStream watcher (new-domain marker match),
-- queued here for the batch runner to feed through the normal investigate()
-- pipeline — never trusted or scored on the marker match alone.
CREATE TABLE IF NOT EXISTS candidate_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL UNIQUE,
    matched_markers TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    investigation_id INTEGER REFERENCES investigations(id),
    first_seen TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_candidate_leads_status ON candidate_leads(status);

-- Переключатели, которые нужно менять без перезапуска сервера (например,
-- "включить/выключить автомониторинг CertStream" из админки). Простое
-- key-value хранилище — заводить отдельную таблицу под каждый флаг избыточно.
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# та же схема, но: без users (им владеет auth_store.py), Postgres-синтаксис
# автоинкремента, и в порядке, где таблицы не ссылаются вперёд — Postgres,
# в отличие от SQLite, проверяет существование FK-таблицы сразу при CREATE.
PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    query_type TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    risk_flags TEXT NOT NULL,
    connectors_run TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title TEXT,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    updated_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    investigation_id INTEGER REFERENCES investigations(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);

CREATE TABLE IF NOT EXISTS usage_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_usage_user_time ON usage_log(user_id, created_at);

CREATE TABLE IF NOT EXISTS login_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_login_log_user_time ON login_log(user_id, created_at);

CREATE TABLE IF NOT EXISTS saq_entities (
    id SERIAL PRIMARY KEY,
    investigation_id INTEGER NOT NULL REFERENCES investigations(id),
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    value_lower TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_value_lower ON saq_entities(value_lower);

CREATE TABLE IF NOT EXISTS tips (
    id SERIAL PRIMARY KEY,
    target TEXT NOT NULL,
    note TEXT NOT NULL,
    contact TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    risk_score INTEGER,
    investigation_id INTEGER REFERENCES investigations(id),
    user_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')),
    source TEXT NOT NULL DEFAULT 'web'
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS candidate_leads (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    matched_markers TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    investigation_id INTEGER REFERENCES investigations(id),
    first_seen TEXT NOT NULL DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_candidate_leads_status ON candidate_leads(status);
"""

_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.IGNORECASE)
# таблицы без числового id (app_settings — PK это key) — им нельзя молча
# дописывать "RETURNING id", Postgres упадёт с "column id does not exist"
_NO_ID_TABLES = {"app_settings"}
# datetime('now') / datetime('now', '-1 day') → Postgres-эквивалент, тем же
# текстовым форматом, что отдаёт SQLite (YYYY-MM-DD HH:MM:SS, без таймзоны)
# — чтобы фронтенд (везде парсит как "date.replace(' ','T')+'Z'") не заметил
# разницы между локальной SQLite и общим Postgres.
_DATETIME_NOW_RE = re.compile(
    r"datetime\(\s*'now'\s*(?:,\s*'([+-]?\d+)\s+(day|hour|minute)s?'\s*)?\)", re.IGNORECASE
)


def _pg_now_expr(offset: str | None, unit: str | None) -> str:
    base = "to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')"
    if offset is None:
        return base
    return f"to_char((now() AT TIME ZONE 'utc') + interval '{offset} {unit}', 'YYYY-MM-DD HH24:MI:SS')"


_INSERT_OR_IGNORE_RE = re.compile(r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)


def _translate_sql(sql: str) -> str:
    sql = _DATETIME_NOW_RE.sub(lambda m: _pg_now_expr(m.group(1), m.group(2)), sql)
    # "INSERT OR IGNORE" — диалект SQLite; в Postgres то же самое (не падать
    # на конфликте UNIQUE/PK, просто ничего не делать) выражается через
    # ON CONFLICT DO NOTHING, приклеенное в конец INSERT-запроса.
    has_or_ignore = bool(_INSERT_OR_IGNORE_RE.search(sql))
    sql = _INSERT_OR_IGNORE_RE.sub("INSERT INTO", sql)
    if has_or_ignore:
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    sql = sql.replace("?", "%s")
    return sql


class _Row(dict):
    """sqlite3.Row поддерживает и row["col"], и row[0] (по позиции) — код
    в main.py/registry.py местами использует позиционный доступ (например
    row[0] для однострочного COUNT(*)). Обычный dict от psycopg этого не
    умеет (KeyError: 0), поэтому здесь int-ключ отдельно резолвится по
    порядку колонок."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    # description is None для запросов без набора колонок в ответе — обычный
    # UPDATE/INSERT без RETURNING (например settings.set_setting()'s UPSERT).
    # psycopg всё равно запрашивает row_factory заранее, до того как что-то
    # реально попытаются fetch'нуть — падать тут нельзя, просто нечего мапить.
    if cursor.description is None:
        return lambda values: _Row()

    cols = [c.name for c in cursor.description]

    def make_row(values):
        return _Row(zip(cols, values))

    return make_row


class _PgCursor:
    """Достаточно sqlite3.Cursor-совместимый враппер: .lastrowid работает
    через автоматический RETURNING id на INSERT, строки — _Row (dict с
    поддержкой и по имени, и по позиции), так что row["x"], row[0] и
    dict(row) работают как в sqlite3.Row."""

    def __init__(self, raw_cursor, lastrowid: int | None):
        self._cur = raw_cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount


class PgConnection:
    def __init__(self, raw, pool=None):
        self._raw = raw
        self._pool = pool

    def execute(self, sql: str, params: tuple = ()) -> _PgCursor:
        translated = _translate_sql(sql)
        lastrowid = None
        m = _INSERT_RE.match(sql)
        if m and m.group(1).lower() in _NO_ID_TABLES:
            m = None
        if m and "returning" not in sql.lower():
            translated = translated.rstrip().rstrip(";") + " RETURNING id"
        cur = self._raw.cursor(row_factory=_row_factory)
        cur.execute(translated, params)
        if m and "returning" not in sql.lower():
            row = cur.fetchone()
            lastrowid = row["id"] if row else None
        return _PgCursor(cur, lastrowid)

    def executemany(self, sql: str, seq_of_params) -> None:
        translated = _translate_sql(sql)
        cur = self._raw.cursor()
        cur.executemany(translated, list(seq_of_params))

    def executescript(self, script: str) -> None:
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._raw.execute(stmt)

    def commit(self) -> None:
        pass  # соединение в autocommit — каждый execute() уже закоммичен

    def close(self) -> None:
        # Весь остальной код открывает/закрывает "соединение" на каждый
        # запрос (как sqlite3 — дёшево, локальный файл). Для Postgres через
        # интернет так же делать нельзя: TCP+TLS-рукопожатие до Neon на
        # каждый чих — вот откуда тормоза, которые заметны в интерфейсе.
        # Поэтому здесь conn.close() не рвёт соединение, а просто возвращает
        # его в пул (_pg_pool ниже) — реально закрывается только при
        # выключении бэкенда.
        if self._pool is not None:
            self._pool.putconn(self._raw)
        else:
            self._raw.close()


_pg_pool = None


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        from psycopg_pool import ConnectionPool

        _pg_pool = ConnectionPool(
            PG_URL,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True},
            # Neon (как и любой serverless-Postgres) закрывает простаивающие
            # соединения со своей стороны. Без этих двух опций пул спокойно
            # отдаёт уже мёртвое соединение, и запрос падает с
            # "server closed the connection unexpectedly" — проверено вживую,
            # логин переставал работать после паузы в несколько минут.
            # check пингует соединение перед выдачей и молча переоткрывает,
            # max_idle не даёт им доживать до серверного таймаута.
            check=ConnectionPool.check_connection,
            max_idle=120,
        )
    return _pg_pool


def get_connection():
    if PG_URL:
        pool = _get_pg_pool()
        return PgConnection(pool.getconn(), pool)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(PG_SCHEMA if PG_URL else SCHEMA)
        # миграции для баз, созданных до появления этих колонок — на Postgres
        # ADD COLUMN IF NOT EXISTS есть нативно, но try/except работает для
        # обеих СУБД одинаково, поэтому оставляем один и тот же код
        for stmt in (
            "ALTER TABLE tips ADD COLUMN risk_score INTEGER",
            "ALTER TABLE tips ADD COLUMN investigation_id INTEGER REFERENCES investigations(id)",
            "ALTER TABLE tips ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE investigations ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE tips ADD COLUMN source TEXT NOT NULL DEFAULT 'web'",
        ):
            try:
                conn.execute(stmt)
            except Exception:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()
