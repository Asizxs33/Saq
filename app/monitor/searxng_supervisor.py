"""Keeps the local self-hosted SearXNG dev server (vendor/searxng) alive.

The Flask dev server isn't a production WSGI deployment — it can die under
a burst of concurrent outbound requests (observed once during testing: a
storm of parallel search_web tool calls coincided with the process exiting,
cause unconfirmed — no fatal traceback, just stopped). Rather than chase a
possibly-transient root cause, we supervise it the same way
certstream_watcher.py handles CertStream dropping: detect it's down and
restart, with backoff, forever. Best-effort auxiliary infra — if this can't
start (venv missing), it logs and gives up quietly; the searx_metasearch
connector already degrades gracefully when SearXNG is unreachable.
"""

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger("searxng_supervisor")

SEARXNG_DIR = Path(__file__).resolve().parent.parent.parent / "vendor" / "searxng"
RESTART_DELAY_SECONDS = 5


async def run_searxng_supervisor_forever() -> None:
    python_exe = SEARXNG_DIR / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        logger.warning("vendor/searxng/.venv not found — local SearXNG supervisor disabled")
        return

    log_path = SEARXNG_DIR / "searxng.log"

    while True:
        logger.info("starting local SearXNG (vendor/searxng)")
        with open(log_path, "a", encoding="utf-8") as log_file:
            proc = await asyncio.create_subprocess_exec(
                str(python_exe),
                "-m", "searx.webapp",
                # Running "searx/webapp.py" as a script path puts the
                # script's own directory (vendor/searxng/searx/) at the
                # front of sys.path instead of vendor/searxng/ itself, so
                # "import searx" inside webapp.py can't find its own
                # package — crash-loops immediately (exit code 1, no
                # useful stderr beyond ModuleNotFoundError). -m resolves
                # the module through cwd correctly.
                cwd=str(SEARXNG_DIR),
                stdout=log_file,
                stderr=log_file,
                env={**os.environ, "SEARXNG_DEBUG": "0"},
            )
            try:
                returncode = await proc.wait()
                logger.warning(
                    "local SearXNG exited (code %s) — restarting in %ss", returncode, RESTART_DELAY_SECONDS
                )
            except asyncio.CancelledError:
                proc.terminate()
                raise
        await asyncio.sleep(RESTART_DELAY_SECONDS)
