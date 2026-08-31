import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType


class SecEdgarConnector(OSINTConnector):
    """SEC EDGAR company search (Atom feed) — free, no key. Catches US
    entities that filed anything with the SEC; absence of a filing for an
    entity claiming to be a "regulated US investment fund" is itself a
    red flag worth surfacing.
    """

    name = "sec_edgar_registry"
    applicable_types = {QueryType.NAME_OR_ORG}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        resp = await client.get(
            "https://www.sec.gov/cgi-bin/browse-edgar",
            params={"action": "getcompany", "company": query, "output": "atom", "count": 10},
            headers={"User-Agent": "OSINT research contact@example.com"},
        )
        resp.raise_for_status()

        import xml.etree.ElementTree as ET

        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        entries = root.findall("a:entry", ns)
        return {
            "match_count": len(entries),
            "entries": [
                {
                    "title": e.findtext("a:title", default="", namespaces=ns),
                    "link": e.find("a:link", ns).attrib.get("href") if e.find("a:link", ns) is not None else None,
                }
                for e in entries[:10]
            ],
        }
