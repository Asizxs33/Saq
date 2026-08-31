"""Находки партнёрского мобильного приложения — ТОЛЬКО ЧТЕНИЕ.

База Postgres общая: наши таблицы и таблицы мобильного приложения лежат рядом
в одной схеме. Приложение ловит опасный контент в соцсетях (TikTok, Instagram,
YouTube) — автор, текст поста, категория схемы и оценка риска. Логично показывать
это в общем списке находок SAQ рядом с наводками с сайта и от Guardian.

Жёсткие правила этого модуля:

1. Только SELECT. Ни одного INSERT/UPDATE/DELETE — чужие данные мы не трогаем,
   их пишет и модерирует их приложение.
2. Схема чужая и может измениться без предупреждения. Любая ошибка (нет таблицы,
   переименовали колонку, поменяли тип) не должна ронять админку SAQ — поэтому
   каждый запрос обёрнут и при сбое возвращается пустой список.
3. Ничего не кэшируем и не копируем к себе: показываем то, что там сейчас.
"""

import json
import logging
from typing import Any

from app.db import get_connection

log = logging.getLogger("mobile_feed")

# записи с этой пометкой в имени автора — тестовые прогоны их приложения
_TEST_MARK = "[SAQ TEST]"


def _loads(raw: Any) -> list:
    """reason_codes_json и подобные приходят строкой; иногда уже списком."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def list_content_findings(limit: int = 100, include_tests: bool = False) -> list[dict]:
    """Контент, помеченный мобильным приложением как рискованный.

    guard_content_records — самая содержательная таблица партнёра: площадка,
    автор, текст, категория схемы, оценка риска и решение пользователя.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, platform, category, author_name, description,
                   risk_score, risk_level, reason_codes_json, signal_codes_json,
                   detected_via_json, view_count_label, blocked, user_decision,
                   observed_at, created_at
            FROM guard_content_records
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except Exception as exc:
        # чужая схема могла измениться — это не наша авария
        log.warning("mobile_feed: guard_content_records недоступна (%s)", exc)
        return []
    finally:
        conn.close()

    out = []
    for r in rows:
        author = r["author_name"] or ""
        is_test = _TEST_MARK in author
        if is_test and not include_tests:
            continue
        out.append(
            {
                "id": r["id"],
                "kind": "content",
                "platform": r["platform"],
                "category": r["category"],
                "author": author.replace(_TEST_MARK, "").strip() or None,
                "text": r["description"],
                "risk_score": r["risk_score"],
                "risk_level": r["risk_level"],
                "reasons": _loads(r["reason_codes_json"]) + _loads(r["signal_codes_json"]),
                "detected_via": _loads(r["detected_via_json"]),
                "views": r["view_count_label"],
                "blocked": bool(r["blocked"]),
                "user_decision": r["user_decision"],
                "created_at": r["observed_at"] or r["created_at"],
                "is_test": is_test,
            }
        )
    return out


def list_signal_findings(limit: int = 100, include_tests: bool = False) -> list[dict]:
    """Сырые сигналы приложения (таблица findings): что сработало на устройстве."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, source_platform, risk_score, risk_level, primary_category,
                   short_explanation, url, status, test_record, created_at
            FROM findings
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except Exception as exc:
        log.warning("mobile_feed: findings недоступна (%s)", exc)
        return []
    finally:
        conn.close()

    out = []
    for r in rows:
        is_test = bool(r["test_record"])
        if is_test and not include_tests:
            continue
        out.append(
            {
                "id": r["id"],
                "kind": "signal",
                "platform": r["source_platform"],
                "category": r["primary_category"],
                "author": None,
                "text": r["short_explanation"],
                "risk_score": r["risk_score"],
                "risk_level": r["risk_level"],
                "reasons": [],
                "detected_via": [],
                "views": None,
                "blocked": False,
                "user_decision": r["status"],
                "url": r["url"],
                "created_at": r["created_at"],
                "is_test": is_test,
            }
        )
    return out


def list_findings(limit: int = 100, include_tests: bool = False) -> list[dict]:
    """Общий список находок мобильного приложения, свежие сверху."""
    items = list_content_findings(limit, include_tests) + list_signal_findings(limit, include_tests)
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return items[:limit]


def stats() -> dict:
    """Сводка для админ-панели. При недоступности партнёрских таблиц — нули."""
    conn = get_connection()
    res = {"content": 0, "signals": 0, "high_risk": 0, "blocked": 0, "available": False}
    try:
        res["content"] = conn.execute("SELECT COUNT(*) FROM guard_content_records").fetchone()[0]
        res["signals"] = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        res["high_risk"] = conn.execute(
            "SELECT COUNT(*) FROM guard_content_records WHERE risk_score >= 60"
        ).fetchone()[0]
        res["blocked"] = conn.execute(
            "SELECT COUNT(*) FROM guard_content_records WHERE blocked = 1"
        ).fetchone()[0]
        res["available"] = True
    except Exception as exc:
        log.warning("mobile_feed: сводка недоступна (%s)", exc)
    finally:
        conn.close()
    return res
