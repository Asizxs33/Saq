"""Живая трансляция находок по WebSocket.

Автомониторинг CertStream ловит свежезарегистрированные домены и прогоняет
их через тот же investigate(), что и ручной запрос. Раньше результат можно
было увидеть только перезагрузив страницу реестра — теперь каждая находка
уходит подписчикам сразу, и Watchlist пополняется на глазах.

Broadcast-хаб намеренно простой: набор активных сокетов в памяти процесса,
без Redis и очередей. Для одного инстанса этого достаточно; при масштабе на
несколько процессов сюда встанет pub/sub, а интерфейс останется тем же.
"""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("live")

_clients: set[WebSocket] = set()
_lock = asyncio.Lock()


async def register(ws: WebSocket) -> None:
    async with _lock:
        _clients.add(ws)
    logger.info("live: клиент подключён (всего %d)", len(_clients))


async def unregister(ws: WebSocket) -> None:
    async with _lock:
        _clients.discard(ws)
    logger.info("live: клиент отключён (осталось %d)", len(_clients))


async def broadcast(event: dict[str, Any]) -> None:
    """Рассылает событие всем подписчикам. Отвалившиеся сокеты вычищает —
    сам вызов никогда не бросает, чтобы падение одного клиента не роняло
    фоновую задачу, из которой рассылают."""
    async with _lock:
        targets = list(_clients)
    if not targets:
        return

    dead: list[WebSocket] = []
    for ws in targets:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)

    if dead:
        async with _lock:
            for ws in dead:
                _clients.discard(ws)
        logger.info("live: убрано отвалившихся клиентов: %d", len(dead))


def broadcast_soon(event: dict[str, Any]) -> None:
    """Синхронная обёртка — планирует рассылку, не дожидаясь её."""
    try:
        asyncio.get_running_loop().create_task(broadcast(event))
    except RuntimeError:
        pass  # нет активного цикла (например, вызов из синхронного скрипта)


def client_count() -> int:
    return len(_clients)
