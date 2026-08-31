import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class UrlscanConnector(OSINTConnector):
    """urlscan.io public search — past scans of a domain, including
    screenshots, redirect chains and detected trackers. Search endpoint
    is free without an API key (key only needed to submit new scans).
    """

    name = "urlscan_search"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(
            "https://urlscan.io/api/v1/search/",
            params={"q": f"domain:{query}", "size": 10},
        )
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("results", [])
        return {
            "total_scans": payload.get("total", 0),
            "recent_scans": [
                {
                    "task_url": r.get("task", {}).get("url"),
                    "screenshot": r.get("screenshot"),
                    "ip": r.get("page", {}).get("ip"),
                    "country": r.get("page", {}).get("country"),
                    "server": r.get("page", {}).get("server"),
                    "scanned_at": r.get("task", {}).get("time"),
                }
                for r in results[:10]
            ],
        }
