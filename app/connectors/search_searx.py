import os

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class SearxConnector(OSINTConnector):
    """Metasearch via a public SearXNG instance.

    A single SearXNG instance fans a query out to dozens of underlying
    engines (Google, Bing, DuckDuckGo, Yandex, Brave, etc.) and returns
    deduplicated results — this is how "searches N search engines at once"
    claims are usually implemented in practice, without needing paid API
    keys for each engine individually.
    """

    name = "searx_metasearch"
    applicable_types = {
        QueryType.NAME_OR_ORG, QueryType.DOMAIN, QueryType.USERNAME,
        QueryType.PHONE,
        QueryType.BTC_ADDRESS, QueryType.ETH_ADDRESS,
    }

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        instance = os.getenv("SEARX_INSTANCE_URL", "https://searx.be").rstrip("/")
        resp = await client.get(
            f"{instance}/search",
            params={"q": query, "format": "json", "language": "all"},
            headers={"User-Agent": "Mozilla/5.0 (OSINT-research-bot)"},
        )
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("results", [])[:15]
        return {
            "engine_count": len(payload.get("engines", [])) or None,
            "results": [
                {"title": r.get("title"), "url": r.get("url"), "content": r.get("content")}
                for r in results
            ],
        }
