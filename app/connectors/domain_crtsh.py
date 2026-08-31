import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class CrtShConnector(OSINTConnector):
    """crt.sh certificate transparency log search.

    Reveals subdomains and related domains that share a certificate issuer
    or SAN list — often exposes a network of clone sites run by the same
    operator (common in pyramid schemes that spin up new domains after
    each one gets flagged).
    """

    name = "crtsh_cert_transparency"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(
            "https://crt.sh/",
            params={"q": f"%.{query}", "output": "json"},
            headers={"User-Agent": "Mozilla/5.0 (OSINT-research-bot)"},
        )
        resp.raise_for_status()
        try:
            entries = resp.json()
        except ValueError:
            return {"related_names": []}

        names = sorted({e.get("name_value", "").strip() for e in entries if e.get("name_value")})
        return {"certificate_count": len(entries), "related_names": names[:30]}
