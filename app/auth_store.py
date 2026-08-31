"""Хранилище пользователей — единственная часть проекта, которая может
жить в общей облачной базе, а не локально на каждом ПК.

Идея: у тебя и у друга — два независимых сервера SAQ (каждый со своими
расследованиями, watchlist, чатом Aqyl — всё локально, как обычно). Но
если оба сервера указывают на ОДИН И ТОТ ЖЕ Postgres через AUTH_DB_URL,
аккаунт (email/пароль), заведённый в одном месте, узнаётся и в другом —
серверы остаются раздельными, общая только таблица пользователей.

Без AUTH_DB_URL всё работает как обычная локальная разработка — таблица
users живёт в той же SQLite (data/phylax.sqlite3), что и всё остальное,
никакой сети и внешних зависимостей не требуется.
"""

import os
from typing import Optional

from app.db import get_connection as get_sqlite_connection

AUTH_DB_URL = os.getenv("AUTH_DB_URL", "").strip()

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
"""


_pg_pool = None


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        from psycopg_pool import ConnectionPool

        _pg_pool = ConnectionPool(
            AUTH_DB_URL,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True},
            # см. тот же комментарий в app/db.py: Neon рвёт простаивающие
            # соединения, и без check пул отдаёт мёртвое — логин падал с 500
            # после нескольких минут бездействия
            check=ConnectionPool.check_connection,
            max_idle=120,
        )
    return _pg_pool


def _pg_connect():
    # get_current_user() дёргает get_user_by_id() на КАЖДЫЙ авторизованный
    # запрос — открывать новое TCP+TLS соединение до Neon на каждый чих
    # означало заметные тормоза интерфейса. Пул держит несколько тёплых
    # соединений и просто выдаёт/забирает их обратно.
    return _get_pg_pool().getconn()


def _pg_release(conn) -> None:
    _get_pg_pool().putconn(conn)


def init_users_table() -> None:
    """Вызывается один раз при старте бэкенда."""
    if not AUTH_DB_URL:
        return  # локальная SQLite-таблица users уже создаётся в app.db.init_db()

    conn = _pg_connect()
    try:
        conn.execute(_PG_SCHEMA)
    finally:
        _pg_release(conn)


def create_user(email: str, password_hash: str) -> int:
    email = email.strip().lower()

    if AUTH_DB_URL:
        conn = _pg_connect()
        try:
            row = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (email, password_hash),
            ).fetchone()
            return row[0]
        finally:
            _pg_release(conn)

    conn = get_sqlite_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_email(email: str) -> Optional[dict]:
    email = email.strip().lower()

    if AUTH_DB_URL:
        conn = _pg_connect()
        try:
            row = conn.execute(
                "SELECT id, email, password_hash, role, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') "
                "FROM users WHERE email = %s",
                (email,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0], "email": row[1], "password_hash": row[2],
                "role": row[3], "created_at": str(row[4]),
            }
        finally:
            _pg_release(conn)

    conn = get_sqlite_connection()
    try:
        row = conn.execute(
            "SELECT id, email, password_hash, role, created_at FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    if AUTH_DB_URL:
        conn = _pg_connect()
        try:
            row = conn.execute(
                "SELECT id, email, role, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') "
                "FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return {"id": row[0], "email": row[1], "role": row[2], "created_at": str(row[3])}
        finally:
            _pg_release(conn)

    conn = get_sqlite_connection()
    try:
        row = conn.execute(
            "SELECT id, email, role, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users(limit: int = 200) -> list[dict]:
    """Для админ-панели: кто зарегистрирован и с какой ролью."""
    if AUTH_DB_URL:
        conn = _pg_connect()
        try:
            rows = conn.execute(
                "SELECT id, email, role, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') "
                "FROM users ORDER BY id DESC LIMIT %s",
                (limit,),
            ).fetchall()
            return [
                {"id": r[0], "email": r[1], "role": r[2], "created_at": str(r[3])} for r in rows
            ]
        finally:
            _pg_release(conn)

    conn = get_sqlite_connection()
    try:
        rows = conn.execute(
            "SELECT id, email, role, created_at FROM users ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_role(user_id: int, role: str) -> bool:
    if AUTH_DB_URL:
        conn = _pg_connect()
        try:
            cur = conn.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
            return cur.rowcount > 0
        finally:
            _pg_release(conn)

    conn = get_sqlite_connection()
    try:
        cur = conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
