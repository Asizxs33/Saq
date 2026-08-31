"""Переключатели рантайма — то, что админ должен уметь включать/выключать
без перезапуска сервера (например, автомониторинг CertStream).

ENABLE_CERTSTREAM_WATCHER в .env остаётся главным рубильником: если он
выключен, фоновые задачи вообще не стартуют при запуске (см. main.py) —
это осознанная защита от того, чтобы клонированный репозиторий молча начал
открывать вебсокеты и тратить квоту API. Настройка отсюда — это "пауза"
поверх уже запущенного мониторинга, включаемая/выключаемая на лету.
"""

from app.db import get_connection

DEFAULTS = {
    "certstream_paused": "false",
}


def get_setting(key: str, default: str | None = None) -> str:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row:
            return row["value"]
        return default if default is not None else DEFAULTS.get(key, "")
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    try:
        # UPSERT — синтаксис одинаков и в SQLite (3.24+), и в Postgres.
        # datetime('now'), а не CURRENT_TIMESTAMP — последний в Postgres
        # вернул бы timestamptz, а колонка TEXT (see db.py._translate_sql
        # для того, как datetime('now') превращается в Postgres-эквивалент)
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def is_certstream_paused() -> bool:
    return get_setting("certstream_paused", "false") == "true"
