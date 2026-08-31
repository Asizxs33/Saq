import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class DuckDuckGoConnector(OSINTConnector):
    """DuckDuckGo Instant Answer API — free, no key, good for known entities."""

    name = "duckduckgo_instant_answer"
    applicable_types = {QueryType.NAME_OR_ORG, QueryType.DOMAIN, QueryType.USERNAME}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        resp.raise_for_status()
        payload = resp.json()
        return {
            "heading": payload.get("Heading"),
            "abstract": payload.get("AbstractText"),
            "abstract_source": payload.get("AbstractSource"),
            "abstract_url": payload.get("AbstractURL"),
            "related_topics": [
                t.get("Text") for t in payload.get("RelatedTopics", []) if isinstance(t, dict) and t.get("Text")
            ][:10],
        }
