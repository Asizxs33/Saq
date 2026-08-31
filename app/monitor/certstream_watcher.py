import asyncio
import json
import logging
import os

import websockets

from app import registry
from app.monitor.markers import match_markers

logger = logging.getLogger("certstream_watcher")

# Points at a local self-hosted certstream-server-go instance (see
# vendor/certstream-server-go) — never the public calidog.io firehose,
# which was found dead (connects but delivers zero messages) when we
# checked. This is best-effort auxiliary infra: if it's not running, the
# watcher just retries with backoff and the rest of the app is unaffected.
CERTSTREAM_WS_URL = os.getenv("CERTSTREAM_WS_URL", "ws://127.0.0.1:8080/domains-only")
RECONNECT_DELAY_SECONDS = 5


async def _handle_message(raw: str) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return

    for domain in payload.get("data", []):
        markers = match_markers(domain)
        if markers:
            clean = domain[2:] if domain.startswith("*.") else domain
            registry.enqueue_candidate_lead(clean, markers)
            logger.info("candidate lead queued: %s (markers=%s)", clean, markers)


async def run_watcher_forever() -> None:
    """Long-running task: connects to the local CertStream feed and queues
    marker-matching domains. Never raises — logs and retries on any
    disconnect so a restart of the Go process doesn't need a Python restart.
    """
    while True:
        try:
            async with websockets.connect(CERTSTREAM_WS_URL, open_timeout=10) as ws:
                logger.info("connected to CertStream at %s", CERTSTREAM_WS_URL)
                async for message in ws:
                    await _handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("CertStream connection lost (%s) — retrying in %ss", exc, RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
