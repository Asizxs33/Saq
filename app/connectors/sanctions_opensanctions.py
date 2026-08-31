"""OpenSanctions — санкционные списки и PEP (политически значимые лица).

Почему через выгрузку, а не через их API: api.opensanctions.org требует
платный ключ (401 без него). Но сами данные публикуются свободно под
CC-BY-NC — для некоммерческого проекта вроде SAQ это законный путь.

Берём `names.txt` объединённого датасета sanctions (~10 МБ, ~290 тыс.
сущностей: ЕС, ООН, OFAC, Великобритания и десятки других списков, со
всеми алиасами и транслитерациями, включая кириллицу). Файл скачивается
один раз, кладётся в data/opensanctions/ и обновляется по TTL — так
проверка идёт локально и мгновенно, без сетевого запроса на каждый объект.

Что это даёт расследованию пирамид: организатор или юрлицо, всплывшее в
санкционных списках или среди PEP, — сигнал совсем другого веса, чем
рекламные красные флаги. Совпадение по имени само по себе не приговор
(однофамильцы), поэтому отдаём точное совпадение отдельно от частичного.
"""

import asyncio
import logging
import os
import time
from pathlib import Path

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

logger = logging.getLogger("opensanctions")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "opensanctions"
NAMES_FILE = DATA_DIR / "names.txt"
NAMES_URL = "https://data.opensanctions.org/datasets/latest/sanctions/names.txt"

# Списки меняются ежедневно, но для наших целей суточной свежести достаточно
REFRESH_AFTER_SECONDS = int(os.getenv("OPENSANCTIONS_TTL_SECONDS", str(24 * 3600)))
DOWNLOAD_TIMEOUT = float(os.getenv("OPENSANCTIONS_DOWNLOAD_TIMEOUT", "180"))

# Слишком короткий запрос даст сотни ложных совпадений по подстроке
MIN_PARTIAL_LEN = 5

_names_exact: set[str] | None = None
_names_raw: list[str] = []
_load_lock = asyncio.Lock()


def _needs_refresh() -> bool:
    if not NAMES_FILE.exists():
        return True
    return (time.time() - NAMES_FILE.stat().st_mtime) > REFRESH_AFTER_SECONDS


async def _download() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = NAMES_FILE.with_suffix(".tmp")
    logger.info("скачиваю список имён OpenSanctions…")
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", NAMES_URL) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                async for chunk in resp.aiter_bytes(chunk_size=1 << 16):
                    fh.write(chunk)
    tmp.replace(NAMES_FILE)
    logger.info("OpenSanctions: список обновлён (%.1f МБ)", NAMES_FILE.stat().st_size / 1024 / 1024)


async def _ensure_loaded() -> bool:
    """Гарантирует, что список скачан и разобран в память. Возвращает False,
    если данных нет и скачать не удалось — коннектор тогда честно скажет,
    что источник недоступен, вместо тихого «совпадений нет»."""
    global _names_exact, _names_raw

    async with _load_lock:
        if _needs_refresh():
            try:
                await _download()
                _names_exact = None  # заставит перечитать свежий файл
            except Exception as exc:
                logger.warning("не удалось обновить OpenSanctions: %s", exc)
                if not NAMES_FILE.exists():
                    return False  # и старой копии нет

        if _names_exact is None:
            try:
                raw = NAMES_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as exc:
                logger.warning("не удалось прочитать список OpenSanctions: %s", exc)
                return False
            _names_raw = [n.strip() for n in raw if n.strip()]
            _names_exact = {n.lower() for n in _names_raw}
            logger.info("OpenSanctions: загружено %d имён", len(_names_raw))

    return bool(_names_exact)


class OpenSanctionsConnector(OSINTConnector):
    """Проверка имени по объединённому санкционному датасету OpenSanctions."""

    name = "opensanctions_lists"
    applicable_types = {QueryType.NAME_OR_ORG, QueryType.USERNAME}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        if not await _ensure_loaded():
            return {
                "available": False,
                "note": (
                    "Список OpenSanctions ещё не скачан и обновить его сейчас не вышло — "
                    "проверка по санкционным спискам в этом прогоне не выполнялась."
                ),
            }

        q = query.strip().lower()
        assert _names_exact is not None

        exact = q in _names_exact

        partial: list[str] = []
        if len(q) >= MIN_PARTIAL_LEN:
            for original in _names_raw:
                if q in original.lower():
                    partial.append(original)
                    if len(partial) >= 10:
                        break

        return {
            "available": True,
            "dataset": "OpenSanctions · consolidated sanctions + PEP",
            "names_indexed": len(_names_raw),
            "exact_match": exact,
            "partial_matches": partial if not exact else [],
            "match_count": len(partial),
        }
