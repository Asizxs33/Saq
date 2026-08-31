import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class CommonCrawlConnector(OSINTConnector):
    """Common Crawl index — independent web crawl, catches mentions/pages
    that Wayback or a live search engine may have missed or removed.
    """

    name = "common_crawl"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        collinfo = await client.get("https://index.commoncrawl.org/collinfo.json")
        collinfo.raise_for_status()
        indexes = collinfo.json()
        if not indexes:
            return {"pages": []}
        latest_index_url = indexes[0]["cdx-api"]

        resp = await client.get(
            latest_index_url,
            params={"url": f"*.{query}/*", "output": "json", "limit": 15},
        )
        if resp.status_code == 404:
            return {"pages": [], "index": indexes[0]["id"]}
        resp.raise_for_status()

        lines = [line for line in resp.text.strip().split("\n") if line]
        import json as _json

        pages = [_json.loads(line) for line in lines]
        return {
            "index": indexes[0]["id"],
            "page_count": len(pages),
            "pages": [
                {"url": p.get("url"), "timestamp": p.get("timestamp"), "status": p.get("status")}
                for p in pages[:10]
            ],
        }
