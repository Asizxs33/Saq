import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

# Free public API (no key), openly documented via its own OpenAPI spec at
# /openapi.json — the operator explicitly welcomes reasonable programmatic
# use ("Direct API querying is permitted... pls dont get wild" per their
# FAQ). It's a solo-maintainer project with no SLA, so treat it as a
# best-effort auxiliary signal, not a load-bearing source.
API_URL = "https://threatactorusernames.com/api/search"

# Below this length, generic handles ("admin", "trader", "goldman") hit
# almost every breached forum dump and tell you nothing about *this*
# specific target — surface the raw hits either way, but flag them as
# low-confidence so the LLM/reader knows not to over-weight a short match.
LOW_CONFIDENCE_LENGTH = 6


class ThreatActorUsernameConnector(OSINTConnector):
    """Checks a handle against a public index of usernames seen in leaked
    cybercrime/carding forum dumps (Raidforums, Cracked, OGusers, etc.).
    A hit means this exact username showed up in a breach dump somewhere —
    a lead worth a look, not proof of anything on its own, especially for
    short/generic handles that collide constantly across dumps.
    """

    name = "threat_actor_username_search"
    applicable_types = {QueryType.USERNAME, QueryType.TELEGRAM_HANDLE}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        handle = query.lstrip("@").replace("https://t.me/", "").replace("http://t.me/", "")
        resp = await client.get(API_URL, params={"q": handle})
        resp.raise_for_status()
        payload = resp.json()

        forums = sorted({r["forum"] for r in payload.get("results", [])})
        return {
            "found": payload.get("found", False),
            "hit_count": payload.get("count", 0),
            "forums": forums,
            "low_confidence": len(handle) < LOW_CONFIDENCE_LENGTH,
        }
