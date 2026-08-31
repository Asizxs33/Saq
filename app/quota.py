"""Лимиты обращений к Aqyl и история переписки.

Каждый запрос к агенту стоит реальных денег (вызовы LLM + внешние API),
поэтому обычному пользователю положена суточная квота, а администратору —
безлимит. Счёт ведётся по скользящим 24 часам, а не по календарным суткам:
так лимит нельзя обойти, отправив пачку запросов в 23:59 и ещё пачку в 00:01.

История переписки лежит в той же базе — раньше диалог хранился только в
памяти процесса и терялся при перезапуске. Теперь он привязан к аккаунту,
поэтому одну и ту же историю видно и на сайте, и в мобильном приложении.
"""

import os
from typing import Optional

from app.db import get_connection

# Сколько обращений к агенту в сутки положено обычному пользователю
DAILY_LIMIT = int(os.getenv("USER_DAILY_QUERY_LIMIT", "20"))

ROLE_ADMIN = "admin"
ROLE_USER = "user"


def is_admin(user: dict | None) -> bool:
    return bool(user and user.get("role") == ROLE_ADMIN)


def used_last_24h(user_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM usage_log "
            "WHERE user_id = ? AND created_at > datetime('now', '-1 day')",
            (user_id,),
        ).fetchone()
        return int(row["n"] if row else 0)
    finally:
        conn.close()


def quota_state(user: dict) -> dict:
    """Текущее состояние лимита — отдаётся клиенту, чтобы интерфейс мог
    показать «осталось N запросов» до того, как пользователь упрётся."""
    if is_admin(user):
        return {"unlimited": True, "used": 0, "limit": None, "remaining": None}
    used = used_last_24h(user["id"])
    return {
        "unlimited": False,
        "used": used,
        "limit": DAILY_LIMIT,
        "remaining": max(0, DAILY_LIMIT - used),
    }


def check_and_consume(user: dict, action: str = "chat_query") -> tuple[bool, dict]:
    """Списывает одно обращение. Возвращает (разрешено, состояние лимита).
    Админам ничего не списывает и всегда разрешает."""
    if is_admin(user):
        return True, quota_state(user)

    used = used_last_24h(user["id"])
    if used >= DAILY_LIMIT:
        return False, {
            "unlimited": False,
            "used": used,
            "limit": DAILY_LIMIT,
            "remaining": 0,
        }

    conn = get_connection()
    try:
        conn.execute("INSERT INTO usage_log (user_id, action) VALUES (?, ?)", (user["id"], action))
        conn.commit()
    finally:
        conn.close()

    return True, {
        "unlimited": False,
        "used": used + 1,
        "limit": DAILY_LIMIT,
        "remaining": max(0, DAILY_LIMIT - used - 1),
    }


# ── активность пользователей (для админки) ─────────────────────────────


def record_login(user_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("INSERT INTO login_log (user_id) VALUES (?)", (user_id,))
        conn.commit()
    finally:
        conn.close()


def users_activity(user_ids: list[int]) -> dict[int, dict]:
    """Последний вход, число входов и активность (расследования/чаты/наводки)
    одним запросом на пачку id — чтобы список пользователей в админке не
    делал по 4 запроса на каждую строку таблицы."""
    if not user_ids:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(user_ids))
        logins = conn.execute(
            f"SELECT user_id, COUNT(*) AS n, MAX(created_at) AS last "
            f"FROM login_log WHERE user_id IN ({placeholders}) GROUP BY user_id",
            user_ids,
        ).fetchall()
        investigations = conn.execute(
            f"SELECT user_id, COUNT(*) AS n FROM investigations "
            f"WHERE user_id IN ({placeholders}) GROUP BY user_id",
            user_ids,
        ).fetchall()
        chats = conn.execute(
            f"SELECT user_id, COUNT(*) AS n FROM chat_sessions "
            f"WHERE user_id IN ({placeholders}) GROUP BY user_id",
            user_ids,
        ).fetchall()

        out = {
            uid: {"login_count": 0, "last_login": None, "investigations_count": 0, "chats_count": 0}
            for uid in user_ids
        }
        for r in logins:
            out[r["user_id"]]["login_count"] = r["n"]
            out[r["user_id"]]["last_login"] = r["last"]
        for r in investigations:
            out[r["user_id"]]["investigations_count"] = r["n"]
        for r in chats:
            out[r["user_id"]]["chats_count"] = r["n"]
        return out
    finally:
        conn.close()


def login_history(user_id: int, limit: int = 20) -> list[str]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT created_at FROM login_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [r["created_at"] for r in rows]
    finally:
        conn.close()


# ── история переписки ──────────────────────────────────────────────────


def ensure_session(session_id: str, user_id: int, first_message: str) -> None:
    """Создаёт запись сессии, если её ещё нет. Заголовок — начало первого
    вопроса: по нему пользователь потом найдёт нужный диалог в истории."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,)
            )
        else:
            title = first_message.strip()[:80] or "Без названия"
            conn.execute(
                "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
                (session_id, user_id, title),
            )
        conn.commit()
    finally:
        conn.close()


def save_message(
    session_id: str, role: str, content: str, investigation_id: Optional[int] = None
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, investigation_id) VALUES (?, ?, ?, ?)",
            (session_id, role, content, investigation_id),
        )
        conn.execute("UPDATE chat_sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def list_sessions(user_id: int, limit: int = 50) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT s.id, s.title, s.created_at, s.updated_at, "
            "       (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count "
            "FROM chat_sessions s WHERE s.user_id = ? "
            "ORDER BY s.updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def session_messages(session_id: str, user_id: int, is_admin_user: bool = False) -> list[dict] | None:
    """Сообщения сессии. Возвращает None, если сессия чужая — чтобы вызывающий
    отдал 404 и не подтверждал даже факт её существования."""
    conn = get_connection()
    try:
        owner = conn.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if not owner:
            return None
        if not is_admin_user and owner["user_id"] != user_id:
            return None
        rows = conn.execute(
            "SELECT role, content, investigation_id, created_at FROM chat_messages "
            "WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_session(session_id: str, user_id: int, is_admin_user: bool = False) -> bool:
    conn = get_connection()
    try:
        owner = conn.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if not owner or (not is_admin_user and owner["user_id"] != user_id):
            return False
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        conn.commit()
        return True
    finally:
        conn.close()
