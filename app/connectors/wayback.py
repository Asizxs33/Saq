import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class WaybackConnector(OSINTConnector):
    """Wayback Machine CDX API — historical snapshots of a domain.

    Useful to see when a site first appeared, whether it rebranded, or
    whether earlier snapshots show a different (often more revealing)
    version of the pitch before it was cleaned up.
    """

    name = "wayback_machine"
    applicable_types = {QueryType.DOMAIN}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": query,
                "matchType": "domain",
                "output": "json",
                "limit": 20,
                "collapse": "timestamp:6",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return {"snapshots": []}
        header, *data_rows = rows
        return {
            "first_seen": data_rows[0][1] if data_rows else None,
            "snapshot_count": len(data_rows),
            "snapshots": [dict(zip(header, row)) for row in data_rows[:10]],
        }
