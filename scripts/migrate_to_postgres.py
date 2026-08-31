"""Разовый перенос данных из локального SQLite (data/phylax.sqlite3) в
общий Postgres, заданный через AUTH_DB_URL/DATABASE_URL.

Идемпотентно: INSERT ... ON CONFLICT (id) DO NOTHING, поэтому повторный
запуск ничего не сломает и не задвоит строки. Порядок таблиц соблюдает
внешние ключи (users -> investigations -> всё остальное).

Запуск: python scripts/migrate_to_postgres.py
"""

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import psycopg

PG_URL = (os.getenv("DATABASE_URL") or os.getenv("AUTH_DB_URL") or "").strip()
if not PG_URL:
    raise SystemExit("AUTH_DB_URL/DATABASE_URL не задан — мигрировать некуда")

SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "phylax.sqlite3"

# (sqlite_table, pg_table, columns) — porядок важен из-за FOREIGN KEY
TABLES = [
    ("users", "users", ["id", "email", "password_hash", "role", "created_at"]),
    ("chat_sessions", "chat_sessions", ["id", "user_id", "title", "created_at", "updated_at"]),
    (
        "investigations",
        "investigations",
        ["id", "query", "query_type", "risk_score", "risk_flags", "connectors_run", "created_at", "user_id"],
    ),
    (
        "chat_messages",
        "chat_messages",
        ["id", "session_id", "role", "content", "investigation_id", "created_at"],
    ),
    ("usage_log", "usage_log", ["id", "user_id", "action", "created_at"]),
    ("login_log", "login_log", ["id", "user_id", "created_at"]),
    ("entities", "saq_entities", ["id", "investigation_id", "kind", "value", "value_lower"]),
    (
        "tips",
        "tips",
        ["id", "target", "note", "contact", "status", "risk_score", "investigation_id", "user_id", "created_at"],
    ),
    (
        "candidate_leads",
        "candidate_leads",
        ["id", "domain", "matched_markers", "status", "investigation_id", "first_seen"],
    ),
]


def main():
    sconn = sqlite3.connect(SQLITE_PATH)
    sconn.row_factory = sqlite3.Row
    pconn = psycopg.connect(PG_URL, autocommit=True)

    # investigations.user_id — колонка появилась миграцией позже, в старых
    # локальных базах её может не быть
    existing_cols = {r[1] for r in sconn.execute("PRAGMA table_info(investigations)").fetchall()}

    for sqlite_table, pg_table, cols in TABLES:
        use_cols = [c for c in cols if sqlite_table != "investigations" or c != "user_id" or "user_id" in existing_cols]
        placeholders = ", ".join(f"%s" for _ in use_cols)
        col_list = ", ".join(use_cols)

        try:
            rows = sconn.execute(f"SELECT {col_list} FROM {sqlite_table}").fetchall()
        except sqlite3.OperationalError as e:
            print(f"skip {sqlite_table}: {e}")
            continue

        if not rows:
            print(f"{sqlite_table}: 0 rows, skip")
            continue

        # пакетами по 300 строк одним INSERT — построчно через сеть до Neon
        # 2300+ строк идут минутами, пакетом — секунды
        BATCH = 300
        inserted = 0
        all_values = [tuple(r[c] for c in use_cols) for r in rows]
        for i in range(0, len(all_values), BATCH):
            chunk = all_values[i : i + BATCH]
            row_ph = "(" + placeholders + ")"
            values_sql = ", ".join([row_ph] * len(chunk))
            flat_params = [v for row in chunk for v in row]
            cur = pconn.execute(
                f"INSERT INTO {pg_table} ({col_list}) VALUES {values_sql} "
                f"ON CONFLICT (id) DO NOTHING",
                flat_params,
            )
            inserted += cur.rowcount
        print(f"{sqlite_table} -> {pg_table}: {inserted}/{len(rows)} новых строк")

        # синхронизируем автоинкремент-последовательность, иначе следующий
        # INSERT без явного id (обычная работа приложения) начнёт с 1 и
        # столкнётся с уже перенесёнными id. chat_sessions.id — TEXT (UUID
        # с клиента), там нет serial-последовательности вообще — пропускаем.
        if pg_table != "chat_sessions":
            pconn.execute(
                f"SELECT setval(pg_get_serial_sequence('{pg_table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {pg_table}), 1))"
            )

    sconn.close()
    pconn.close()
    print("done")


if __name__ == "__main__":
    main()
