"""Автопроверка наводок сообщества.

Каждая наводка (POST /tips) сразу уходит в фоновую задачу: полный
investigate() по объекту, статус и risk score пишутся обратно в наводку —
лента сообщества показывает вердикт Aqyl всем.

Петля самообучения: подтверждённые объекты (score >= CONFIRM_THRESHOLD)
добавляются в data/blacklists/community.json. Этот файл читает тот же
LocalBlacklistConnector, что и списки регуляторов, — значит каждая
подтверждённая наводка немедленно усиливает ВСЕ будущие проверки: следующий
пользователь, спросивший про тот же объект, получит совпадение с чёрным
списком (+50 к скору) даже если внешние источники молчат.

Важно: наводка проверяется ДО добавления в список, поэтому сама себе
скор не накручивает.
"""

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from app import registry
from app.orchestrator import investigate

logger = logging.getLogger("tips_worker")

CONFIRM_THRESHOLD = 40
COMMUNITY_BLACKLIST = Path(__file__).resolve().parent.parent / "data" / "blacklists" / "community.json"

# keep strong references so tasks aren't garbage-collected mid-flight
_tasks: set[asyncio.Task] = set()


def reschedule_pending_tips() -> None:
    """Called on startup: tips submitted while the backend was down (or
    before auto-checking existed) would otherwise stay 'pending' forever."""
    pending = [t for t in registry.list_tips(limit=200) if t["status"] == "pending"]
    for t in pending:
        schedule_tip_check(t["id"], t["target"])
    if pending:
        logger.info("rescheduled %s pending tip(s) for auto-check", len(pending))


def schedule_tip_check(tip_id: int, target: str) -> None:
    task = asyncio.create_task(_process_tip(tip_id, target))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _process_tip(tip_id: int, target: str) -> None:
    try:
        investigation_id, _qtype, _run, _results, score, _flags, _summary, _rec = await investigate(
            target, None, False
        )
    except Exception:
        logger.exception("tip #%s (%s): auto-check failed, stays pending", tip_id, target)
        return

    status = "confirmed" if score >= CONFIRM_THRESHOLD else "rejected"
    registry.update_tip_result(tip_id, status, score, investigation_id)
    if status == "confirmed":
        _add_to_community_blacklist(target, tip_id, score)
    logger.info("tip #%s (%s): score %s -> %s", tip_id, target, score, status)


def _add_to_community_blacklist(target: str, tip_id: int, score: int) -> None:
    if COMMUNITY_BLACKLIST.exists():
        try:
            dataset = json.loads(COMMUNITY_BLACKLIST.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("community blacklist unreadable, recreating")
            dataset = None
    else:
        dataset = None

    if not isinstance(dataset, dict) or not isinstance(dataset.get("entries"), list):
        dataset = {
            "regulator": "Сообщество SAQ — наводки, подтверждённые автопроверкой Aqyl",
            "note_on_provenance": (
                "Пополняется автоматически: наводка из ленты сообщества проходит "
                "полный OSINT-прогон, и при risk score выше порога объект "
                "добавляется сюда. Это сигнал для дальнейшей проверки, не приговор."
            ),
            "entries": [],
        }

    if any(e.get("name", "").lower() == target.lower() for e in dataset["entries"]):
        return  # уже в списке

    dataset["entries"].append(
        {
            "name": target,
            "domains": [],
            "note": f"наводка сообщества #{tip_id}, risk score {score}/100, {date.today().isoformat()}",
        }
    )
    dataset["updated"] = date.today().isoformat()
    COMMUNITY_BLACKLIST.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("community blacklist: added «%s» (%s entries total)", target, len(dataset["entries"]))
