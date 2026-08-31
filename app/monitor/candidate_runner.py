import asyncio
import logging
import os

from app import live, registry
from app import settings as app_settings
from app.models import QueryType
from app.orchestrator import investigate

logger = logging.getLogger("candidate_runner")

# Controls how hard we hit external sources (SearX, WHOIS, etc.) and the
# Anthropic key from auto-discovered candidates — separate from, and much
# lower than, what a human clicking "Спросить Aqyl" would trigger one at a
# time. Tune via env if your source rate limits allow more.
BATCH_SIZE = int(os.getenv("CANDIDATE_RUNNER_BATCH_SIZE", "5"))
INTERVAL_SECONDS = int(os.getenv("CANDIDATE_RUNNER_INTERVAL_SECONDS", "60"))

# Our self-hosted SearXNG leans almost entirely on one engine (google cse),
# which has a hard 100 queries/day free quota. This background runner can
# fire dozens of investigations per hour on its own — left unchecked it
# burns through that quota by itself and starves the interactive chat's
# search_web tool (observed: all 5 engines "Suspended" mid-session).
# Metasearch adds little for a bare domain anyway (WHOIS/blacklist/crt.sh/
# blockchain already carry the signal here) — skip it for auto-candidates,
# keep it for anything a human actually asks about.
EXCLUDED_CONNECTORS = {"searx_metasearch"}


async def _process_one(candidate: dict) -> None:
    domain = candidate["domain"]
    try:
        # synthesize=False: LLM summaries aren't persisted anywhere today
        # (see InvestigateResponse — summary is returned, not stored), so
        # generating one for a background run nobody's watching would just
        # burn API credits for nothing. The score/flags DO get persisted via
        # registry.record_investigation() inside investigate(), which is
        # what actually surfaces this domain on /registry (Watchlist) if it
        # scores high enough — a human can always re-run it live for a
        # fresh LLM report.
        investigation_id, _qt, _conn, _res, risk_score, risk_flags, *_ = await investigate(
            domain, QueryType.DOMAIN, False, EXCLUDED_CONNECTORS
        )
        registry.mark_candidate_done(candidate["id"], investigation_id)
        logger.info("auto-investigated candidate: %s -> investigation #%s", domain, investigation_id)

        # находка уходит в открытые вкладки Watchlist сразу, без перезагрузки
        await live.broadcast(
            {
                "type": "investigation",
                "id": investigation_id,
                "query": domain,
                "query_type": QueryType.DOMAIN.value,
                "risk_score": risk_score,
                "risk_flags": risk_flags,
                "source": "certstream_monitor",
            }
        )
    except Exception:
        logger.exception("candidate investigation failed, will retry: %s", domain)
        registry.mark_candidate_failed(candidate["id"])


async def run_candidate_runner_forever() -> None:
    """Periodically drains the candidate_leads queue through the same
    investigate() pipeline a manual query would use. Never raises.
    """
    while True:
        try:
            # пауза из админки — не трогать очередь, но и не выходить из
            # цикла: как только админ снова включит, подхватится сам
            if app_settings.is_certstream_paused():
                await asyncio.sleep(INTERVAL_SECONDS)
                continue
            batch = registry.claim_pending_candidates(BATCH_SIZE)
            if batch:
                logger.info("processing %d candidate(s)", len(batch))
                for candidate in batch:
                    await _process_one(candidate)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("candidate runner tick failed")
        await asyncio.sleep(INTERVAL_SECONDS)
