import json
from pathlib import Path

import httpx

from app.connectors.base import OSINTConnector
from app.models import QueryType

BLACKLIST_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "blacklists"


class LocalBlacklistConnector(OSINTConnector):
    """Matches a query against locally stored regulator blacklist
    snapshots (see data/blacklists/README.md). Not a live scraper —
    regulator sites change markup often and often block bots, so this
    reads a manually/periodically refreshed local dataset instead.
    """

    name = "regulator_blacklist_local"
    # single-word pyramid brand names (Finiko, Qnet, Platincoin, Crowd1...)
    # are indistinguishable from usernames by shape alone, and this is a
    # free local JSON scan — so check it for USERNAME queries too, not
    # just NAME_OR_ORG/DOMAIN, or the most common brand-name lookups skip it.
    applicable_types = {QueryType.NAME_OR_ORG, QueryType.DOMAIN, QueryType.USERNAME, QueryType.PHONE}

    async def _fetch(self, client: httpx.AsyncClient, query: str, query_type: QueryType):
        query_lower = query.lower()
        matches = []
        if not BLACKLIST_DIR.exists():
            return {"matches": [], "lists_checked": 0}

        files = list(BLACKLIST_DIR.glob("*.json"))
        for file in files:
            try:
                dataset = json.loads(file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            # Происхождение списка важнее его содержимого: community.json
            # пополняется собственными прогонами Aqyl, и засчитывать его как
            # независимое подтверждение регулятора — значит ссылаться на себя.
            kind = dataset.get("source_kind", "regulator")
            for entry in dataset.get("entries", []):
                haystack = " ".join([entry.get("name", "")] + entry.get("domains", [])).lower()
                if query_lower in haystack:
                    matches.append(
                        {"regulator": dataset.get("regulator"), "source_kind": kind, **entry}
                    )

        return {
            "lists_checked": len(files),
            "matches": matches,
            "regulator_matches": [m for m in matches if m.get("source_kind") == "regulator"],
        }
