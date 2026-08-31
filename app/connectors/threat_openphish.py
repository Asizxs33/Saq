"""OpenPhish — открытый фид активных фишинговых URL.

Бесплатный аналог платных threat-intel подписок. OpenPhish публикует
открытую выборку из своей базы (community feed): актуальные URL, по
которым прямо сейчас идёт фишинг. Ключ не нужен.

Оговорка про охват, которую важно понимать: бесплатный фид — это срез
последних записей, а не вся база. Отсутствие домена в фиде ничего не
доказывает; наличие — доказывает многое.

Зачем это в SAQ: пирамиды и фишинг часто делят инфраструктуру и приёмы
(поддельные страницы входа «личного кабинета инвестора», клоны сайтов
банков). Совпадение по домену здесь — прямая улика: кто-то уже
зафиксировал на этом хосте фишинговую страницу.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

logger = logging.getLogger("openphish")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "threatfeeds"
FEED_FILE = DATA_DIR / "openphish.txt"
FEED_URL = "https://openphish.com/feed.txt"

# Фид обновляется часто; для наших целей достаточно нескольких часов
REFRESH_AFTER_SECONDS = int(os.getenv("OPENPHISH_TTL_SECONDS", str(6 * 3600)))

_hosts: set[str] | None = None
_entries: list[str] = []
_lock = asyncio.Lock()


def _needs_refresh() -> bool:
    if not FEED_FILE.exists():
        return True
    return (time.time() - FEED_FILE.stat().st_mtime) > REFRESH_AFTER_SECONDS


async def _ensure_loaded() -> bool:
    global _hosts, _entries

    async with _lock:
        if _needs_refresh():
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
                    resp = await c.get(FEED_URL)
                    resp.raise_for_status()
                    FEED_FILE.write_text(resp.text, encoding="utf-8")
                _hosts = None
                logger.info("OpenPhish: фид обновлён")
            except Exception as exc:
                logger.warning("не удалось обновить фид OpenPhish: %s", exc)
                if not FEED_FILE.exists():
                    return False

        if _hosts is None:
            try:
                lines = FEED_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                return False
            _entries = [ln.strip() for ln in lines if ln.strip()]
            hosts = set()
            for url in _entries:
                host = urlparse(url).hostname
                if host:
                    hosts.add(host.lower().removeprefix("www."))
            _hosts = hosts
            logger.info("OpenPhish: загружено %d URL / %d хостов", len(_entries), len(_hosts))

    return _hosts is not None


class OpenPhishConnector(OSINTConnector):
    name = "openphish_feed"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        if not await _ensure_loaded():
            return {"available": False, "note": "Фид OpenPhish недоступен — проверка не выполнялась."}

        assert _hosts is not None
        host = query.lower().strip().removeprefix("www.")
        listed = host in _hosts

        matching_urls = [u for u in _entries if host in u.lower()][:5] if listed else []

        return {
            "available": True,
            "feed_size": len(_entries),
            "listed": listed,
            "matching_urls": matching_urls,
            "note": None
            if listed
            else "Домена нет в открытой части фида. Это не значит «чисто» — бесплатный фид покрывает только свежий срез базы.",
        }
